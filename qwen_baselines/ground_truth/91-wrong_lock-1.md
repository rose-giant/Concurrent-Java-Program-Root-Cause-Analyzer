# Ground Truth: Mutant-P91-wrong_lock-1

| Field | Value |
| --- | --- |
| Case ID | Mutant-P91-wrong_lock-1 |
| CONCUR problem name | n/a (the `topic` field is empty; original `prompt_id` is 91) |
| Model that generated the code | Qwen (original program, prompt_id 91). Mutated by `mutate_concurrency.py` (operator `wrong_lock`, `91-wrong_lock-1`) |
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

Selected pattern: **read/write** race on `PrimeGenerator.cancelled`: main WRITE in `PrimeGenerator.setCancelled` vs pool-1-thread-1 READ in `PrimeGenerator.isCancelled`

This is the access pattern JPF reported for error #1. JPF stops at the first error, so other racing pairs may exist.

**Deadlock type**

n/a

---

## 2. JPF evidence

* **Violated property / error message:**

  `gov.nasa.jpf.listener.PreciseRaceDetector`: `race for field PrimeGenerator@1c1.cancelled`

* **Location (file:line):**

  * `PrimeGenerator.setCancelled` (main) at Main.java:15
  * `PrimeGenerator.isCancelled` (pool-1-thread-1) at Main.java:11

* **Counterexample summary (threads, key steps):**

  1. JPF starts on `Main.main()` as the system under test.
  2. main and pool-1-thread-1 reach the conflicting accesses listed above.
  3. Search ends at error #1 (states new=60,visited=26,backtracked=54,end=27, maxDepth 32, 179875 instructions).
  4. The mutated method `isCancelled()` is one of the two reported accesses, so JPF's report points directly at the injected defect.

---

## 3. Root cause

**Injected mutation (known by construction):**

The critical section in `PrimeGenerator.isCancelled()` now locks the injected static lock `__wrongLock` instead of `this`. It still looks synchronized, but no other code uses `__wrongLock`, so it has no lock in common with the other accesses.

**Shared state** *(variable / object / lock):*

`PrimeGenerator.cancelled` (field)

**Accesses involved**

| Thread | Method | Line | Operation (R/W/lock/wait/notify) |
| --- | --- | --- | --- |
| main | `PrimeGenerator.setCancelled` | 15 | WRITE `putfield PrimeGenerator.cancelled` |
| pool-1-thread-1 | `PrimeGenerator.isCancelled` | 11 | READ `getfield PrimeGenerator.cancelled` |

* `PrimeGenerator.setCancelled` (main): synchronized method (monitor of `this`)
* `PrimeGenerator.isCancelled` (pool-1-thread-1): contains `synchronized` block(s) on `__wrongLock`

Line = line reported by JPF.

**Guarantee that is missing** *(what should be atomic, ordered, or protected):*

A single lock shared by all conflicting accesses. `PrimeGenerator.isCancelled()` is guarded by `__wrongLock`, the others by `this`, so the guards do not exclude each other.

**Buggy interleaving** *(2 to 4 steps)*

1. main executes WRITE `putfield PrimeGenerator.cancelled` in `PrimeGenerator.setCancelled`; protection there: synchronized method (monitor of `this`).
2. pool-1-thread-1 executes READ `getfield PrimeGenerator.cancelled` in `PrimeGenerator.isCancelled`; protection there: contains `synchronized` block(s) on `__wrongLock`.
3. The two accesses share no common lock and no happens-before edge. At least one is a write.
4. PreciseRaceDetector reports the race (error #1).

**Why this produces the JPF symptom:**

PreciseRaceDetector flags two accesses to the same location from different threads, at least one a write, that are not ordered by a common lock or other happens-before edge. The mutation replaced the common guard (`this`) of one critical section with an unrelated lock, so the checker finds such a pair in the explored schedules.

---

## 4. Suggested solution

**Fix type**

* [ ] Add or widen synchronization (synchronized / lock)
* [ ] Use an atomic or concurrent class
* [ ] Add volatile
* [x] Change lock order / lock granularity (use one common lock for all conflicting accesses)
* [ ] Fix wait/notify (condition loop, notifyAll, missing signal)
* [ ] Thread confinement or immutability
* [ ] Other

**Where to apply it** *(file:line range)*:

lock expression in `PrimeGenerator.isCancelled()` (and the injected `__wrongLock` field); mutated source, line ~10.

**Description of the fix:**

Restore the `synchronized` modifier on `isCancelled()` and remove the `synchronized (__wrongLock)` wrapper and the `__wrongLock` field (undo the mutation).

**Code sketch**

```java
// before (mutated, buggy)

class PrimeGenerator implements Runnable { private static final Object __wrongLock = new Object();
    private boolean cancelled;   // guarded by "this"
// ...
    private boolean isCancelled() { synchronized (__wrongLock) {
        return cancelled;
     } }
```

```java
// after (fix = original program)

class PrimeGenerator implements Runnable {
    private boolean cancelled;   // guarded by "this"
// ...
    private synchronized boolean isCancelled() {
        return cancelled;
    }
```

**Why it removes the symptom:**

Restores one common guard for all conflicting accesses, so they are mutually exclusive and ordered; PreciseRaceDetector has nothing to report.

**Validation:**

The fixed version is the unmodified original program (prompt_id 91 in `codes.json`), taken as passing JPF per the dataset. This was not re-run here.

**Other acceptable fixes** *(there is often more than one)*:

* Make **every** critical section of the class use one common lock (for example `__wrongLock` everywhere); the original choice is `this`. Not tested.

**Invalid or superficial fixes for this bug:**

* Adding more synchronization on `__wrongLock` inside `isCancelled()` only (still no common lock)
* Locking `__wrongLock` in addition to, but nested inside, the old lock in one method only
* Adding `Thread.sleep()` or other timing changes
* Removing or merging threads, or shrinking the workload, to hide the failure

**Reference solution** *(CONCUR ground_truth.csv row, if any):*

The original program, prompt_id 91 (`codes.json`).

---

## 5. Second annotator check *(about 10 cases)*

| Key field | Annotator 1 | Annotator 2 | Agree? |
| --- | --- | --- | --- |
| Class / pattern | Non-deadlock: Data race (inconsistent locking) | n/a | n/a |
| Shared state | `PrimeGenerator.cancelled` (field) | n/a | n/a |
| Minimal fix | Restore the `synchronized` modifier on `isCancelled()` and remove the `synchronized (__wrongLock)` wrapper and the `__wrongLock` field (undo the mutation) | n/a | n/a |

Notes / disagreements:

* This case is auto-generated: the root cause is the injected mutation, so no annotator judgement was involved. No second annotator was used.
* JPF stops at the first error it finds; other defects introduced by the same mutation, if any, would not appear in this log.
* Sibling mutants of the same program and operator: `91-wrong_lock-0` → Race Condition.
