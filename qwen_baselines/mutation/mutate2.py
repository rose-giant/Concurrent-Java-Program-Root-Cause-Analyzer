#!/usr/bin/env python3
"""
mutate_concurrency_v3.py - inject concurrency bugs into Java programs (hard-tier + starvation).

Every operator of mutate_concurrency.py plus:
  atomicity_split_sync  atomicity violation: one critical section split into two (check-then-act)
  nonatomic_rmw         lost update: AtomicInteger/AtomicLong read-modify-write made non-atomic
  order_late_setup      order violation: a shared FIELD's setup moved after the first thread start
  rm_defensive_copy     thread-confinement violation: defensive copy removed
  starve_lock_hog       starvation: a contended lock is held during a long yield loop
  starve_spin_wait      starvation: wait() replaced by a yield-spin that keeps the monitor
  decoy_*               harmless look-alike edits (hard negatives, bug_type 'none')
and two-bug mutants (--pairs-per-program) whose footprints (fields/locks they touch) are DISJOINT.

v3 fixes (from the JPF run on programs 7,8,9,28,84,85):
  * jpf_confirmable is now evidence-based (see --list-ops): rm_join, unsafe_collection, rm_volatile are
    off by default (--include-weak); pairs only use operators that JPF has confirmed.
  * pair independence = disjoint footprints (an earlier pair shared one list and was really one bug).
  * at most one mutant per (program, operator, method) - no near-duplicates.

Workflow (two stages, so every two-bug case is really two confirmed bugs):
  1) python mutate_concurrency_v3.py codes.json -o mutants_v3.json --javac --keep-original --pairs-per-program 0
     -> run every mutant through JPF (results file in the same order as mutants_v3.json)
  2) python mutate_concurrency_v3.py codes.json --pairs-from mutants_v3.json jpf_results.json -o pairs_v3.json --javac
     -> pairs are built ONLY from singles that failed in JPF, with disjoint footprints.
Other:
  python mutate_concurrency_v3.py codes.json --new-only --javac --hog-iters 200   # starvation: longer hog loop
  python mutate_concurrency_v3.py --list-ops                                      # operators + JPF evidence

New vocabulary to add to your GT schema: bug_class 'starvation'; fix_action 'shrink_critical_section',
'restore_blocking_wait', 'merge_critical_sections', 'restore_atomic_op', 'move_setup_before_start',
'restore_defensive_copy'.
"""
import argparse
import difflib
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict

# --------------------------------------------------------------------------
# lexical helpers: work on a "masked" copy (strings/comments blanked, same
# length) so regexes and brace matching are never fooled by literals.
# --------------------------------------------------------------------------

def mask_code(src):
    out = list(src)
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if c == '/' and i + 1 < n and src[i + 1] == '/':
            j = src.find('\n', i)
            j = n if j < 0 else j
            for k in range(i, j):
                out[k] = ' '
            i = j
        elif c == '/' and i + 1 < n and src[i + 1] == '*':
            j = src.find('*/', i + 2)
            j = n if j < 0 else j + 2
            for k in range(i, j):
                if out[k] != '\n':
                    out[k] = ' '
            i = j
        elif c in '"\'':
            q, j = c, i + 1
            while j < n and src[j] != q:
                if src[j] == '\\':
                    j += 1
                j += 1
            j = min(j + 1, n)
            for k in range(i + 1, j - 1):
                if out[k] != '\n':
                    out[k] = ' '
            i = j
        else:
            i += 1
    return ''.join(out)


def match_close(m, i, o, c):
    d = 0
    for k in range(i, len(m)):
        if m[k] == o:
            d += 1
        elif m[k] == c:
            d -= 1
            if d == 0:
                return k
    return -1


def skip_ws(m, i):
    while i < len(m) and m[i].isspace():
        i += 1
    return i


def apply_edits(code, edits):
    """edits: (start, end, text); non-overlapping; applied back to front."""
    for s, e, t in sorted(edits, key=lambda x: (x[0], x[1]), reverse=True):
        code = code[:s] + t + code[e:]
    return code


def balanced(code):
    m = mask_code(code)
    return all(m.count(a) == m.count(b) for a, b in ('{}', '()', '[]'))


# --------------------------------------------------------------------------
# light-weight structural model of a Java source file
# --------------------------------------------------------------------------
KEYWORDS = {'if', 'for', 'while', 'switch', 'catch', 'synchronized', 'try',
            'else', 'do', 'return', 'new', 'throw'}
WAIT_RE = re.compile(r'\b(wait|notify|notifyAll)\s*\(')
AUX = '__auxLock'
WRONG = '__wrongLock'


class Src:
    def __init__(self, code):
        self.code = code
        self.m = mask_code(code)
        self.classes = self._classes()
        self.methods = self._methods()
        self.sync_methods = self._sync_methods()
        self.sync_blocks = self._sync_blocks()

    # ---- classes / methods ------------------------------------------------
    def _classes(self):
        res = []
        for mt in re.finditer(r'\b(class|interface|enum)\s+(\w+)', self.m):
            o = self.m.find('{', mt.end())
            if o < 0:
                continue
            c = match_close(self.m, o, '{', '}')
            if c > 0:
                res.append(dict(kind=mt.group(1), name=mt.group(2), open=o, close=c))
        return res

    def _methods(self):
        res = []
        pat = re.compile(r'(?<![\w.])(\w+)\s*\([^()]*\)\s*(?:throws\s+[\w.,\s]+?)?\s*\{')
        for mt in pat.finditer(self.m):
            name = mt.group(1)
            if name in KEYWORDS:
                continue
            before = self.m[:mt.start()].rstrip()
            if before.endswith('new'):          # anonymous class: new Runnable() {
                continue
            o = mt.end() - 1
            c = match_close(self.m, o, '{', '}')
            if c > 0:
                res.append(dict(name=name, open=o, close=c, decl=mt.start()))
        return res

    def enclosing_class(self, pos):
        cand = [c for c in self.classes if c['open'] < pos < c['close']]
        return min(cand, key=lambda c: c['close'] - c['open']) if cand else None

    def enclosing_method(self, pos):
        cand = [x for x in self.methods if x['open'] < pos < x['close']]
        return min(cand, key=lambda c: c['close'] - c['open'])['name'] if cand else None

    def is_called(self, name):
        """Is `name` invoked from somewhere other than its own body/declaration?
        (ignores delegation such as `map.get(k)` inside our own get())."""
        if not name:
            return False
        own = [(x['decl'], x['close']) for x in self.methods if x['name'] == name]
        pos = [mt.start() for mt in re.finditer(r'\b%s\s*\(' % re.escape(name), self.m)]
        pos += [mt.start() for mt in re.finditer(r'::\s*%s\b' % re.escape(name), self.m)]
        return any(not any(a <= p <= b for a, b in own) for p in pos)

    # ---- synchronized methods --------------------------------------------
    def _sync_methods(self):
        res = []
        for mt in re.finditer(r'\bsynchronized\b(?!\s*\()', self.m):
            s, e = mt.start(), mt.end()
            p = self.m.find('(', e)
            if p < 0 or any(ch in self.m[e:p] for ch in '{};='):
                continue
            q = match_close(self.m, p, '(', ')')
            if q < 0:
                continue
            r = q + 1
            while r < len(self.m) and self.m[r] not in '{;':
                r += 1
            if r >= len(self.m) or self.m[r] != '{':
                continue
            b = match_close(self.m, r, '{', '}')
            if b < 0:
                continue
            nm = re.search(r'(\w+)\s*$', self.m[e:p])
            if not nm:
                continue
            sig_start = max(self.m.rfind(ch, 0, s) for ch in '{};') + 1
            sig = self.m[sig_start:q + 1]
            cls = self.enclosing_class(s)
            res.append(dict(
                start=s, mod_end=skip_ws(self.m, e), name=nm.group(1),
                body_open=r, body_close=b, static=bool(re.search(r'\bstatic\b', sig)),
                has_wait=bool(WAIT_RE.search(self.m[r:b])), cls=cls,
                called=self.is_called(nm.group(1))))
        return res

    # ---- synchronized blocks ---------------------------------------------
    def _sync_blocks(self):
        res = []
        for mt in re.finditer(r'\bsynchronized\s*\(', self.m):
            p = mt.end() - 1
            q = match_close(self.m, p, '(', ')')
            if q < 0:
                continue
            o = skip_ws(self.m, q + 1)
            if o >= len(self.m) or self.m[o] != '{':
                continue
            c = match_close(self.m, o, '{', '}')
            if c < 0:
                continue
            meth = self.enclosing_method(mt.start())
            res.append(dict(
                start=mt.start(), lock_s=p + 1, lock_e=q, lock=self.code[p + 1:q].strip(),
                header_end=o, body_open=o, body_close=c, method=meth,
                cls=self.enclosing_class(mt.start()), called=self.is_called(meth)))
        return res

    # ---- misc -------------------------------------------------------------
    def sync_sites_in(self, cls):
        n = sum(1 for x in self.sync_methods if x['cls'] is cls)
        n += sum(1 for x in self.sync_blocks if x['cls'] is cls)
        return n

    def aux_field_edit(self, cls, name=AUX):
        return (cls['open'] + 1, cls['open'] + 1,
                ' private static final Object %s = new Object(); ' % name)


def same_cls(a, b):
    return a is not None and a is b


def cls_ok(c):
    return c is not None and c['kind'] == 'class'


def drop_modifier(x):
    return (x['start'], x['mod_end'], '')


def wrap_body(body_open, body_close, head, tail):
    """insert `head` after '{' and `tail` before the matching '}'."""
    return [(body_open + 1, body_open + 1, ' ' + head + ' '),
            (body_close, body_close, ' ' + tail + ' ')]


# --------------------------------------------------------------------------
# mutation operators.  Each returns [(priority, description, new_code)]
# (lower priority number = more likely to manifest, kept first when capping)
# --------------------------------------------------------------------------
OPS = {}


def op(name, bug, expected, doc):
    def deco(fn):
        OPS[name] = dict(fn=fn, bug=bug, expected=expected, doc=doc)
        return fn
    return deco


# ---------------------------- RACE CONDITIONS -----------------------------

@op('rm_sync_all', 'race', 'PreciseRaceDetector data race',
    'BASELINE: strip `synchronized` from every method signature (what you already do).')
def rm_sync_all(S):
    if not S.sync_methods:
        return []
    return [(0, 'removed synchronized from all %d methods' % len(S.sync_methods),
             apply_edits(S.code, [drop_modifier(x) for x in S.sync_methods]))]


@op('rm_sync_one', 'race', 'PreciseRaceDetector data race',
    'Remove `synchronized` from ONE method only (partial protection: the remaining synchronized '
    'methods now race against the unprotected one).')
def rm_sync_one(S):
    res = []
    for x in S.sync_methods:
        if x['has_wait']:
            continue
        res.append((0 if x['called'] else 1, 'removed synchronized from method %s()' % x['name'],
                    apply_edits(S.code, [drop_modifier(x)])))
    return res


@op('rm_sync_block', 'race', 'PreciseRaceDetector data race',
    'Unwrap ONE `synchronized (lock) {...}` block (the body stays, the lock is gone).')
def rm_sync_block(S):
    res = []
    for b in S.sync_blocks:
        e = skip_ws(S.m, b['lock_e'] + 1)
        res.append((0 if b['called'] else 1,
                    'removed synchronized(%s) block in %s()' % (b['lock'], b['method']),
                    apply_edits(S.code, [(b['start'], e, '')])))
    return res


@op('wrong_lock', 'race', 'PreciseRaceDetector data race',
    'Guard ONE critical section with a different lock than the other sections of the class '
    '(inconsistent locking: looks synchronized, but there is no common lock).')
def wrong_lock(S):
    res = []
    for x in S.sync_methods:
        if x['has_wait'] or x['static'] or not cls_ok(x['cls']) or S.sync_sites_in(x['cls']) < 2:
            continue
        ed = [drop_modifier(x), S.aux_field_edit(x['cls'], WRONG)]
        ed += wrap_body(x['body_open'], x['body_close'], 'synchronized (%s) {' % WRONG, '}')
        res.append((0 if x['called'] else 1, 'method %s() now locks a private unrelated lock' % x['name'],
                    apply_edits(S.code, ed)))
    for b in S.sync_blocks:
        if not cls_ok(b['cls']) or S.sync_sites_in(b['cls']) < 2:
            continue
        ed = [(b['lock_s'], b['lock_e'], WRONG), S.aux_field_edit(b['cls'], WRONG)]
        res.append((0 if b['called'] else 1,
                    'block in %s() locks %s instead of %s' % (b['method'], WRONG, b['lock']),
                    apply_edits(S.code, ed)))
    return res


@op('rm_volatile', 'race', 'PreciseRaceDetector data race (visibility)',
    'Remove ONE `volatile` modifier.')
def rm_volatile(S):
    res = []
    for mt in re.finditer(r'\bvolatile\s+', S.m):
        line_start = max(S.m.rfind(ch, 0, mt.start()) for ch in ';{}') + 1
        decl = S.code[mt.end():S.m.find(';', mt.end())].strip()
        res.append((0, 'removed volatile from: %s' % ' '.join(decl.split())[:60],
                    apply_edits(S.code, [(mt.start(), mt.end(), '')])))
    return res


@op('unsafe_collection', 'race', 'PreciseRaceDetector data race inside the collection '
    '(needs java.util.* not excluded from race detection)',
    'Downgrade a thread-safe collection: unwrap Collections.synchronizedX(..) (one site each), or '
    'ConcurrentHashMap -> HashMap (all occurrences).')
def unsafe_collection(S):
    res = []
    for mt in re.finditer(r'Collections\s*\.\s*synchronized(List|Map|Set|Collection)\s*\(', S.m):
        p = mt.end() - 1
        q = match_close(S.m, p, '(', ')')
        if q < 0:
            continue
        inner = S.code[p + 1:q]
        res.append((0, 'unwrapped Collections.synchronized%s(...)' % mt.group(1),
                    apply_edits(S.code, [(mt.start(), q + 1, inner)])))
    if re.search(r'ConcurrentHashMap', S.m):
        c = S.code.replace('java.util.concurrent.ConcurrentHashMap', 'java.util.HashMap')
        c = c.replace('ConcurrentHashMap', 'HashMap')
        res.append((0, 'ConcurrentHashMap -> HashMap', c))
    return res


@op('rm_join', 'race', 'PreciseRaceDetector data race between worker writes and main-thread reads',
    'Remove ONE `t.join();` so the main thread no longer waits for a worker (missing happens-before).')
def rm_join(S):
    res = []
    for mt in re.finditer(r'\b\w+\s*\.\s*join\s*\(\s*\)\s*;', S.m):
        res.append((0, 'removed %s' % ' '.join(S.code[mt.start():mt.end()].split()),
                    apply_edits(S.code, [(mt.start(), mt.end(), '')])))
    return res


@op('nonatomic_cas', 'semantic', 'usually NOT reported by JPF (lost update, no data race); needs an assertion',
    'Replace AtomicReference.compareAndSet by a check-then-set (lost-update bug). Appends a helper class.')
def nonatomic_cas(S):
    res = []
    helper = ('\n\nclass RacyCas {\n    static <T> boolean compareAndSet(java.util.concurrent.atomic.AtomicReference<T> r, '
              'T expect, T update) {\n        if (r.get() == expect) { r.set(update); return true; }\n'
              '        return false;\n    }\n}\n')
    for mt in re.finditer(r'\b(\w+)\s*\.\s*compareAndSet\s*\(', S.m):
        if 'AtomicReference' not in S.m:
            break
        p = mt.end() - 1
        q = match_close(S.m, p, '(', ')')
        args = S.code[p + 1:q]
        new = 'RacyCas.compareAndSet(%s, %s)' % (mt.group(1), args)
        code = apply_edits(S.code, [(mt.start(), q + 1, new)])
        res.append((0, 'compareAndSet on %s made non-atomic' % mt.group(1), code.rstrip() + helper))
    return res


# ------------------------------- EXCEPTIONS -------------------------------

@op('monitor_misuse', 'exception', 'uncaught java.lang.IllegalMonitorStateException',
    'Remove `synchronized` from ONE method that calls wait()/notify()/notifyAll().')
def monitor_misuse(S):
    return [(0, 'removed synchronized from %s(), which calls wait/notify' % x['name'],
             apply_edits(S.code, [drop_modifier(x)])) for x in S.sync_methods if x['has_wait']]


# -------------------------------- DEADLOCKS -------------------------------

@op('lock_order_inversion_methods', 'deadlock', 'JPF "deadlock encountered"',
    'Two synchronized methods A,B of a class: A takes (this -> aux), B takes (aux -> this). '
    'Mutual exclusion is preserved, but opposite acquisition order => classic lock-ordering deadlock.')
def lock_order_inversion_methods(S):
    res = []
    by_cls = defaultdict(list)
    for x in S.sync_methods:
        if not x['has_wait'] and not x['static'] and cls_ok(x['cls']):
            by_cls[id(x['cls'])].append(x)
    for xs in by_cls.values():
        for i in range(len(xs)):
            for j in range(i + 1, len(xs)):
                a, b = xs[i], xs[j]
                ed = [S.aux_field_edit(a['cls'])]
                ed += wrap_body(a['body_open'], a['body_close'], 'synchronized (%s) {' % AUX, '}')
                ed.append(drop_modifier(b))
                ed += wrap_body(b['body_open'], b['body_close'],
                                'synchronized (%s) { synchronized (this) {' % AUX, '} }')
                pr = 0 if (a['called'] and b['called']) else 1
                res.append((pr, '%s() locks this->aux, %s() locks aux->this' % (a['name'], b['name']),
                            apply_edits(S.code, ed)))
    return res


@op('lock_order_inversion_blocks', 'deadlock', 'JPF "deadlock encountered"',
    'Two synchronized blocks in different methods get nested in opposite order: distinct locks L1,L2 '
    '-> (L1,L2) vs (L2,L1); same lock L -> (L,aux) vs (aux,L).')
def lock_order_inversion_blocks(S):
    res = []
    simple = re.compile(r'^(this|\w+(\.\w+)*)$')
    bl = [b for b in S.sync_blocks if simple.match(b['lock']) and cls_ok(b['cls'])]
    for i in range(len(bl)):
        for j in range(i + 1, len(bl)):
            a, b = bl[i], bl[j]
            if not same_cls(a['cls'], b['cls']) or a['method'] == b['method']:
                continue
            if a['body_open'] < b['start'] < a['body_close'] or b['body_open'] < a['start'] < b['body_close']:
                continue
            ed = []
            if a['lock'] != b['lock']:
                ed += wrap_body(a['body_open'], a['body_close'], 'synchronized (%s) {' % b['lock'], '}')
                ed += wrap_body(b['body_open'], b['body_close'], 'synchronized (%s) {' % a['lock'], '}')
                desc = '%s() nests %s->%s, %s() nests %s->%s' % (
                    a['method'], a['lock'], b['lock'], b['method'], b['lock'], a['lock'])
                pr = 0
            else:
                ed.append(S.aux_field_edit(a['cls']))
                ed += wrap_body(a['body_open'], a['body_close'], 'synchronized (%s) {' % AUX, '}')
                ed.append((b['lock_s'], b['lock_e'], AUX))
                ed += wrap_body(b['body_open'], b['body_close'], 'synchronized (%s) {' % a['lock'], '}')
                desc = '%s() nests %s->aux, %s() nests aux->%s' % (a['method'], a['lock'], b['method'], a['lock'])
                pr = 1
            if not (a['called'] and b['called']):
                pr += 2
            res.append((pr, desc, apply_edits(S.code, ed)))
    return res


@op('missing_notify', 'deadlock', 'JPF "deadlock encountered" (waiter never woken)',
    'Remove ONE notify()/notifyAll() call.')
def missing_notify(S):
    res = []
    for mt in re.finditer(r'(?:\b\w+\s*\.\s*)?\bnotify(?:All)?\s*\(\s*\)\s*;', S.m):
        res.append((0, 'removed %s' % ' '.join(S.code[mt.start():mt.end()].split()),
                    apply_edits(S.code, [(mt.start(), mt.end(), '')])))
    return res


@op('unguarded_wait', 'deadlock', 'JPF "deadlock encountered" (lost wake-up when notify runs first)',
    'Turn `while (cond) { wait(); }` into an unconditional wait (condition re-check removed).')
def unguarded_wait(S):
    res = []
    for mt in re.finditer(r'\bwhile\s*\(', S.m):
        p = mt.end() - 1
        q = match_close(S.m, p, '(', ')')
        o = skip_ws(S.m, q + 1)
        if q < 0 or o >= len(S.m) or S.m[o] != '{':
            continue
        c = match_close(S.m, o, '{', '}')
        if c > 0 and re.search(r'\bwait\s*\(', S.m[o:c]):
            res.append((0, 'removed guard of while(%s) around wait()' % S.code[p + 1:q].strip(),
                        apply_edits(S.code, [(mt.start(), o, '')])))
    return res


@op('semaphore_starve', 'deadlock', 'JPF "deadlock encountered" (acquire never satisfied)',
    'Create ONE Semaphore with one permit fewer than originally.')
def semaphore_starve(S):
    res = []
    for mt in re.finditer(r'\bnew\s+(?:java\.util\.concurrent\.)?Semaphore\s*\(', S.m):
        p = mt.end() - 1
        q = match_close(S.m, p, '(', ')')
        arg = S.code[p + 1:q].strip()
        if q < 0 or ',' in arg or arg in ('0', ''):
            continue
        res.append((0, 'Semaphore(%s) -> Semaphore(max(0, %s - 1))' % (arg, arg),
                    apply_edits(S.code, [(p + 1, q, 'Math.max(0, (%s) - 1)' % arg)])))
    return res


@op('missing_release', 'deadlock', 'JPF "deadlock encountered" (permit never returned)',
    'Remove ONE semaphore.release() call.')
def missing_release(S):
    res = []
    for mt in re.finditer(r'\b\w+\s*\.\s*release\s*\(\s*\)\s*;', S.m):
        res.append((0, 'removed %s' % ' '.join(S.code[mt.start():mt.end()].split()),
                    apply_edits(S.code, [(mt.start(), mt.end(), '')])))
    return res




# --------------------------------------------------------------------------
# optional compile check (needs a JDK on PATH; use the same Java as JPF, i.e. 8)
# --------------------------------------------------------------------------

# ==========================================================================
# v2 ADDITIONS: new operators, decoys, two-bug (pair) mutants, metadata
# ==========================================================================

def split_stmts(m, o, c):
    """top-level statements of the block m[o]=='{' .. m[c]=='}' -> [(start, end)] (end exclusive)."""
    res, start, depth, i = [], None, 0, o + 1
    while i < c:
        ch = m[i]
        if start is None:
            if ch.isspace():
                i += 1
                continue
            start = i
        if ch in '([{':
            depth += 1
        elif ch in ')]}':
            depth -= 1
        if depth == 0 and ch == ';':
            j = skip_ws(m, i + 1)
            if not (m.startswith('else', j) and not (m[j + 4:j + 5].isalnum() or m[j + 4:j + 5] == '_')):
                res.append((start, i + 1))
                start = None
        elif depth == 0 and ch == '}':
            j = skip_ws(m, i + 1)
            nxt = re.match(r'(else|catch|finally)\b', m[j:j + 8])
            dowhile = m[start:start + 2] == 'do' and re.match(r'while\b', m[j:j + 6])
            cont = j < len(m) and m[j] in ';),'          # `new X() { ... };`  /  `() -> { ... });`
            if not nxt and not dowhile and not cont:
                res.append((start, i + 1))
                start = None
        i += 1
    return res


DECL_RE = re.compile(r'\s*(?:final\s+)?([\w.]+(?:<[^;=()]*>)?(?:\[\])*)\s+(\w+)\s*(=|;)')
NOT_TYPES = {'return', 'throw', 'new', 'else', 'case', 'break', 'continue'}


def declared_name(stmt):
    mt = DECL_RE.match(stmt)
    return mt.group(2) if mt and mt.group(1) not in NOT_TYPES else None


def class_fields(S, cls):
    names = set()
    for a, b in split_stmts(S.m, cls['open'], cls['close']):
        t = S.m[a:b]
        if not t.endswith(';'):
            continue
        head = re.split(r'[=;]', t, 1)[0]
        if '(' in head:
            continue
        mt = re.search(r'(\w+)\s*$', head)
        if mt and mt.group(1) not in KEYWORDS:
            names.add(mt.group(1))
    return names


def add_helper(code, helper):
    return code.rstrip() + '\n\n' + helper


# ------------------------------- ATOMICITY --------------------------------

@op('atomicity_split_sync', 'atomicity',
    'usually NOT reported by JPF (every access is still locked => no data race); needs an assertion/exception on the broken invariant',
    'Split ONE critical section into two consecutive critical sections on the same lock, between two '
    'statements that touch the same field (check-then-act / read-modify-write is no longer atomic).')
def atomicity_split_sync(S):
    res = []
    sites = []
    for x in S.sync_methods:
        if not x['has_wait'] and not x['static'] and cls_ok(x['cls']):
            sites.append(('m', x, x['body_open'], x['body_close'], x['name'], 'this'))
    for b in S.sync_blocks:
        if cls_ok(b['cls']) and not WAIT_RE.search(S.m[b['body_open']:b['body_close']]):
            sites.append(('b', b, b['body_open'], b['body_close'], b['method'], b['lock']))
    for kind, x, bo, bc, meth, lock in sites:
        stm = split_stmts(S.m, bo, bc)
        if len(stm) < 2:
            continue
        fields = class_fields(S, x['cls'])
        for k in range(1, len(stm)):
            first, second = stm[:k], stm[k:]
            if any(re.match(r'(return|throw)\b', S.m[a:b]) for a, b in first):
                continue
            ftxt = S.m[first[0][0]:first[-1][1]]
            stxt = S.m[second[0][0]:second[-1][1]]
            declared = {declared_name(S.m[a:b]) for a, b in first} - {None}
            if any(re.search(r'\b%s\b' % re.escape(d), stxt) for d in declared):
                continue
            shared = fields & set(re.findall(r'\w+', ftxt)) & set(re.findall(r'\w+', stxt))
            if not shared:
                continue
            s2 = second[0][0]
            if kind == 'm':
                ed = [drop_modifier(x), (first[0][0], first[0][0], 'synchronized (this) { '),
                      (s2, s2, '} synchronized (this) { '), (bc, bc, ' }')]
            else:
                ed = [(s2, s2, '} synchronized (%s) { ' % lock)]
            res.append((0 if x['called'] else 1,
                        'critical section of %s() split between statements %d and %d (shared: %s)'
                        % (meth, k, k + 1, ','.join(sorted(shared))), apply_edits(S.code, ed)))
    return res


def _racy_atomic_helper():
    out = ['class RacyAtomic {']
    for T, P in (('AtomicInteger', 'int'), ('AtomicLong', 'long')):
        A = 'java.util.concurrent.atomic.' + T
        out += ['    static %s incrementAndGet(%s a) { %s v = a.get() + 1; a.set(v); return v; }' % (P, A, P),
                '    static %s getAndIncrement(%s a) { %s v = a.get(); a.set(v + 1); return v; }' % (P, A, P),
                '    static %s decrementAndGet(%s a) { %s v = a.get() - 1; a.set(v); return v; }' % (P, A, P),
                '    static %s getAndDecrement(%s a) { %s v = a.get(); a.set(v - 1); return v; }' % (P, A, P),
                '    static %s addAndGet(%s a, %s d) { %s v = a.get() + d; a.set(v); return v; }' % (P, A, P, P),
                '    static %s getAndAdd(%s a, %s d) { %s v = a.get(); a.set(v + d); return v; }' % (P, A, P, P)]
    return '\n'.join(out) + '\n}\n'


@op('nonatomic_rmw', 'atomicity',
    'usually NOT reported by JPF (lost update, no data race); needs an assertion',
    'Replace ONE AtomicInteger/AtomicLong read-modify-write (incrementAndGet, addAndGet, ...) by '
    'get()+set() (lost update). Appends a helper class.')
def nonatomic_rmw(S):
    if not re.search(r'\bAtomic(Integer|Long)\b', S.m) or 'class RacyAtomic' in S.m:
        return []
    res = []
    pat = (r'([A-Za-z_][\w.]*(?:\[[^\]]*\])?)\s*\.\s*(incrementAndGet|getAndIncrement|decrementAndGet|'
           r'getAndDecrement|addAndGet|getAndAdd)\s*\(')
    for mt in re.finditer(pat, S.m):
        p = mt.end() - 1
        q = match_close(S.m, p, '(', ')')
        if q < 0:
            continue
        args = S.code[p + 1:q].strip()
        new = 'RacyAtomic.%s(%s%s)' % (mt.group(2), S.code[mt.start(1):mt.end(1)], (', ' + args) if args else '')
        res.append((0, '%s.%s() made a non-atomic read-modify-write' % (mt.group(1), mt.group(2)),
                    add_helper(apply_edits(S.code, [(mt.start(), q + 1, new)]), _racy_atomic_helper())))
    return res


# --------------------------------- ORDER ----------------------------------

@op('order_late_setup', 'order',
    'PreciseRaceDetector data race on the setup field, or NullPointerException in the worker',
    'Move ONE setup statement (field assignment / init call) from before the first thread start to '
    'right after it (use-before-initialisation: order violation).')
def order_late_setup(S):
    res = []
    start_re = re.compile(r'\.\s*start\s*\(\s*\)\s*;|\.\s*(?:execute|submit)\s*\(')
    skip_re = re.compile(r'Thread|\.\s*start\b|\.\s*join\b|System\s*\.|Executors|\.\s*execute\b|\.\s*submit\b')
    for meth in S.methods:
        sts = split_stmts(S.m, meth['open'], meth['close'])
        first = next((i for i, (a, b) in enumerate(sts) if start_re.search(S.m[a:b])), None)
        if first is None:
            continue
        cls = S.enclosing_class(meth['open'])
        fields = class_fields(S, cls) if cls else set()
        for i in range(first):
            a, b = sts[i]
            t = S.m[a:b]
            if not t.endswith(';') or declared_name(t) or skip_re.search(t):
                continue
            lead = re.match(r'\s*(?:this\s*\.\s*)?(\w+)', t)
            if not lead:
                continue
            if lead.group(1) not in fields:     # locals captured by lambdas cannot race at field level
                continue
            ed = [(a, b, ''), (sts[first][1], sts[first][1], ' ' + S.code[a:b])]
            res.append((0,
                        'setup statement `%s` in %s() moved after the first thread start' % (' '.join(S.code[a:b].split())[:60], meth['name']),
                        apply_edits(S.code, ed)))
    return res


# ------------------------- THREAD CONFINEMENT -----------------------------

@op('rm_defensive_copy', 'race',
    'PreciseRaceDetector data race / exception inside java.util (only if java.util.* is NOT excluded from race detection)',
    'Replace a defensive copy `new ArrayList<>(x)` (or HashMap/HashSet/...) by `x` itself, so state that was '
    'thread-confined now escapes and is shared.')
def rm_defensive_copy(S):
    res = []
    pat = re.compile(r'new\s+(?:java\.util\.)?(?:ArrayList|LinkedList|HashMap|LinkedHashMap|TreeMap|HashSet|'
                     r'TreeSet|ArrayDeque)\s*(?:<[^()]*?>)?\s*\(\s*([A-Za-z_][\w.]*)\s*\)')
    for mt in pat.finditer(S.m):
        decl = re.search(r'([\w.]+(?:<[^;=()]*>)?)\s+%s\s*[=;,)]' % re.escape(mt.group(1).split('.')[-1]), S.m)
        if decl and re.search(r'Concurrent|CopyOnWrite|Synchronized', decl.group(1)):
            continue                            # source is already thread-safe: the copy only made a snapshot
        res.append((0, 'defensive copy of %s removed in %s()' % (mt.group(1), S.enclosing_method(mt.start()) or '<field>'),
                    apply_edits(S.code, [(mt.start(), mt.end(), mt.group(1))])))
    return res


# --------------------------------- DECOYS ---------------------------------
# harmless edits that LOOK like concurrency changes (hard negatives; bug_type 'none')

@op('decoy_sync_method_to_block', 'none', 'no JPF error (semantically equivalent refactoring)',
    'DECOY: turn `synchronized m() {..}` into `m() { synchronized (this) {..} }` (identical locking).')
def decoy_sync_method_to_block(S):
    return [(0, '%s(): synchronized modifier replaced by an equivalent synchronized(this) block' % x['name'],
             apply_edits(S.code, [drop_modifier(x)] + wrap_body(x['body_open'], x['body_close'], 'synchronized (this) {', '}')))
            for x in S.sync_methods if not x['static'] and cls_ok(x['cls'])]


@op('decoy_reentrant_lock', 'none', 'no JPF error (reentrant re-acquisition of the same lock)',
    'DECOY: wrap the body of a synchronized method/block in a second, redundant synchronized on the same lock.')
def decoy_reentrant_lock(S):
    res = [(0, '%s(): redundant reentrant synchronized(this)' % x['name'],
            apply_edits(S.code, wrap_body(x['body_open'], x['body_close'], 'synchronized (this) {', '}')))
           for x in S.sync_methods if not x['static'] and cls_ok(x['cls'])]
    for b in S.sync_blocks:
        res.append((1, 'block in %s(): redundant nested synchronized(%s)' % (b['method'], b['lock']),
                    apply_edits(S.code, wrap_body(b['body_open'], b['body_close'], 'synchronized (%s) {' % b['lock'], '}'))))
    return res


@op('decoy_redundant_join', 'none', 'no JPF error (joining a finished thread again is a no-op)',
    'DECOY: duplicate ONE `t.join();`.')
def decoy_redundant_join(S):
    return [(0, 'duplicated %s' % ' '.join(S.code[mt.start():mt.end()].split()),
             apply_edits(S.code, [(mt.end(), mt.end(), ' ' + S.code[mt.start():mt.end()])]))
            for mt in re.finditer(r'\b\w+\s*\.\s*join\s*\(\s*\)\s*;', S.m)]


# ------------------------------ STARVATION --------------------------------
HOG_ITERS = [100]


def _lock_sites(S):
    """synchronized sites grouped by (class, lock): (kind, site, body_open, body_close, method)."""
    groups = {}
    for x in S.sync_methods:
        if cls_ok(x['cls']):
            key = (x['cls']['name'], '<static>' if x['static'] else 'this')
            groups.setdefault(key, []).append(('m', x, x['body_open'], x['body_close'], x['name']))
    for b in S.sync_blocks:
        if cls_ok(b['cls']):
            key = (b['cls']['name'], re.sub(r'\s+', '', b['lock']))
            groups.setdefault(key, []).append(('b', b, b['body_open'], b['body_close'], b['method']))
    return groups


@op('starve_lock_hog', 'starvation',
    'JPF-STARVATION: the threads competing for the lock wait for most of the run (waiting proportion far above '
    'the 45-75% of healthy runs); no deadlock, the run finishes',
    'Insert a long Thread.yield() loop at the start of ONE critical section whose lock other methods also need '
    '(lock hogging: the holder keeps the lock while the others starve).')
def starve_lock_hog(S):
    res, n = [], HOG_ITERS[0]
    for key, group in _lock_sites(S).items():
        if len({g[4] for g in group}) < 2:
            continue                                     # nobody competes for this lock
        for kind, x, bo, bc, meth in group:
            if WAIT_RE.search(S.m[bo:bc]):               # a wait() releases the monitor: not a hog
                continue
            loop = ' for (int __hog = 0; __hog < %d; __hog++) { Thread.yield(); } ' % n
            res.append((0 if x.get('called', True) else 1,
                        '%s(): lock %s held during a %d-iteration yield loop (lock hogging)' % (meth, key[1], n),
                        apply_edits(S.code, [(bo + 1, bo + 1, loop)])))
    return res


@op('starve_spin_wait', 'starvation',
    'JPF-STARVATION: the thread that must change the condition stays blocked while the waiter spins holding the '
    'monitor; no deadlock (the spinner is always runnable)',
    'Replace ONE `wait();` by a Thread.yield() spin: the waiter keeps the monitor, so the thread that must make '
    'the condition true can never enter (starvation, not deadlock).')
def starve_spin_wait(S):
    res = []
    for mt in re.finditer(r'(?:\b[\w.]+\s*\.\s*)?\bwait\s*\(\s*\)\s*;', S.m):
        new = '{ Thread.yield(); if (false) { throw new InterruptedException(); } }'
        res.append((0, 'wait() in %s() replaced by a yield-spin that keeps the monitor' % method_at(S, mt.start()),
                    apply_edits(S.code, [(mt.start(), mt.end(), new)])))
    return res



# ------------------------------- METADATA ---------------------------------
# jpf: yes = JPF should report it | needs-oracle = JPF cannot see it without an assertion |
#      benign = no program-level defect | baseline
META = {
    'rm_sync_all':      dict(jpf='baseline', bug_class='data_race', fix=('add_or_widen_synchronization', 'restore_sync_block')),
    'rm_sync_one':      dict(jpf='yes', bug_class='data_race', fix=('add_or_widen_synchronization', 'restore_sync_block')),
    'rm_sync_block':    dict(jpf='yes', bug_class='data_race', fix=('add_or_widen_synchronization', 'restore_sync_block')),
    'wrong_lock':       dict(jpf='yes', bug_class='data_race', fix=('change_lock_order_or_granularity', 'unify_lock')),
    'rm_volatile':      dict(jpf='unverified', bug_class='data_race', fix=('add_volatile', 'add_volatile_or_atomic')),
    'unsafe_collection': dict(jpf='no', bug_class='data_race', fix=('use_atomic_or_concurrent_class', 'other')),
    'rm_join':          dict(jpf='benign', bug_class='no_defect', fix=('other', 'restore_join')),
    'nonatomic_cas':    dict(jpf='needs-oracle', bug_class='atomicity_violation', fix=('use_atomic_or_concurrent_class', 'other')),
    'monitor_misuse':   dict(jpf='yes', bug_class='monitor_misuse', fix=('add_or_widen_synchronization', 'restore_sync_block')),
    'lock_order_inversion_methods': dict(jpf='yes', bug_class='resource_deadlock', fix=('change_lock_order_or_granularity', 'remove_nested_lock')),
    'lock_order_inversion_blocks':  dict(jpf='yes', bug_class='resource_deadlock', fix=('change_lock_order_or_granularity', 'remove_nested_lock')),
    'missing_notify':   dict(jpf='yes', bug_class='communication_deadlock', fix=('fix_wait_notify', 'restore_notify')),
    'unguarded_wait':   dict(jpf='yes', bug_class='communication_deadlock', fix=('fix_wait_notify', 'restore_wait_loop')),
    'semaphore_starve': dict(jpf='yes', bug_class='resource_deadlock', fix=('other', 'restore_semaphore_permits')),
    'missing_release':  dict(jpf='yes', bug_class='resource_deadlock', fix=('other', 'restore_release')),
    # --- new in v2 (fix_action labels marked * are NEW: add them to your vocabulary)
    'atomicity_split_sync': dict(jpf='needs-oracle', bug_class='atomicity_violation', fix=('add_or_widen_synchronization', 'merge_critical_sections')),  # *
    'nonatomic_rmw':    dict(jpf='needs-oracle', bug_class='atomicity_violation', fix=('use_atomic_or_concurrent_class', 'restore_atomic_op')),        # *
    'order_late_setup': dict(jpf='unverified', bug_class='order_violation', fix=('other', 'move_setup_before_start')),                                          # *
    'rm_defensive_copy': dict(jpf='yes', bug_class='data_race', fix=('thread_confinement_or_immutability', 'restore_defensive_copy')),                   # *
    'starve_lock_hog':  dict(jpf='unverified', bug_class='starvation', fix=('change_lock_order_or_granularity', 'shrink_critical_section')),   # *
    'starve_spin_wait': dict(jpf='unverified', bug_class='starvation', fix=('fix_wait_notify', 'restore_blocking_wait')),                    # *
    'decoy_sync_method_to_block': dict(jpf='benign', bug_class='no_defect', fix=('none', 'none')),
    'decoy_reentrant_lock':       dict(jpf='benign', bug_class='no_defect', fix=('none', 'none')),
    'decoy_redundant_join':       dict(jpf='benign', bug_class='no_defect', fix=('none', 'none')),
}
DECOYS = [k for k in OPS if k.startswith('decoy_')]
NEW_OPS = ['atomicity_split_sync', 'nonatomic_rmw', 'order_late_setup', 'rm_defensive_copy',
           'starve_lock_hog', 'starve_spin_wait']
WEAK = ['rm_join', 'unsafe_collection', 'rm_volatile']       # produced no JPF failure so far (see EVIDENCE)
EVIDENCE = {
    'rm_join': 'benign: 0/11 failed on programs 7,8,9,28,84,85 (all Pass)',
    'unsafe_collection': '0/5 failed on programs 7,8,9,84,85; 0 cases in the 99-case GT',
    'rm_volatile': '0 cases in the 99-case GT',
    'order_late_setup': '0/4 failed (programs 28, 85); unexplained for 85 - check the race listener',
    'rm_defensive_copy': '1/1 failed (program 28: ConcurrentModificationException in Collections.sort)',
    'starve_lock_hog': 'untested; JPF-STARVATION threshold unknown (healthy runs print up to ~74%)',
    'starve_spin_wait': 'untested; JPF-STARVATION threshold unknown (healthy runs print up to ~74%)',
}
for _k, _v in META.items():
    EVIDENCE.setdefault(_k, 'confirmed in the 99-case GT' if _v['jpf'] == 'yes' else '')
DEFAULT_OPS = [k for k in OPS if k not in ('rm_sync_all', 'nonatomic_cas') and k not in DECOYS and k not in WEAK]
PAIRABLE = [k for k, v in META.items() if v['jpf'] == 'yes']      # both bugs must be JPF-visible
for _k in OPS:
    assert _k in META, 'missing META for %s' % _k


# ----------------------- two-bug composition (pairs) -----------------------

def _toks(s):
    return re.findall(r'\w+|\s+|.', s, re.S)


def diff_regions(orig, new):
    """(start, end, replacement) edits that turn `orig` into `new` (token-level diff)."""
    ta, tb = _toks(orig), _toks(new)
    off = [0]
    for t in ta:
        off.append(off[-1] + len(t))
    sm = difflib.SequenceMatcher(None, ta, tb, autojunk=False)
    return [(off[i1], off[i2], ''.join(tb[j1:j2])) for tag, i1, i2, j1, j2 in sm.get_opcodes() if tag != 'equal']


def method_at(S, pos):
    best = None
    for x in S.methods:
        sig = max(S.m.rfind(ch, 0, x['decl']) for ch in ';{}') + 1
        if sig <= pos <= x['close'] and (best is None or x['close'] - sig < best[1]):
            best = (x['name'], x['close'] - sig)
    if best:
        return best[0]
    c = S.enclosing_class(pos)
    return '<class %s>' % (c['name'] if c else '?')


def sites(S, regs):
    out = set()
    for s, e, _ in regs:
        out.add(method_at(S, s))
        if e > s:
            out.add(method_at(S, e - 1))
    return out


def overlaps(r1, r2):
    return not (r1[1] < r2[0] or r2[1] < r1[0])


FP_STOP = {'add', 'put', 'get', 'set', 'remove', 'size', 'this', 'null', 'true', 'false', 'println', 'print', 'out',
           'start', 'join', 'run', 'main', 'length', 'equals', 'contains', 'containskey', 'isempty', 'tostring',
           'valueof', 'args', 'e', 'i', 'j', 'k', 'x', 'y', 'int', 'long', 'boolean', 'void', 'public', 'private',
           'static', 'final', 'class', 'super'}


def footprint(S, regs):
    """names a mutation touches: identifiers in its edits + shared fields/locks used by the methods it edits."""
    ids = set()
    for s0, e0, rep in regs:
        ids |= set(re.findall(r'\b[a-z_]\w*', S.m[s0:e0])) | set(re.findall(r'\b[a-z_]\w*', mask_code(rep)))
    fields = set()
    for c in S.classes:
        fields |= class_fields(S, c)
    todo = {method_at(S, pos) for s0, e0, _ in regs for pos in {s0, max(s0, e0 - 1)}}
    reach, stack = set(todo), list(todo)
    known = {x['name'] for x in S.methods}
    while stack:                                   # follow calls: callee bodies touch shared state too
        n = stack.pop()
        for x in S.methods:
            if x['name'] == n:
                for call in re.findall(r'\b(\w+)\s*\(', S.m[x['open']:x['close']]):
                    if call in known and call not in reach:
                        reach.add(call)
                        stack.append(call)
    for x in S.methods:
        if x['name'] in reach:
            ids |= fields & set(re.findall(r'\w+', S.m[x['open']:x['close']]))
    return {t for t in ids if t.lower() not in FP_STOP and t not in KEYWORDS}


def compose(S, code_a, code_b):
    """combine two single-site mutants if their edits AND footprints are independent -> (code, fp_a, fp_b) or None."""
    ra, rb = diff_regions(S.code, code_a), diff_regions(S.code, code_b)
    if any(overlaps(x, y) for x in ra for y in rb):
        return None
    if sites(S, ra) & sites(S, rb):
        return None
    fa, fb = footprint(S, ra), footprint(S, rb)
    if not fa or not fb:                          # independence cannot be shown without a footprint
        return None
    if fa & fb:                                   # they touch the same field/lock/variable: one interacting bug
        return None
    return apply_edits(S.code, ra + rb), fa, fb


# --------------------------------------------------------------------------
# javac check
# --------------------------------------------------------------------------

def javac_cmd(javac):
    if shutil.which(javac):
        return [javac]
    if shutil.which('java'):
        return ['java', '-m', 'jdk.compiler/com.sun.tools.javac.Main']
    sys.exit('no javac found')


def compiles(code, javac):
    d = tempfile.mkdtemp(prefix='mut_')
    try:
        mt = re.search(r'public\s+(?:final\s+|abstract\s+)*class\s+(\w+)', mask_code(code))
        path = os.path.join(d, (mt.group(1) if mt else 'Main') + '.java')
        with open(path, 'w') as f:
            f.write(code)
        r = subprocess.run(javac_cmd(javac) + ['-proc:none', '-nowarn', '-Xlint:none', '-d', d, path],
                           capture_output=True, text=True, timeout=120)
        return r.returncode == 0
    finally:
        shutil.rmtree(d, ignore_errors=True)


# --------------------------------------------------------------------------

def component(name, desc, fp=None):
    m = META[name]
    extra = dict(footprint=sorted(fp)) if fp else {}
    return dict(**extra, mutation=name, bug_type=OPS[name]['bug'], description=desc, bug_class_hint=m['bug_class'],
                fix_hint=dict(fix_type=m['fix'][0], fix_action=m['fix'][1]))


def stage2_pairs(a, data, rng):
    muts, res = json.load(open(a.pairs_from[0])), json.load(open(a.pairs_from[1]))
    if len(muts) != len(res):
        sys.exit('mutants (%d) and JPF results (%d) differ in length' % (len(muts), len(res)))
    pools = defaultdict(list)
    for mu, rr in zip(muts, res):
        if str(rr.get('prompt_id', mu['id'])) != str(mu['id']):
            sys.exit('results are not aligned with mutants at %s' % mu['mutant_id'])
        if (mu['kind'] == 'single' and rr.get('classification') not in ('Pass', 'Termination Error', None)
                and META[mu['mutation']]['bug_class'] != 'no_defect'):
            pools[mu['id']].append((mu['mutation'], mu['description'], mu['code']))
    out = []
    for entry in data:
        S = Src(entry['code'])
        pool = pools.get(entry['id'], [])
        combos = [(x, y) for i, x in enumerate(pool) for y in pool[i + 1:] if x[0] != y[0]]
        rng.shuffle(combos)
        made, seen = 0, {entry['code']}
        for ca, cb in combos:
            if made >= a.pairs_per_program:
                break
            got = compose(S, ca[2], cb[2])
            if got is None or got[0] in seen or (a.javac and not compiles(got[0], a.javac)):
                continue
            new, fa, fb = got
            seen.add(new)
            rec = {k: v for k, v in entry.items() if k != 'code'}
            rec.update(mutant_id='%s-pair-%s+%s-%d' % (entry['id'], ca[0], cb[0], made), kind='pair',
                       mutation='%s+%s' % (ca[0], cb[0]), bug_type='multi', n_bugs=2, jpf_confirmable='yes',
                       jpf_evidence='both components failed JPF individually',
                       expected_jpf='JPF reports whichever bug it reaches first (it stops at the first error)',
                       description=' && '.join([ca[1], cb[1]]),
                       components=[component(ca[0], ca[1], fa), component(cb[0], cb[1], fb)], code=new)
            out.append(rec)
            made += 1
    json.dump(out, open(a.output, 'w'), indent=2)
    print('stage 2: wrote %d two-bug mutants (components JPF-confirmed, footprints disjoint) -> %s' % (len(out), a.output))
    print('programs with a confirmed single:', len(pools), '| programs that got a pair:', len({r['id'] for r in out}))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('input', nargs='?')
    ap.add_argument('-o', '--output', default='mutants_v2.json')
    ap.add_argument('--ops', nargs='+', default=None, help='single-bug operators (default: all except baseline/decoys)')
    ap.add_argument('--new-only', action='store_true', help='run only the new operators (%s)' % ', '.join(NEW_OPS))
    ap.add_argument('--include-weak', action='store_true', help='also run %s (no JPF failure so far)' % ', '.join(WEAK))
    ap.add_argument('--starve-per-op', type=int, default=1, help='max starvation mutants per (program, operator) until JPF-STARVATION is calibrated')
    ap.add_argument('--hog-iters', type=int, default=100, help='yield-loop length of starve_lock_hog (raise it if JPF-STARVATION does not flag)')
    ap.add_argument('--max-per-op', type=int, default=3, help='max single mutants per (program, operator); 0 = unlimited')
    ap.add_argument('--pairs-per-program', type=int, default=2, help='two-bug mutants per program (0 = off)')
    ap.add_argument('--decoys-per-program', type=int, default=1, help='harmless decoy mutants per program (0 = off)')
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--javac', nargs='?', const='javac', default=None,
                    help='compile-check every mutant and drop failures (STRONGLY recommended)')
    ap.add_argument('--keep-original', action='store_true', help='also emit the unmodified programs as clean controls')
    ap.add_argument('--pairs-from', nargs=2, metavar=('MUTANTS_JSON', 'JPF_RESULTS_JSON'),
                    help='STAGE 2: build two-bug mutants ONLY from singles that already failed in JPF (results zipped by order, '
                         'as in mutant_jpf_results.json); each component is then confirmed on its own')
    ap.add_argument('--list-ops', action='store_true')
    a = ap.parse_args()
    HOG_ITERS[0] = a.hog_iters

    if a.list_ops:
        for k, v in OPS.items():
            print('%-30s %-10s jpf=%-12s %s\n%32s expect: %s\n%32s evidence: %s' % (k, v['bug'], META[k]['jpf'], v['doc'], '', v['expected'], '', EVIDENCE.get(k, '')))
        return
    if not a.input:
        ap.error('input json required')
    ops = NEW_OPS if a.new_only else (a.ops or (DEFAULT_OPS + (WEAK if a.include_weak else [])))
    for o in ops:
        if o not in OPS:
            ap.error('unknown op %s (see --list-ops)' % o)
    rng = random.Random(a.seed)
    data = json.load(open(a.input))
    if a.pairs_from:
        return stage2_pairs(a, data, rng)
    out, stats, dropped, per_prog = [], Counter(), Counter(), Counter()

    def ok(code, seen):
        if code in seen:
            return False
        if not balanced(code):
            dropped['unbalanced'] += 1
            return False
        if a.javac and not compiles(code, a.javac):
            dropped['does not compile'] += 1
            return False
        return True

    def emit(entry, mid, kind, mutation, bug, expected, desc, code, comps, jpf):
        rec = {k: v for k, v in entry.items() if k != 'code'}
        rec.update(mutant_id=mid, kind=kind, mutation=mutation, bug_type=bug, n_bugs=len(comps),
                   jpf_confirmable=jpf, jpf_evidence=' | '.join(EVIDENCE.get(c['mutation'], '') for c in comps), expected_jpf=expected, description=desc, components=comps, code=code)
        out.append(rec)
        stats[(kind, mutation)] += 1
        per_prog[entry['id']] += 1

    for entry in data:
        code = entry['code']
        S = Src(code)
        seen = {code}
        if a.keep_original:
            emit(entry, '%s-original' % entry['id'], 'control', 'none', 'none', 'JPF finishes without error',
                 'unmodified program', code, [], 'benign')
        pool = {}
        used = defaultdict(set)
        for name in ops:
            spec = OPS[name]
            cands = spec['fn'](S)
            rng.shuffle(cands)
            cands.sort(key=lambda t: t[0])
            if name in PAIRABLE:
                pool[name] = cands[:4]
            kept = 0
            for pr, desc, new in cands:
                cap = a.starve_per_op if name.startswith('starve_') else a.max_per_op
                if cap and kept >= cap:
                    break
                key = tuple(sorted(sites(S, diff_regions(S.code, new))))
                if key in used[name]:
                    continue                                  # same operator, same method: near-duplicate
                if not ok(new, seen):
                    continue
                used[name].add(key)
                seen.add(new)
                emit(entry, '%s-%s-%d' % (entry['id'], name, kept), 'single', name, spec['bug'], spec['expected'],
                     desc, new, [component(name, desc)], META[name]['jpf'])
                kept += 1

        # ---- two-bug mutants: two different operators at independent sites -------------
        if a.pairs_per_program:
            names = sorted(n for n in pool if pool[n])
            combos = [(x, y) for i, x in enumerate(names) for y in names[i + 1:]]
            rng.shuffle(combos)
            made = 0
            for x, y in combos:
                if made >= a.pairs_per_program:
                    break
                tried = [(ca, cb) for ca in pool[x] for cb in pool[y]]
                rng.shuffle(tried)
                for ca, cb in tried[:6]:
                    got = compose(S, ca[2], cb[2])
                    if got is None:
                        continue
                    new, fa, fb = got
                    if not ok(new, seen):
                        continue
                    seen.add(new)
                    desc = ' && '.join([ca[1], cb[1]])
                    emit(entry, '%s-pair-%s+%s-%d' % (entry['id'], x, y, made), 'pair', '%s+%s' % (x, y), 'multi',
                         'JPF reports whichever bug it reaches first (it stops at the first error): ' +
                         ' | '.join([OPS[x]['expected'], OPS[y]['expected']]),
                         desc, new, [component(x, ca[1], fa), component(y, cb[1], fb)], 'yes')
                    made += 1
                    break

        # ---- decoys ------------------------------------------------------------------
        if a.decoys_per_program:
            dc = []
            for name in DECOYS:
                dc += [(name, d, n) for _, d, n in OPS[name]['fn'](S)]
            rng.shuffle(dc)
            made = 0
            for name, desc, new in dc:
                if made >= a.decoys_per_program:
                    break
                if not ok(new, seen):
                    continue
                seen.add(new)
                emit(entry, '%s-%s-%d' % (entry['id'], name, made), 'decoy', name, 'none',
                     OPS[name]['expected'], desc, new, [component(name, desc)], 'benign')
                made += 1

    json.dump(out, open(a.output, 'w'), indent=2)
    print('wrote %d mutants from %d programs -> %s' % (len(out), len(data), a.output))
    for (kind, name), n in sorted(stats.items()):
        print('  %-8s %-45s %4d' % (kind, name, n))
    empty = [e['id'] for e in data if per_prog[e['id']] == 0]
    print('programs with >=1 mutant: %d/%d' % (len(data) - len(empty), len(data)))
    if empty:
        print('programs with NO mutant (nothing to hit; use as clean controls):', empty)
    if dropped:
        print('dropped:', dict(dropped))
    if not a.javac:
        print('note: mutants were NOT compile-checked (pass --javac to check).')


if __name__ == '__main__':
    main()