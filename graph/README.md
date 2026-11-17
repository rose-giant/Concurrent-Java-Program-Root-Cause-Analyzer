# JPF counterexample + state-graph toolkit for concurrency RCA

Goal: for every failing program, get (1) the exact thread interleaving JPF used to reach the
violation, with real source line numbers, and (2) the explored state graph. Then turn both into
a compact evidence document you can give to the LLM (or use to check its root cause).

## Prerequisites
- Java 8 JDK (for `javac` and JPF) and a built jpf-core (`build/jpf.jar`, `build/RunJPF.jar`)
- Your `~/.jpf/site.properties` already working (you ran JPF for the dataset)
- Your race-detector and starvation-listener classes
- The JSON file(s) that hold the Java **code** (e.g. `mutants.json`, `codes.json`).
  `codes_jpf_results.json` has no code field, only results.
- python3 (no extra packages). Graphviz `dot` is optional.

## Steps (run from this folder)

0. Edit `base.jpf`: paste in the lines from the .jpf you used for the dataset
   (listeners, native_classpath, starvation bound), minus `target` and `classpath`.

1. Build the listener (once):
   ```
   JAVA8_HOME=/path/to/jdk8 ./build_listener.sh /path/to/jpf-core
   ```

2. Extract and format the programs (fixes the "every line is 1" problem):
   ```
   python3 01_extract_format.py --results codes_jpf_results.json \
       --code-json mutants.json --code-json codes.json --work work
   ```
   Add `--include-pass` if you also want passing programs (good for original-vs-mutant comparison).

3. Smoke test on ONE case first:
   ```
   python3 02_run_jpf.py --work work --jpf-core /path/to/jpf-core \
       --java8-home /path/to/jdk8 --ids 1-rm_sync_block-0 --render
   python3 03_make_context.py --work work
   cat work/1-rm_sync_block-0/context.md
   ```
   Check that `work/1-rm_sync_block-0/jpf_out/trace.json` exists and the lines in
   `context.md` match the formatted source.

4. Run everything:
   ```
   python3 02_run_jpf.py --work work --jpf-core /path/to/jpf-core \
       --java8-home /path/to/jdk8 -j 4 --timeout 300
   python3 03_make_context.py --work work
   ```

## Output per case (`work/<id>/`)
- `src/<Class>.java`   formatted program
- `jpf.log`            full JPF output
- `jpf_out/trace.json` raw counterexample (user-code instructions per thread)
- `jpf_out/graph.dot`  / `graph.json` / `graph.svg`   explored state graph
- `context.md`         evidence document: violation, numbered source, relevant interleaving,
                       schedule, lockset table + race hint, lock-order edges + cycle hint
- `work/INDEX_context.csv`, `work/run_summary.csv`

## Using it for RCA
Paste `context.md` into the "JPF evidence" part of your RCA prompt as a new condition
(for example `jpf_trace`) next to your existing `nojpf` condition, and optionally a
`jpf_message` condition with only the old violation text. Score all three against the same
ground truth. The race hint and lock-cycle lines are heuristics computed from one trace;
they are not ground truth.

## Known limits
- `TraceDump.java` was written against jpf-core 8 but could not be compiled here (no JPF in the
  sandbox). If `javac` complains about a method name, it is one of: `Search.getTransition`,
  `Search.isNewState`, `Search.isEndState`, `VM.getPath`, `Transition.getStep/getStepCount`,
  `MethodInfo.isSynchronized`. Check it against your jpf-core version.
- Locks are identified by the source expression in `synchronized (x)`. Synchronized methods
  appear as `method-sync` without the lock object, so wrong-lock bugs that use synchronized
  methods are visible only through the line numbers.
- Starvation runs stop at your skip bound (about 500 steps), so their trace is a spinning
  prefix; look for the repeating pattern, not the whole graph.
- Termination and uncaught-exception cases may produce no `trace.json` if JPF did not raise a
  property violation for them (for example a timeout); `run_summary.csv` shows which.
- The graph is capped at 20000 edges (`tracedump.max_edges`).
