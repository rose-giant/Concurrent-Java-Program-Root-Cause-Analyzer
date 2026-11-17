# Ground Truth: Mutant-P113-rm_join-1

| Field | Value |
| --- | --- |
| Case ID | Mutant-P113-rm_join-1 |
| CONCUR problem name | n/a (the `topic` field is empty; original `prompt_id` is 113) |
| Model that generated the code | Qwen (original program, prompt_id 113). Mutated by `mutate_concurrency.py` (operator `rm_join`, `113-rm_join-1`) |
| JPF version / config file | JavaPathfinder core v8.0 (rev 2345caaa002e15c6147d001d1ccd71e4b538f8e9, from the run banner in the same results file); max_depth 3000; config file n/a |
| Annotator / date | auto-generated from the mutation metadata and the JPF log (`make_ground_truth.py`) / 2026-10-04 |
| Confidence | high that the removed `t1.join()` is the trigger (the original passes JPF and this is the only edit; reproducibility of the run was not checked); low for the mechanism. The log is truncated and shows no property violation, so the explanation of the JPF-side failure is an inference. |
| Bug status | `jpf-no-finish (mutation is program-level benign; failure is JPF-side)` |

---

## 1. Bug classification (ConFixAgent taxonomy)

**Family**

* [ ] Non-deadlock
* [ ] Deadlock
* [x] Other / out of scope (e.g. non-termination, unrelated exception, compile error): **JPF run did not complete (harness classification: Uncaught Exception)**

**Non-deadlock class** *(only if non-deadlock)*

n/a

**Memory-access pattern**

Selected pattern: **none**

No property violation or access pattern was reported by JPF.

**Deadlock type**

n/a

---

## 2. JPF evidence

* **Violated property / error message:**

  None reported. The output has no `error #1: ...` line, no `results` section and no `statistics` section. The first line after `search started` is `java.lang.NullPointerException`.

* **Location (file:line):**

  n/a. The visible frames end in the search loop (`gov.nasa.jpf.search.DFSearch.search(DFSearch.java:79)` → `JPF.run` → `JPF.start` → `RunJPF.main`); no frame of the program under test is shown. The log keeps 10 lines and elides the middle with `...`.

* **Counterexample summary (threads, key steps):**

  1. JPF starts on `ServerStatusAfterSplit.main()` as the system under test and begins the depth-first search.
  2. The first captured line is `java.lang.NullPointerException`: an exception that propagated out of JPF's search loop. Its own frames are elided by the log truncation, and the visible tail frames are JPF's, so it looks host-side rather than a violation in the program under test.
  3. The captured output ends with host-side frames of `DFSearch.search`, not with a `results`/`statistics` section.
  4. No program trace is available.

---

## 3. Root cause

**Injected mutation (known by construction):**

`t1.join();` was removed from `main`. After the joins, `main` executes nothing else, so no code reads or depends on the joined thread's results.

**Shared state** *(variable / object / lock):*

n/a as a concurrency bug. The program's own shared state is not touched by the mutation.

**Accesses involved**

| Thread | Method | Line | Operation (R/W/lock/wait/notify) |
| --- | --- | --- | --- |
| main | `ServerStatusAfterSplit.main` | n/a | `t1.join()` removed (no wait for `t1`) |

The accesses of the worker threads are unchanged and are not related to the failure.

The source is on a single line, so line numbers are not meaningful.

**Guarantee that is missing** *(what should be atomic, ordered, or protected):*

Strictly, `main` no longer waits for `t1`, but `main` does nothing after its joins that depends on `t1`, so no guarantee is lost at the program level.

**Buggy interleaving** *(2 to 4 steps)*

n/a. There is no buggy interleaving in the program under test.

**Why this produces the JPF symptom:**

The root cause of the JPF failure is not determined by the supplied evidence. The only difference from the passing original is the removed `join()`, so the trigger is the mutation, but the program itself has no defect. The output has the same shape as Executor-ImproveList-P87 (host-side frames in `DFSearch.search`, no results section). A plausible reading is that JPF or one of the harness's listeners failed (or did not finish) when `main` terminates while another thread may still be alive. This is an inference: the harness timeout, exit code and stderr were not available.

---

## 4. Suggested solution

**Fix type**

* [ ] Add or widen synchronization (synchronized / lock)
* [ ] Use an atomic or concurrent class
* [ ] Add volatile
* [ ] Change lock order / lock granularity
* [ ] Fix wait/notify (condition loop, notifyAll, missing signal)
* [ ] Thread confinement or immutability
* [x] Other: **Restore `t1.join();` (undo the mutation).**

**Where to apply it** *(file:line range)*:

`ServerStatusAfterSplit.main`; single-line source (line numbers are not meaningful).

**Description of the fix:**

Restore `t1.join();` (undo the mutation).

**Code sketch**

```java
// before (mutated, buggy)

        t2.start();
        t2.join();
```

```java
// after (fix = original program)

        t2.start();
        t1.join();
        t2.join();
```

**Why it removes the symptom:**

n/a as an interleaving fix. With the join restored, the program is the original, which passes JPF.

**Validation:**

The fixed version is the unmodified original program (prompt_id 113 in `codes.json`), taken as passing JPF per the dataset. This was not re-run here.

**Behavioral note:**

The JVM does not exit until all non-daemon threads finish, and `main` reads nothing from the worker after its joins, so removing this `join()` does not change the final program state. The mutation is behaviour-preserving at the program level.

**Other acceptable fixes** *(there is often more than one)*:

* Bound the search or change the harness configuration. Not tested, and not a code change.

**Invalid or superficial fixes for this bug:**

* Adding or widening synchronization in the worker classes
* Wrapping or replacing the shared data structures
* Adding `Thread.sleep()`

**Reference solution** *(CONCUR ground_truth.csv row, if any):*

The original program, prompt_id 113 (`codes.json`).

---

## 5. Second annotator check *(about 10 cases)*

| Key field | Annotator 1 | Annotator 2 | Agree? |
| --- | --- | --- | --- |
| Class / pattern | Other / JPF run did not complete: JPF-side failure (benign mutation) | n/a | n/a |
| Shared state | n/a as a concurrency bug. The program's own shared state is not touched by the mutation. | n/a | n/a |
| Minimal fix | Restore `t1.join();` (undo the mutation) | n/a | n/a |

Notes / disagreements:

* This case is auto-generated: the root cause is the injected mutation, so no annotator judgement was involved. No second annotator was used.
* JPF stops at the first error it finds; other defects introduced by the same mutation, if any, would not appear in this log.
* Sibling mutants of the same program and operator: `113-rm_join-0` → Uncaught Exception.
* The harness label for this case (Uncaught Exception) comes from the shape of the truncated log. The exception shown appears to be on the JPF host side, not a `NoUncaughtExceptionsProperty` violation of the program under test, so this label should not be read as a program-level uncaught exception.
* Other `rm_join` mutants of other programs passed JPF (for example prompt_id 73 under both removals), so removing a join is not by itself sufficient to trigger this JPF-side failure; the trigger condition was not identified.
