# Ground Truth: Mutant-P80-rm_sync_one-0

| Field | Value |
| --- | --- |
| Case ID | Mutant-P80-rm_sync_one-0 |
| CONCUR problem name | n/a (the `topic` field is empty; original `prompt_id` is 80) |
| Model that generated the code | Qwen (original program, prompt_id 80). Mutated by `mutate_concurrency.py` (operator `rm_sync_one`, `80-rm_sync_one-0`) |
| JPF version / config file | JavaPathfinder core v8.0 (rev 2345caaa002e15c6147d001d1ccd71e4b538f8e9, from the run banner in the same results file); max_depth 3000; config file n/a |
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

Selected pattern: **read/write** race on `Factorizer.cache`: Thread-1 READ in `Factorizer.service` vs Thread-2 WRITE in `Factorizer.service`

This is the access pattern JPF reported for error #1. JPF stops at the first error, so other racing pairs may exist.

**Deadlock type**

n/a

---

## 2. JPF evidence

* **Violated property / error message:**

  `gov.nasa.jpf.listener.PreciseRaceDetector`: `race for field Factorizer@1c0.cache`

* **Location (file:line):**

  * `Factorizer.service` (Thread-1) at Main.java:1 (line number not meaningful: single-line source)
  * `Factorizer.service` (Thread-2) at Main.java:1 (line number not meaningful: single-line source)

* **Counterexample summary (threads, key steps):**

  1. JPF starts on `Main.main()` as the system under test.
  2. Thread-1 and Thread-2 reach the conflicting accesses listed above.
  3. Search ends at error #1 (states new=35,visited=15,backtracked=36,end=2, maxDepth 16, 16011 instructions).
  4. The mutated method `service()` is one of the two reported accesses, so JPF's report points directly at the injected defect.

---

## 3. Root cause

**Injected mutation (known by construction):**

`synchronized` was removed from the signature of `Factorizer.service()`. The other synchronized methods of the class still take the instance monitor, but this method no longer does.

**Shared state** *(variable / object / lock):*

`Factorizer.cache` (field)

**Accesses involved**

| Thread | Method | Line | Operation (R/W/lock/wait/notify) |
| --- | --- | --- | --- |
| Thread-1 | `Factorizer.service` | n/a | READ `getfield Factorizer.cache` |
| Thread-2 | `Factorizer.service` | n/a | WRITE `putfield Factorizer.cache` |

* `Factorizer.service` (Thread-1): no synchronization in the method itself
* `Factorizer.service` (Thread-2): no synchronization in the method itself

The source is on a single line, so line numbers are not meaningful.

**Guarantee that is missing** *(what should be atomic, ordered, or protected):*

Mutual exclusion on the shared state: every access must hold the same monitor. `service()` holds none, so its access is not ordered with the accesses made by the still-synchronized methods.

**Buggy interleaving** *(2 to 4 steps)*

1. Thread-1 executes READ `getfield Factorizer.cache` in `Factorizer.service`; protection there: no synchronization in the method itself.
2. Thread-2 executes WRITE `putfield Factorizer.cache` in `Factorizer.service`; protection there: no synchronization in the method itself.
3. The two accesses share no common lock and no happens-before edge. At least one is a write.
4. PreciseRaceDetector reports the race (error #1).

**Why this produces the JPF symptom:**

PreciseRaceDetector flags two accesses to the same location from different threads, at least one a write, that are not ordered by a common lock or other happens-before edge. The mutation removed the common guard (the instance monitor (`this`) that the other synchronized methods use), so the checker finds such a pair in the explored schedules.

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

signature of `Factorizer.service()`; single-line source (line numbers are not meaningful).

**Description of the fix:**

Restore the `synchronized` modifier on `service()` (undo the mutation).

**Code sketch**

```java
// before (mutated, buggy)

    );
    BigInteger[] service(BigInteger input) {
        BigInteger[] factors = cache.getFactors(input);
```

```java
// after (fix = original program)

    );
    synchronized BigInteger[] service(BigInteger input) {
        BigInteger[] factors = cache.getFactors(input);
```

**Why it removes the symptom:**

Restores one common guard for all conflicting accesses, so they are mutually exclusive and ordered; PreciseRaceDetector has nothing to report.

**Validation:**

The fixed version is the unmodified original program (prompt_id 80 in `codes.json`), taken as passing JPF per the dataset. This was not re-run here.

**Other acceptable fixes** *(there is often more than one)*:

* Wrap the body of `service()` in `synchronized (this) { ... }` (equivalent to the modifier).
* If the unprotected access is a single read or write of one field, declaring that field `volatile` (or using an `Atomic*` class) removes the data race, but only the lock restores atomicity of compound actions. Not tested.

**Invalid or superficial fixes for this bug:**

* Adding `synchronized` to unrelated methods that do not touch the raced state
* Synchronizing `service()` on a different lock than the other methods (that is the `wrong_lock` mutation)
* Adding `Thread.sleep()` or other timing changes
* Removing or merging threads, or shrinking the workload, to hide the failure

**Reference solution** *(CONCUR ground_truth.csv row, if any):*

The original program, prompt_id 80 (`codes.json`).

---

## 5. Second annotator check *(about 10 cases)*

| Key field | Annotator 1 | Annotator 2 | Agree? |
| --- | --- | --- | --- |
| Class / pattern | Non-deadlock: Data race | n/a | n/a |
| Shared state | `Factorizer.cache` (field) | n/a | n/a |
| Minimal fix | Restore the `synchronized` modifier on `service()` (undo the mutation) | n/a | n/a |

Notes / disagreements:

* This case is auto-generated: the root cause is the injected mutation, so no annotator judgement was involved. No second annotator was used.
* JPF stops at the first error it finds; other defects introduced by the same mutation, if any, would not appear in this log.
