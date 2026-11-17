# Ground Truth: Mutant-P97-missing_release-1

| Field | Value |
| --- | --- |
| Case ID | Mutant-P97-missing_release-1 |
| CONCUR problem name | n/a (the `topic` field is empty; original `prompt_id` is 97) |
| Model that generated the code | Qwen (original program, prompt_id 97). Mutated by `mutate_concurrency.py` (operator `missing_release`, `97-missing_release-1`) |
| JPF version / config file | JavaPathfinder core v8.0 (rev 2345caaa002e15c6147d001d1ccd71e4b538f8e9, from the run banner in the same results file); max_depth 3000; config file n/a |
| Annotator / date | auto-generated from the mutation metadata and the JPF log (`make_ground_truth.py`) / 2026-10-04 |
| Confidence | high. The only edit removes `availableItems.release()`, and JPF reports a deadlock with the releasing thread TERMINATED and the acquiring thread WAITING. |
| Bug status | `injected-deadlock-confirmed-by-JPF` |

---

## 1. Bug classification (ConFixAgent taxonomy)

**Family**

* [ ] Non-deadlock
* [x] Deadlock
* [ ] Other / out of scope (e.g. non-termination, unrelated exception, compile error)

**Non-deadlock class** *(only if non-deadlock)*

n/a

**Memory-access pattern**

Selected pattern: **none**

No data-race or access pattern was reported; JPF reported a deadlock.

**Deadlock type**

Resource deadlock on a counting semaphore: a permit is never released.

---

## 2. JPF evidence

* **Violated property / error message:**

  `gov.nasa.jpf.vm.NotDeadlockedProperty`: `deadlock encountered`

* **Location (file:line):**

  n/a. JPF prints thread states only. The release was removed in `BoundedBuffer.put()`; the matching `acquire()` is in `BoundedBuffer.take()`.

* **Counterexample summary (threads, key steps):**

  1. JPF starts on `Main.main()` as the system under test.
  2. At the deadlock JPF lists these thread states (table below).
  3. The thread that ran `put()` has TERMINATED, the thread in `take()` is WAITING on `availableItems.acquire()`, `main` is WAITING (in `join`).
  4. Search ends at error #1 (states new=15,visited=0,backtracked=0,end=1, maxDepth 15, 6936 instructions).

  | Thread | JPF status | lockCount |
  | --- | --- | --- |
  | main (id 0) | WAITING | 0 |
  | Thread-1 (id 1) | TERMINATED | 0 |
  | Thread-2 (id 2) | WAITING | 0 |

---

## 3. Root cause

**Injected mutation (known by construction):**

The call `availableItems.release();` was removed from `BoundedBuffer.put()`.

**Shared state** *(variable / object / lock):*

the semaphore `availableItems` of `BoundedBuffer`

**Accesses involved**

| Thread | Method | Line | Operation (R/W/lock/wait/notify) |
| --- | --- | --- | --- |
| releaser | `BoundedBuffer.put` | 25 | `availableItems.release()` removed |
| acquirer | `BoundedBuffer.take` | 34 | `availableItems.acquire()` blocks |

Facts come from the mutated source and the thread states in the JPF log.

Line = declaration line of the method in the mutated source.

**Guarantee that is missing** *(what should be atomic, ordered, or protected):*

Every `acquire()` needs a matching `release()` by the thread that makes the resource available.

**Buggy interleaving** *(2 to 4 steps)*

1. The releaser completes `put()` without releasing `availableItems`.
2. The acquirer calls `take()` and blocks in `availableItems.acquire()`; no permit will ever be released.
3. `main` waits in `join` for the acquirer. No thread can run.

**Why this produces the JPF symptom:**

Schedules in which the acquirer needs the missing permit end with all remaining threads waiting, which JPF reports as a deadlock.

---

## 4. Suggested solution

**Fix type**

* [ ] Add or widen synchronization (synchronized / lock)
* [ ] Use an atomic or concurrent class
* [ ] Add volatile
* [ ] Change lock order / lock granularity
* [ ] Fix wait/notify (condition loop, notifyAll, missing signal)
* [ ] Thread confinement or immutability
* [x] Other: **Restore `availableItems.release();` at the end of `put()` (undo the mutation).**

**Where to apply it** *(file:line range)*:

`BoundedBuffer.put()`; mutated source, line ~25.

**Description of the fix:**

Restore `availableItems.release();` at the end of `put()` (undo the mutation).

**Code sketch**

```java
// before (mutated, buggy)

        }

    }
```

```java
// after (fix = original program)

        }
        availableItems.release();
    }
```

**Why it removes the symptom:**

The permit is returned, so the waiting acquirer can proceed.

**Validation:**

The fixed version is the unmodified original program (prompt_id 97 in `codes.json`), taken as passing JPF per the dataset. This was not re-run here.

**Other acceptable fixes** *(there is often more than one)*:

* Release inside a `finally` block so it also happens on exceptions. Not tested.

**Invalid or superficial fixes for this bug:**

* Adding `tryAcquire()` with a timeout and ignoring failure
* Adding an unconditional extra `release()` elsewhere
* Adding `Thread.sleep()` or other timing changes
* Removing or merging threads, or shrinking the workload, to hide the failure

**Reference solution** *(CONCUR ground_truth.csv row, if any):*

The original program, prompt_id 97 (`codes.json`).

---

## 5. Second annotator check *(about 10 cases)*

| Key field | Annotator 1 | Annotator 2 | Agree? |
| --- | --- | --- | --- |
| Class / pattern | Deadlock: Resource deadlock (semaphore) | n/a | n/a |
| Shared state | the semaphore `availableItems` of `BoundedBuffer` | n/a | n/a |
| Minimal fix | Restore `availableItems.release();` at the end of `put()` (undo the mutation) | n/a | n/a |

Notes / disagreements:

* This case is auto-generated: the root cause is the injected mutation, so no annotator judgement was involved. No second annotator was used.
* JPF stops at the first error it finds; other defects introduced by the same mutation, if any, would not appear in this log.
* Sibling mutants of the same program and operator: `97-missing_release-0` → Pass. A passing sibling means JPF did not find the injected bug in that variant, not that the variant is correct.
