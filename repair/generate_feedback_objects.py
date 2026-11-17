# #!/usr/bin/env python3
# """
# Parse merged JPF results (merged_jpf_results.json) into structured
# "feedback objects" suitable for a repair-prompt: {error_type, resource,
# exception_class, message, threads_involved, notes}.

# No LLM needed -- JPF/javac output is templated enough for regex parsing.
# Where the underlying log is truncated (JPF's own report cuts messages
# short with "..."), we say so explicitly in `truncated` rather than
# guessing the rest.

# NOTE on Uncaught Exception quality: as of this version, every jpf_result
# string for this category in the source data is truncated to exactly 110
# characters by the upstream harness (confirmed empirically -- not JPF's own
# limit). The parser below is written to make full use of the untruncated
# text once you fix that upstream capture step (grab the full text between
# the "results" and "statistics" section headers, including any stack trace
# JPF prints), without needing any changes here -- it degrades gracefully
# today and gets strictly better once richer input arrives.

# Usage:
#   python3 generate_feedback_objects.py merged_jpf_results.json feedback_objects.json [qwen_code.json]

#   The optional third argument is a code-lookup file (id -> code), e.g.
#   qwen_all.json, used only to flag likely reflection-related exceptions
#   (NoSuchFieldException/NoSuchMethodException) by checking whether the
#   buggy code actually uses reflection APIs.
# """
# import json
# import re
# import sys

# # Frame prefixes that belong to the JDK / JPF itself, not to generated code.
# _NON_USER_FRAME_PREFIXES = (
#     'java.', 'javax.', 'jdk.', 'sun.', 'com.sun.',
#     'gov.nasa.jpf.',
# )

# _REFLECTION_API_PATTERN = re.compile(
#     r'\.getDeclaredField\(|\.getField\(|\.getDeclaredMethod\(|\.getMethod\(|'
#     r'Class\.forName\(|\.newInstance\(|\.setAccessible\('
# )


# def parse_compilation_error(entry):
#     """javac output: repeated blocks of 'file:line: error: message'."""
#     text = entry.get('compile_error', '') or ''
#     errors = []
#     # javac format: <path>:<line>: error: <message>
#     for m in re.finditer(r'^(.*?):(\d+):\s*error:\s*(.+)$', text, re.MULTILINE):
#         errors.append({
#             'file': m.group(1).strip(),
#             'line': int(m.group(2)),
#             'message': m.group(3).strip(),
#         })
#     if not errors:
#         # fallback: couldn't match the usual javac shape, keep raw snippet
#         errors.append({'file': None, 'line': None, 'message': text[:300]})
#     return {
#         'error_type': 'Compilation Errors',
#         'errors': errors,
#         'error_count': len(errors),
#     }


# def parse_race_condition(entry):
#     """PreciseRaceDetector: error #1: ... "race for field Class@hash.field ...""" 
#     text = entry.get('jpf_result', '') or ''
#     m = re.search(r'race for field ([\w$.]+)@\w+\.(\w+)', text)
#     class_name, field_name = (m.group(1), m.group(2)) if m else (None, None)
#     truncated = text.rstrip().endswith('...\"') or text.rstrip().endswith('...')
#     return {
#         'error_type': 'Race Condition',
#         'racing_class': class_name,
#         'racing_field': field_name,
#         'raw_message': text,
#         'truncated': truncated,
#         'notes': (
#             "JPF's PreciseRaceDetector flagged this field as accessed by "
#             "multiple threads without a happens-before ordering between "
#             "them (missing/incorrect synchronization)."
#         ),
#     }


# def _extract_stack_frames(text):
#     """Find any 'at pkg.Class.method(File.java:NN)' lines in the full log
#     and split into user-code frames vs JDK/JPF-internal frames. Returns
#     (user_frames, internal_frame_count). Empty today for most entries
#     since the current harness doesn't capture a trace at all -- becomes
#     useful automatically once the upstream capture is fixed."""
#     frames = re.findall(r'^\s*at\s+([\w.$]+)\(([^)]*)\)\s*$', text, re.MULTILINE)
#     user_frames, internal_count = [], 0
#     for cls_method, location in frames:
#         if cls_method.startswith(_NON_USER_FRAME_PREFIXES):
#             internal_count += 1
#         else:
#             user_frames.append(f'{cls_method}({location})')
#     return user_frames, internal_count


# def _max_depth_at_failure(jpf_details):
#     m = re.search(r'maxDepth=(\d+)', jpf_details or '')
#     return int(m.group(1)) if m else None


# def parse_uncaught_exception(entry, code_lookup=None):
#     """NoUncaughtExceptionsProperty: "<ExceptionClass>[: message]..." """
#     result_text = entry.get('jpf_result', '') or ''
#     details_text = entry.get('jpf_details', '') or ''

#     m = re.search(r'"((?:[\w.]+\.)?(\w*(?:Exception|Error)))(?::\s*(.*?))?"?\s*$', result_text)
#     if m:
#         exc_class = m.group(1)
#         message = (m.group(3) or '').rstrip('.')
#     else:
#         exc_class, message = None, None

#     # Handle the "wrapped" case: java.lang.Error: java.lang.NoSuchFieldException: ...
#     root_cause = None
#     if message:
#         inner = re.match(r'^((?:[\w.]+\.)?\w+(?:Exception|Error))\b:?\s*(.*)', message)
#         if inner:
#             root_cause = inner.group(1)
#             message = inner.group(2) or message

#     exception_class = root_cause or exc_class
#     truncated = result_text.rstrip().endswith('...\"') or result_text.rstrip().endswith('...')

#     # Stack trace: empty today for almost all entries (the current harness
#     # doesn't capture one), but this scans the full jpf_details every time,
#     # so it starts working the moment richer logs are fed in -- no code
#     # changes needed here later.
#     user_frames, internal_frame_count = _extract_stack_frames(details_text)

#     # maxDepth as a proxy for "fails immediately" vs "only under a specific
#     # deep interleaving" -- cheap, already-available signal, no re-run needed.
#     max_depth = _max_depth_at_failure(details_text)
#     depth_note = None
#     if max_depth is not None:
#         if max_depth <= 2:
#             depth_note = (
#                 f"Failed almost immediately (maxDepth={max_depth}) -- likely an "
#                 f"initialization-time bug, not something that depends on a rare "
#                 f"thread interleaving."
#             )
#         else:
#             depth_note = (
#                 f"Failed after {max_depth} explored steps -- may only surface "
#                 f"under a specific thread interleaving rather than every run."
#             )

#     # Reflection heuristic: strong exception-class signal on its own, backed
#     # up by scanning the actual buggy code for reflection API calls when
#     # we have it (currently only available for qwen via qwen_all.json).
#     reflection_exception_classes = {
#         'NoSuchFieldException', 'NoSuchMethodException',
#         'IllegalAccessException', 'IllegalArgumentException',
#     }
#     exc_suggests_reflection = bool(exception_class) and any(
#         exception_class.endswith(c) for c in reflection_exception_classes
#     )
#     code = (code_lookup or {}).get(entry.get('id'))
#     code_uses_reflection = bool(code and _REFLECTION_API_PATTERN.search(code))
#     reflection_suspected = exc_suggests_reflection and (
#         code_uses_reflection if code is not None else None
#     )

#     notes = [
#         "This exception was thrown during at least one explored thread "
#         "interleaving and was never caught."
#     ]
#     if truncated and not user_frames:
#         notes.append(
#             "The captured message/log is truncated and contains no stack "
#             "trace -- exact source location is unknown from this run. "
#             "Re-run JPF with full (untruncated) report capture for this id "
#             "to get an actionable location."
#         )
#     if depth_note:
#         notes.append(depth_note)
#     if reflection_suspected is True:
#         notes.append(
#             "This looks like a reflection-related failure (exception class "
#             f"'{exception_class}' plus reflection API calls found in the "
#             "generated code). The likely fix is to remove the reflection "
#             "usage entirely and access the field/method directly, rather "
#             "than trying to correct the looked-up name."
#         )
#     elif reflection_suspected is None and exc_suggests_reflection:
#         notes.append(
#             "Exception class suggests a reflection-related failure, but the "
#             "generated code wasn't available to confirm reflection API "
#             "usage (pass a code-lookup file to check)."
#         )

#     return {
#         'error_type': 'Uncaught Exception',
#         'exception_class': exception_class,
#         'wrapper_class': exc_class if root_cause else None,
#         'message': message,
#         'truncated': truncated,
#         'stack_trace_user_frames': user_frames,
#         'stack_trace_internal_frame_count': internal_frame_count,
#         'max_depth_at_failure': max_depth,
#         'reflection_suspected': reflection_suspected,
#         'notes': ' '.join(notes),
#     }


# def parse_termination_error(entry):
#     """JPF crashed internally (or hit its resource/time bound) mid-search."""
#     details = entry.get('jpf_details', '') or ''
#     result = entry.get('jpf_result', '') or ''
#     return {
#         'error_type': 'Termination Error',
#         'raw_tail_of_log': details[-500:] if details else result[-500:],
#         'notes': (
#             "JPF terminated abnormally while exploring this program rather "
#             "than completing its search or reporting a specific property "
#             "violation. This can mean the model checker ran out of a "
#             "resource bound (states/time/depth), or it can mask a genuine "
#             "concurrency defect (e.g. a livelock) that JPF cannot name "
#             "directly. Treat as inconclusive rather than a confirmed "
#             "specific bug; do not assume the code is otherwise correct."
#         ),
#     }


# # Parsers that don't need the code-lookup take just `entry`; the uncaught-
# # exception parser optionally takes `code_lookup` too. Wrapped below so
# # DISPATCH stays a uniform `entry -> dict` interface for callers.
# DISPATCH_SIMPLE = {
#     'Compilation Errors': parse_compilation_error,
#     'Race Condition': parse_race_condition,
#     'Termination Error': parse_termination_error,
# }


# def build_feedback_object(entry, code_lookup=None):
#     cls = entry.get('classification')
#     if cls == 'Pass' or cls is None:
#         return None
#     base = {
#         'id': entry['id'],
#         'model': entry['model'],
#         'topic': entry.get('topic', ''),
#         'classification': cls,
#     }
#     if cls == 'Uncaught Exception':
#         base['feedback'] = parse_uncaught_exception(entry, code_lookup=code_lookup)
#     elif cls in DISPATCH_SIMPLE:
#         base['feedback'] = DISPATCH_SIMPLE[cls](entry)
#     else:
#         # Unknown/unhandled category (e.g. Deadlock, Starvation, if present
#         # in your data later) -- fall back to raw text so nothing is silently
#         # dropped; extend DISPATCH with a dedicated parser when you hit this.
#         base['feedback'] = {
#             'error_type': cls,
#             'raw_jpf_result': entry.get('jpf_result', ''),
#             'notes': 'No dedicated parser yet for this error_type -- add one to DISPATCH.',
#         }
#     return base


# def main(in_path, out_path, code_lookup_path=None):
#     with open(in_path) as f:
#         data = json.load(f)

#     code_lookup = None
#     if code_lookup_path:
#         with open(code_lookup_path) as f:
#             code_entries = json.load(f)
#         code_lookup = {x['id']: x['code'] for x in code_entries if 'id' in x and 'code' in x}

#     feedback_objects = []
#     for entry in data:
#         obj = build_feedback_object(entry, code_lookup=code_lookup)
#         if obj is not None:
#             feedback_objects.append(obj)

#     with open(out_path, 'w') as f:
#         json.dump(feedback_objects, f, indent=2)

#     print(f'Parsed {len(data)} entries -> {len(feedback_objects)} feedback objects '
#           f'(non-Pass) written to {out_path}')

#     from collections import Counter
#     print(Counter(o['classification'] for o in feedback_objects))

#     n_reflect = sum(
#         1 for o in feedback_objects
#         if o['classification'] == 'Uncaught Exception'
#         and o['feedback'].get('reflection_suspected')
#     )
#     if n_reflect:
#         print(f'{n_reflect} Uncaught Exception case(s) flagged as reflection-related.')


# if __name__ == '__main__':
#     in_path = sys.argv[1] if len(sys.argv) > 1 else 'merged_jpf_results.json'
#     out_path = sys.argv[2] if len(sys.argv) > 2 else 'feedback_objects.json'
#     code_lookup_path = sys.argv[3] if len(sys.argv) > 3 else None
#     main(in_path, out_path, code_lookup_path)

#!/usr/bin/env python3
"""
Parse merged JPF results into structured "feedback objects" suitable for a
repair-prompt: {error_type, resource, exception_class, message,
threads_involved, notes}.

No LLM needed -- JPF/javac output is templated enough for regex parsing.

Input field names: this accepts both the original merged_jpf_results.json
shape ("id", "model") and the failed_repaired_results.json shape
("prompt_id", "llm") -- see _entry_id/_entry_model.

NOTE on stack traces: newer harness output (e.g. claude_failed_repaired_
results.json / qwen_failed_repaired_results.json) includes a
"===== full exception (untruncated) =====" section in jpf_details with the
complete Java exception chain and real stack frames, and complete
per-thread access info for races. Where that section is present, this
parser extracts full structured stack traces. Where it's absent (older,
still-truncated captures), it degrades gracefully to the old truncated-
summary heuristics and says so explicitly via `truncated` / a note,
rather than guessing the rest.
"""
import json
import re
import sys

# Frame prefixes that belong to the JDK / JPF itself, not to generated code.
_NON_USER_FRAME_PREFIXES = (
    'java.', 'javax.', 'jdk.', 'sun.', 'com.sun.',
    'gov.nasa.jpf.',
)

_REFLECTION_API_PATTERN = re.compile(
    r'\.getDeclaredField\(|\.getField\(|\.getDeclaredMethod\(|\.getMethod\(|'
    r'Class\.forName\(|\.newInstance\(|\.setAccessible\('
)

# Matches a stack frame line, with or without a leading thread name (JPF's
# race detector prefixes frames with the thread, e.g.
# "  pool-1-thread-1 at Class.method(File.java:21)"), and with or without a
# parenthesized location (lambda frames sometimes have neither, e.g.
# "at Foo$$Lambda$0.run").
_FRAME_RE = re.compile(
    r'^\s*(?:(?P<thread>[\w$.-]+)\s+)?at\s+(?P<method>[\w.$<>]+)'
    r'(?:\((?P<location>[^)]*)\))?\s*$',
    re.MULTILINE,
)

# The two-line shape PreciseRaceDetector uses per racing thread:
#   <thread> at Class.method(File.java:NN)
#       "source line"  READ|WRITE: putfield/getfield Class.field
_RACE_ACCESS_RE = re.compile(
    r'^\s*(?P<thread>[\w$.-]+)\s+at\s+(?P<location>[\w.$<>]+(?:\([^)]*\))?)\s*\n'
    r'\s*"(?P<source_line>[^"]*)"\s+(?P<access>READ|WRITE):\s*(?P<opcode>\S+)',
    re.MULTILINE,
)

# Grabs the untruncated exception block the newer harness captures, cutting
# it off before the "====== results" / "Unique logical threads" tail so we
# don't run frame/exception regexes over statistics noise.
_UNTRUNCATED_RE = re.compile(
    r'full exception \(untruncated\)\s*=====\s*\n(.*?)'
    r'(?:\n=+\s*results\b|\nUnique logical threads|\Z)',
    re.DOTALL,
)

# One line of an exception chain: "pkg.SomeException: message text".
# \w* (not \w+) before the Exception|Error suffix -- a bare wrapper class
# like "java.lang.Error" has nothing left in its final token once the
# "java."/"lang." dot-segments are consumed, so the suffix must be allowed
# to stand alone.
_EXC_LINE_RE = re.compile(r'^((?:[\w$]+\.)*\w*(?:Exception|Error))\s*:?\s*(.*)$')


def _entry_id(entry):
    """merged_jpf_results.json uses 'id'; failed_repaired_results.json uses
    'prompt_id'. Accept either."""
    return entry.get('id', entry.get('prompt_id'))


def _entry_model(entry):
    """merged_jpf_results.json uses 'model'; failed_repaired_results.json
    uses 'llm'. Accept either."""
    return entry.get('model', entry.get('llm'))


def _untruncated_block(details_text):
    """Return the text of the harness's "full exception (untruncated)"
    section if present, else None."""
    if not details_text:
        return None
    m = _UNTRUNCATED_RE.search(details_text)
    return m.group(1) if m else None


def _extract_stack_frames(text):
    """Find all 'at Class.method(File.java:NN)'-shaped frames anywhere in
    the given text (thread-prefixed or not, parenthesized or not). Returns
    (user_frames, internal_frame_count); each user frame is a display
    string, thread-tagged when a thread name was present."""
    if not text:
        return [], 0
    user_frames, internal_count = [], 0
    for m in _FRAME_RE.finditer(text):
        method = m.group('method')
        location = m.group('location')
        thread = m.group('thread')
        display = f'{method}({location})' if location else method
        if thread:
            display = f'[{thread}] {display}'
        if method.startswith(_NON_USER_FRAME_PREFIXES):
            internal_count += 1
        else:
            user_frames.append(display)
    return user_frames, internal_count


def _dedupe(items):
    seen, out = set(), []
    for i in items:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


def _parse_exception_chain(text):
    """Parse a Java-style exception + 'Caused by:' chain into a list of
    {exception_class, message, stack_trace_user_frames,
    stack_trace_internal_frame_count}, one entry per link in the chain,
    outermost first."""
    if not text:
        return []
    segments = re.split(r'\nCaused by:\s*', text)
    chain = []
    for seg in segments:
        cls, msg = None, ''
        for line in seg.splitlines():
            line = line.strip()
            if not line or line.startswith('at '):
                continue
            m = _EXC_LINE_RE.match(line)
            if m:
                cls, msg = m.group(1), m.group(2).strip()
                break
        if cls is None:
            continue
        frames, internal_count = _extract_stack_frames(seg)
        chain.append({
            'exception_class': cls,
            'message': msg or None,
            'stack_trace_user_frames': frames,
            'stack_trace_internal_frame_count': internal_count,
        })
    return chain


def parse_compilation_error(entry):
    """javac output: repeated blocks of 'file:line: error: message'."""
    text = entry.get('compile_error', '') or ''
    errors = []
    for m in re.finditer(r'^(.*?):(\d+):\s*error:\s*(.+)$', text, re.MULTILINE):
        errors.append({
            'file': m.group(1).strip(),
            'line': int(m.group(2)),
            'message': m.group(3).strip(),
        })
    if not errors:
        errors.append({'file': None, 'line': None, 'message': text[:300]})
    return {
        'error_type': 'Compilation Errors',
        'errors': errors,
        'error_count': len(errors),
        # No program ever ran, so there is no runtime stack trace -- the
        # key is still present (empty) for schema consistency across all
        # feedback object types.
        'stack_trace_user_frames': [],
        'stack_trace_internal_frame_count': 0,
        'notes': 'Not applicable -- compilation failed before the program could run.',
    }


def parse_race_condition(entry):
    """PreciseRaceDetector: error #1: ... "race for field Class@hash.field ...".

    PreciseRaceDetector doesn't report a call stack; it reports exactly the
    two conflicting accesses (one per thread), each with its own source
    location. That's the trace-equivalent for this category, captured in
    `racing_accesses`, and flattened into `stack_trace_user_frames` for
    schema consistency with the other categories."""
    text = entry.get('jpf_result', '') or ''
    details_text = entry.get('jpf_details', '') or ''
    full_block = _untruncated_block(details_text) or details_text

    m = (re.search(r'race for field ([\w$.]+)@\w+\.(\w+)', full_block)
         or re.search(r'race for field ([\w$.]+)@\w+\.(\w+)', text))
    class_name, field_name = (m.group(1), m.group(2)) if m else (None, None)

    racing_accesses = [
        {
            'thread': am.group('thread'),
            'location': am.group('location'),
            'access_type': am.group('access'),
            'source_line': am.group('source_line'),
        }
        for am in _RACE_ACCESS_RE.finditer(full_block)
    ]
    stack_trace_user_frames = [
        f"[{a['thread']}] {a['location']}" for a in racing_accesses
    ]

    truncated = text.rstrip().endswith('...\"') or text.rstrip().endswith('...')

    notes = [
        "JPF's PreciseRaceDetector flagged this field as accessed by "
        "multiple threads without a happens-before ordering between "
        "them (missing/incorrect synchronization)."
    ]
    if not racing_accesses:
        notes.append(
            "The captured log has no per-thread access detail (older or "
            "still-truncated capture) -- exact racing locations are "
            "unknown from this run."
        )

    return {
        'error_type': 'Race Condition',
        'racing_class': class_name,
        'racing_field': field_name,
        'raw_message': text,
        'truncated': truncated,
        'racing_accesses': racing_accesses,
        'stack_trace_user_frames': stack_trace_user_frames,
        'stack_trace_internal_frame_count': 0,
        'notes': ' '.join(notes),
    }


def parse_uncaught_exception(entry, code_lookup=None):
    """NoUncaughtExceptionsProperty: "<ExceptionClass>[: message]..."

    Prefers the harness's untruncated exception block when present (full
    Java exception + 'Caused by:' chain with real stack frames per link);
    falls back to the old truncated-summary regex on jpf_result when it
    isn't."""
    result_text = entry.get('jpf_result', '') or ''
    details_text = entry.get('jpf_details', '') or ''
    full_block = _untruncated_block(details_text)

    if full_block:
        # First line is the JPF property name (e.g.
        # "gov.nasa.jpf.vm.NoUncaughtExceptionsProperty"), not part of the
        # Java exception chain itself -- skip it.
        lines = full_block.splitlines()
        chain = _parse_exception_chain('\n'.join(lines[1:]) if lines else '')
    else:
        chain = []

    if chain:
        exception_class = chain[-1]['exception_class']
        wrapper_class = chain[0]['exception_class'] if len(chain) > 1 else None
        message = chain[-1]['message']
        user_frames = _dedupe(
            f for link in chain for f in link['stack_trace_user_frames']
        )
        internal_frame_count = sum(
            link['stack_trace_internal_frame_count'] for link in chain
        )
        truncated = False  # the untruncated block gave us everything
    else:
        # Fall back to the old truncated-summary path, so this still works
        # unchanged on older captures that never got a "full exception
        # (untruncated)" section.
        m = re.search(r'"((?:[\w.]+\.)?(\w*(?:Exception|Error)))(?::\s*(.*?))?"?\s*$', result_text)
        if m:
            exc_class = m.group(1)
            message = (m.group(3) or '').rstrip('.')
        else:
            exc_class, message = None, None
        root_cause = None
        if message:
            inner = re.match(r'^((?:[\w.]+\.)?\w+(?:Exception|Error))\b:?\s*(.*)', message)
            if inner:
                root_cause = inner.group(1)
                message = inner.group(2) or message
        exception_class = root_cause or exc_class
        wrapper_class = exc_class if root_cause else None
        user_frames, internal_frame_count = _extract_stack_frames(details_text)
        truncated = result_text.rstrip().endswith('...\"') or result_text.rstrip().endswith('...')

    max_depth = None
    dm = re.search(r'maxDepth=(\d+)', details_text or '')
    if dm:
        max_depth = int(dm.group(1))
    depth_note = None
    if max_depth is not None:
        if max_depth <= 2:
            depth_note = (
                f"Failed almost immediately (maxDepth={max_depth}) -- likely an "
                f"initialization-time bug, not something that depends on a rare "
                f"thread interleaving."
            )
        else:
            depth_note = (
                f"Failed after {max_depth} explored steps -- may only surface "
                f"under a specific thread interleaving rather than every run."
            )

    reflection_exception_classes = {
        'NoSuchFieldException', 'NoSuchMethodException',
        'IllegalAccessException', 'IllegalArgumentException',
    }
    exc_suggests_reflection = bool(exception_class) and any(
        exception_class.endswith(c) for c in reflection_exception_classes
    )
    code = (code_lookup or {}).get(_entry_id(entry))
    code_uses_reflection = bool(code and _REFLECTION_API_PATTERN.search(code))
    reflection_suspected = exc_suggests_reflection and (
        code_uses_reflection if code is not None else None
    )

    notes = [
        "This exception was thrown during at least one explored thread "
        "interleaving and was never caught."
    ]
    if chain:
        if len(chain) > 1:
            notes.append(
                f"Full exception chain recovered: {wrapper_class} wrapping "
                f"{exception_class}, with a real stack trace for each link."
            )
        else:
            notes.append("Full exception text and stack trace were recovered for this run.")
    elif truncated and not user_frames:
        notes.append(
            "The captured message/log is truncated and contains no stack "
            "trace -- exact source location is unknown from this run. "
            "Re-run JPF with full (untruncated) report capture for this id "
            "to get an actionable location."
        )
    if depth_note:
        notes.append(depth_note)
    if reflection_suspected is True:
        notes.append(
            "This looks like a reflection-related failure (exception class "
            f"'{exception_class}' plus reflection API calls found in the "
            "generated code). The likely fix is to remove the reflection "
            "usage entirely and access the field/method directly, rather "
            "than trying to correct the looked-up name."
        )
    elif reflection_suspected is None and exc_suggests_reflection:
        notes.append(
            "Exception class suggests a reflection-related failure, but the "
            "generated code wasn't available to confirm reflection API "
            "usage (pass a code-lookup file to check)."
        )

    return {
        'error_type': 'Uncaught Exception',
        'exception_class': exception_class,
        'wrapper_class': wrapper_class,
        'message': message,
        'truncated': truncated,
        'exception_chain': chain,
        'stack_trace_user_frames': user_frames,
        'stack_trace_internal_frame_count': internal_frame_count,
        'max_depth_at_failure': max_depth,
        'reflection_suspected': reflection_suspected,
        'notes': ' '.join(notes),
    }


def parse_termination_error(entry):
    """JPF crashed internally (or hit its resource/time bound) mid-search."""
    details = entry.get('jpf_details', '') or ''
    result = entry.get('jpf_result', '') or ''
    combined = (result + '\n' + details) if details else result
    user_frames, internal_frame_count = _extract_stack_frames(combined)
    user_frames = _dedupe(user_frames)

    notes = [
        "JPF terminated abnormally while exploring this program rather "
        "than completing its search or reporting a specific property "
        "violation. This can mean the model checker ran out of a "
        "resource bound (states/time/depth), or it can mask a genuine "
        "concurrency defect (e.g. a livelock) that JPF cannot name "
        "directly. Treat as inconclusive rather than a confirmed "
        "specific bug; do not assume the code is otherwise correct."
    ]
    if not user_frames and internal_frame_count:
        notes.append(
            "The termination trace is entirely inside JPF/JVM internals "
            "with no user-code frames, consistent with a resource-bound "
            "or search-engine-level termination rather than a bug "
            "reachable in the generated code."
        )

    return {
        'error_type': 'Termination Error',
        'raw_tail_of_log': details[-500:] if details else result[-500:],
        'stack_trace_user_frames': user_frames,
        'stack_trace_internal_frame_count': internal_frame_count,
        'notes': ' '.join(notes),
    }


DISPATCH_SIMPLE = {
    'Compilation Errors': parse_compilation_error,
    'Race Condition': parse_race_condition,
    'Termination Error': parse_termination_error,
}


def build_feedback_object(entry, code_lookup=None):
    cls = entry.get('classification')
    if cls == 'Pass' or cls is None:
        return None
    base = {
        'id': _entry_id(entry),
        'model': _entry_model(entry),
        'topic': entry.get('topic', ''),
        'classification': cls,
    }
    if cls == 'Uncaught Exception':
        base['feedback'] = parse_uncaught_exception(entry, code_lookup=code_lookup)
    elif cls in DISPATCH_SIMPLE:
        base['feedback'] = DISPATCH_SIMPLE[cls](entry)
    else:
        base['feedback'] = {
            'error_type': cls,
            'raw_jpf_result': entry.get('jpf_result', ''),
            'stack_trace_user_frames': [],
            'stack_trace_internal_frame_count': 0,
            'notes': 'No dedicated parser yet for this error_type -- add one to DISPATCH.',
        }
    return base


def main(in_path, out_path, code_lookup_path=None):
    with open(in_path) as f:
        data = json.load(f)

    code_lookup = None
    if code_lookup_path:
        with open(code_lookup_path) as f:
            code_entries = json.load(f)
        code_lookup = {x['id']: x['code'] for x in code_entries if 'id' in x and 'code' in x}

    feedback_objects = []
    for entry in data:
        obj = build_feedback_object(entry, code_lookup=code_lookup)
        if obj is not None:
            feedback_objects.append(obj)

    with open(out_path, 'w') as f:
        json.dump(feedback_objects, f, indent=2)

    print(f'Parsed {len(data)} entries -> {len(feedback_objects)} feedback objects '
          f'(non-Pass) written to {out_path}')

    from collections import Counter
    print(Counter(o['classification'] for o in feedback_objects))

    n_reflect = sum(
        1 for o in feedback_objects
        if o['classification'] == 'Uncaught Exception'
        and o['feedback'].get('reflection_suspected')
    )
    if n_reflect:
        print(f'{n_reflect} Uncaught Exception case(s) flagged as reflection-related.')

    n_with_trace = sum(
        1 for o in feedback_objects
        if o['feedback'].get('stack_trace_user_frames')
    )
    print(f'{n_with_trace}/{len(feedback_objects)} feedback objects have a non-empty user-code stack trace.')


if __name__ == '__main__':
    in_path = sys.argv[1] if len(sys.argv) > 1 else 'merged_jpf_results.json'
    out_path = sys.argv[2] if len(sys.argv) > 2 else 'feedback_objects.json'
    code_lookup_path = sys.argv[3] if len(sys.argv) > 3 else None
    main(in_path, out_path, code_lookup_path)