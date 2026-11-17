#!/usr/bin/env python3
"""
mutate_concurrency.py -- inject concurrency bugs (races, deadlocks, monitor
misuse, ...) into correct Java programs stored in a JSON list.

Input : [{"id": ..., "code": "..."}, ...]            (extra keys are kept)
Output: [{"id": <orig id>, "mutant_id": "73-lock_order_inversion_methods-0",
          "mutation": ..., "bug_type": "race|deadlock|exception|semantic",
          "expected_jpf": ..., "description": ..., "code": <mutated code>}, ...]

Usage:
  python mutate_concurrency.py codes.json -o mutants.json
  python mutate_concurrency.py codes.json -o mutants.json --javac   # drop mutants that don't compile
  python mutate_concurrency.py --list-ops
  python mutate_concurrency.py codes.json --ops rm_sync_one lock_order_inversion --max-per-op 5

Every mutant is produced by ONE mutation operator applied at ONE site (or one
coupled pair of sites for lock-order inversion), so a JPF failure can be
attributed to a single, known change.
"""
import argparse
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


DEFAULT_OPS = [k for k in OPS if k not in ('rm_sync_all', 'nonatomic_cas')]


# --------------------------------------------------------------------------
# optional compile check (needs a JDK on PATH; use the same Java as JPF, i.e. 8)
# --------------------------------------------------------------------------

def javac_cmd(javac):
    if shutil.which(javac):
        return [javac]
    if shutil.which('java'):                      # JRE that still ships the compiler module
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

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('input', nargs='?')
    ap.add_argument('-o', '--output', default='mutants.json')
    ap.add_argument('--ops', nargs='+', default=None, help='operators to run (default: all except baseline/semantic)')
    ap.add_argument('--max-per-op', type=int, default=3,
                    help='max mutants per (program, operator); 0 = unlimited (default 3)')
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--javac', nargs='?', const='javac', default=None,
                    help='compile-check each mutant with this javac and drop failures')
    ap.add_argument('--keep-original', action='store_true', help='also emit the unmodified programs')
    ap.add_argument('--list-ops', action='store_true')
    a = ap.parse_args()

    if a.list_ops:
        for k, v in OPS.items():
            flag = '' if k in DEFAULT_OPS else '  [off by default]'
            print('%-30s %-9s %s%s\n%32s expect: %s' % (k, v['bug'], v['doc'], flag, '', v['expected']))
        return
    if not a.input:
        ap.error('input json required')

    ops = a.ops or DEFAULT_OPS
    for o in ops:
        if o not in OPS:
            ap.error('unknown op %s (see --list-ops)' % o)
    rng = random.Random(a.seed)
    data = json.load(open(a.input))
    out, stats, dropped = [], Counter(), Counter()

    for entry in data:
        code = entry['code']
        S = Src(code)
        seen = {code}
        if a.keep_original:
            out.append(dict(entry, mutant_id='%s-original' % entry['id'], mutation='none', bug_type='none'))
        for name in ops:
            spec = OPS[name]
            cands = spec['fn'](S)
            rng.shuffle(cands)
            cands.sort(key=lambda t: t[0])            # stable: priority first, random within
            kept = 0
            for pr, desc, new in cands:
                if a.max_per_op and kept >= a.max_per_op:
                    break
                if new in seen:
                    continue
                if not balanced(new):
                    dropped['unbalanced'] += 1
                    continue
                if a.javac and not compiles(new, a.javac):
                    dropped['does not compile'] += 1
                    continue
                seen.add(new)
                rec = {k: v for k, v in entry.items() if k != 'code'}
                rec.update(mutant_id='%s-%s-%d' % (entry['id'], name, kept), mutation=name,
                           bug_type=spec['bug'], expected_jpf=spec['expected'],
                           description=desc, code=new)
                out.append(rec)
                stats[(name, spec['bug'])] += 1
                kept += 1

    json.dump(out, open(a.output, 'w'), indent=2)
    print('wrote %d mutants from %d programs -> %s' % (len(out), len(data), a.output))
    for (name, bug), n in sorted(stats.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        print('  %-30s %-9s %4d' % (name, bug, n))
    by_bug = Counter()
    for (name, bug), n in stats.items():
        by_bug[bug] += n
    print('by bug type:', dict(by_bug))
    covered = len({r['id'] for r in out})
    print('programs with >=1 mutant: %d/%d' % (covered, len(data)))
    if dropped:
        print('dropped:', dict(dropped))
    if not a.javac:
        print('note: mutants were NOT compile-checked (pass --javac to check).')


if __name__ == '__main__':
    main()