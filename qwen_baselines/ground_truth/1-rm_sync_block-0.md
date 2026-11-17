# Ground Truth: Mutant-P1-rm_sync_block-0

| Field | Value |
| --- | --- |
| Case ID | Mutant-P1-rm_sync_block-0 |
| CONCUR problem name | Avoiding lock-ordering deadlock using try Lock. M1 |
| Model that generated the code | Qwen (original program, prompt_id 1). Mutated by `mutate_concurrency.py` (operator `rm_sync_block`, `1-rm_sync_block-0`) |
| JPF version / config file | JavaPathfinder core v8.0 (rev 2345caaa002e15c6147d001d1ccd71e4b538f8e9, from the run banner in the same results file); max_depth 27920; config file n/a |
| Annotator / date | auto-generated from the mutation metadata and the JPF log (`make_ground_truth.py`) / 2026-10-04 |
| Confidence | high. The only difference from the passing original is this one edit, and JPF's race report involves the mutated method. |
| Bug status | `injected-race-confirmed-by-JPF` |

---

## 1. Bug classification (ConFixAgent taxonomy)

**Family**

* [x] Non-deadlock
* [ ] Deadlock
* [ ] Other / out of scope (e.g. non-termination, unrelated exception, compile error)

**Non-deadlock class** *(only if non-deadlock)*

Data race (conflicting accesses to the same location with no common lock or happens-before ordering).

**Memory-access pattern**

Selected pattern: **read/write** race on `CountingLanterns.asleep`: Thread-1 READ in `CountingLanterns.tryToSleep` vs Thread-2 WRITE in `CountingLanterns.setAsleep`

This is the access pattern JPF reported for error #1. JPF stops at the first error, so other racing pairs may exist.

**Deadlock type**

n/a

---

## 2. JPF evidence

* **Violated property / error message:**

  `gov.nasa.jpf.listener.PreciseRaceDetector`: `race for field CountingLanterns@1bd.asleep`

* **Location (file:line):**

  * `CountingLanterns.tryToSleep` (Thread-1) at CountingLanterns.java:1 (line number not meaningful: single-line source)
  * `CountingLanterns.setAsleep` (Thread-2) at CountingLanterns.java:1 (line number not meaningful: single-line source)

* **Counterexample summary (threads, key steps):**

  1. JPF starts on `CountingLanterns.main()` as the system under test.
  2. Thread-1 and Thread-2 reach the conflicting accesses listed above.
  3. Search ends at error #1 (states new=14,visited=4,backtracked=4,end=0, maxDepth 14, 6493 instructions).
  4. The mutated method `tryToSleep()` is one of the two reported accesses, so JPF's report points directly at the injected defect.

---

## 3. Root cause

**Injected mutation (known by construction):**

The `synchronized (asleepLock) { ... }` wrapper was removed in `CountingLanterns.tryToSleep()`; its body is unchanged but no longer holds `asleepLock`.

**Shared state** *(variable / object / lock):*

`CountingLanterns.asleep` (field)

**Accesses involved**

| Thread | Method | Line | Operation (R/W/lock/wait/notify) |
| --- | --- | --- | --- |
| Thread-1 | `CountingLanterns.tryToSleep` | n/a | READ `getfield CountingLanterns.asleep` |
| Thread-2 | `CountingLanterns.setAsleep` | n/a | WRITE `putfield CountingLanterns.asleep` |

* `CountingLanterns.tryToSleep` (Thread-1): no synchronization in the method itself
* `CountingLanterns.setAsleep` (Thread-2): contains `synchronized` block(s) on `asleepLock`

The source is on a single line, so line numbers are not meaningful.

**Guarantee that is missing** *(what should be atomic, ordered, or protected):*

Mutual exclusion on the shared state: the other critical sections hold `asleepLock`, but `CountingLanterns.tryToSleep()` no longer does, so there is no common lock between them.

**Buggy interleaving** *(2 to 4 steps)*

1. Thread-1 executes READ `getfield CountingLanterns.asleep` in `CountingLanterns.tryToSleep`; protection there: no synchronization in the method itself.
2. Thread-2 executes WRITE `putfield CountingLanterns.asleep` in `CountingLanterns.setAsleep`; protection there: contains `synchronized` block(s) on `asleepLock`.
3. The two accesses share no common lock and no happens-before edge. At least one is a write.
4. PreciseRaceDetector reports the race (error #1).

**Why this produces the JPF symptom:**

PreciseRaceDetector flags two accesses to the same location from different threads, at least one a write, that are not ordered by a common lock or other happens-before edge. The mutation removed the common guard (`asleepLock`, which the other sections still hold), so the checker finds such a pair in the explored schedules.

---

## 4. Suggested solution

**Fix type**

* [x] Add or widen synchronization (synchronized / lock)
* [ ] Use an atomic or concurrent class
* [ ] Add volatile
* [ ] Change lock order / lock granularity
* [ ] Fix wait/notify (condition loop, notifyAll, missing signal)
* [ ] Thread confinement or immutability
* [ ] Other

**Where to apply it** *(file:line range)*:

body of `CountingLanterns.tryToSleep()`; single-line source (line numbers are not meaningful).

**Description of the fix:**

Re-wrap the removed statements in `synchronized (asleepLock) { ... }` (undo the mutation).

**Code sketch**

```java
// before (mutated, buggy)

            boolean isAsleep;
            {
                isAsleep = asleep;
```

```java
// after (fix = original program)

            boolean isAsleep;
            synchronized (asleepLock) {
                isAsleep = asleep;
```

**Why it removes the symptom:**

Restores one common guard for all conflicting accesses, so they are mutually exclusive and ordered; PreciseRaceDetector has nothing to report.

**Validation:**

The fixed version is the unmodified original program (prompt_id 1 in `codes.json`), taken as passing JPF per the dataset. This was not re-run here.

**Other acceptable fixes** *(there is often more than one)*:

* Any lock that **all** conflicting sections share works; the original choice is `asleepLock`. For example, changing every section to the same other lock is equivalent. Not tested.
* If the unprotected access is a single read or write of one field, `volatile` removes the data race but not any compound-action atomicity. Not tested.

**Invalid or superficial fixes for this bug:**

* Adding a lock around only the unprotected method but with a different lock object
* Making an unrelated method `synchronized`
* Adding `Thread.sleep()` or other timing changes
* Removing or merging threads, or shrinking the workload, to hide the failure

**Reference solution** *(CONCUR ground_truth.csv row, if any):*

The original program, prompt_id 1 (`codes.json`).

---

## 5. Second annotator check *(about 10 cases)*

| Key field | Annotator 1 | Annotator 2 | Agree? |
| --- | --- | --- | --- |
| Class / pattern | Non-deadlock: Data race | n/a | n/a |
| Shared state | `CountingLanterns.asleep` (field) | n/a | n/a |
| Minimal fix | Re-wrap the removed statements in `synchronized (asleepLock) { ... }` (undo the mutation) | n/a | n/a |

Notes / disagreements:

* This case is auto-generated: the root cause is the injected mutation, so no annotator judgement was involved. No second annotator was used.
* JPF stops at the first error it finds; other defects introduced by the same mutation, if any, would not appear in this log.
* Sibling mutants of the same program and operator: `1-rm_sync_block-1` → Race Condition.
