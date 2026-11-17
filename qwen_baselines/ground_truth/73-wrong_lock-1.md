# Ground Truth: Mutant-P73-wrong_lock-1

| Field | Value |
| --- | --- |
| Case ID | Mutant-P73-wrong_lock-1 |
| CONCUR problem name | n/a (the `topic` field is empty; original `prompt_id` is 73) |
| Model that generated the code | Qwen (original program, prompt_id 73). Mutated by `mutate_concurrency.py` (operator `wrong_lock`, `73-wrong_lock-1`) |
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

Selected pattern: **read/write** race on `IntHolder.value`: Thread-1 WRITE in `IntHolder.set` vs Thread-2 READ in `IntHolder.get`

This is the access pattern JPF reported for error #1. JPF stops at the first error, so other racing pairs may exist.

**Deadlock type**

n/a

---

## 2. JPF evidence

* **Violated property / error message:**

  `gov.nasa.jpf.listener.PreciseRaceDetector`: `race for field IntHolder@1c1.value`

* **Location (file:line):**

  * `IntHolder.set` (Thread-1) at Main.java:35
  * `IntHolder.get` (Thread-2) at Main.java:31

* **Counterexample summary (threads, key steps):**

  1. JPF starts on `Main.main()` as the system under test.
  2. Thread-1 and Thread-2 reach the conflicting accesses listed above.
  3. Search ends at error #1 (states new=20,visited=6,backtracked=17,end=2, maxDepth 10, 6505 instructions).
  4. The mutated method `get()` is one of the two reported accesses, so JPF's report points directly at the injected defect.

---

## 3. Root cause

**Injected mutation (known by construction):**

The critical section in `IntHolder.get()` now locks the injected static lock `__wrongLock` instead of `this`. It still looks synchronized, but no other code uses `__wrongLock`, so it has no lock in common with the other accesses.

**Shared state** *(variable / object / lock):*

`IntHolder.value` (field)

**Accesses involved**

| Thread | Method | Line | Operation (R/W/lock/wait/notify) |
| --- | --- | --- | --- |
| Thread-1 | `IntHolder.set` | 35 | WRITE `putfield IntHolder.value` |
| Thread-2 | `IntHolder.get` | 31 | READ `getfield IntHolder.value` |

* `IntHolder.set` (Thread-1): synchronized method (monitor of `this`)
* `IntHolder.get` (Thread-2): contains `synchronized` block(s) on `__wrongLock`

Line = line reported by JPF.

**Guarantee that is missing** *(what should be atomic, ordered, or protected):*

A single lock shared by all conflicting accesses. `IntHolder.get()` is guarded by `__wrongLock`, the others by `this`, so the guards do not exclude each other.

**Buggy interleaving** *(2 to 4 steps)*

1. Thread-1 executes WRITE `putfield IntHolder.value` in `IntHolder.set`; protection there: synchronized method (monitor of `this`).
2. Thread-2 executes READ `getfield IntHolder.value` in `IntHolder.get`; protection there: contains `synchronized` block(s) on `__wrongLock`.
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

lock expression in `IntHolder.get()` (and the injected `__wrongLock` field); mutated source, line ~30.

**Description of the fix:**

Restore the `synchronized` modifier on `get()` and remove the `synchronized (__wrongLock)` wrapper and the `__wrongLock` field (undo the mutation).

**Code sketch**

```java
// before (mutated, buggy)

class IntHolder { private static final Object __wrongLock = new Object();
    private int value;

    public int get() { synchronized (__wrongLock) {
        return value;
     } }
```

```java
// after (fix = original program)

class IntHolder {
    private int value;

    public synchronized int get() {
        return value;
    }
```

**Why it removes the symptom:**

Restores one common guard for all conflicting accesses, so they are mutually exclusive and ordered; PreciseRaceDetector has nothing to report.

**Validation:**

The fixed version is the unmodified original program (prompt_id 73 in `codes.json`), taken as passing JPF per the dataset. This was not re-run here.

**Other acceptable fixes** *(there is often more than one)*:

* Make **every** critical section of the class use one common lock (for example `__wrongLock` everywhere); the original choice is `this`. Not tested.

**Invalid or superficial fixes for this bug:**

* Adding more synchronization on `__wrongLock` inside `get()` only (still no common lock)
* Locking `__wrongLock` in addition to, but nested inside, the old lock in one method only
* Adding `Thread.sleep()` or other timing changes
* Removing or merging threads, or shrinking the workload, to hide the failure

**Reference solution** *(CONCUR ground_truth.csv row, if any):*

The original program, prompt_id 73 (`codes.json`).

---

## 5. Second annotator check *(about 10 cases)*

| Key field | Annotator 1 | Annotator 2 | Agree? |
| --- | --- | --- | --- |
| Class / pattern | Non-deadlock: Data race (inconsistent locking) | n/a | n/a |
| Shared state | `IntHolder.value` (field) | n/a | n/a |
| Minimal fix | Restore the `synchronized` modifier on `get()` and remove the `synchronized (__wrongLock)` wrapper and the `__wrongLock` field (undo the mutation) | n/a | n/a |

Notes / disagreements:

* This case is auto-generated: the root cause is the injected mutation, so no annotator judgement was involved. No second annotator was used.
* JPF stops at the first error it finds; other defects introduced by the same mutation, if any, would not appear in this log.
* Sibling mutants of the same program and operator: `73-wrong_lock-0` → Race Condition.
