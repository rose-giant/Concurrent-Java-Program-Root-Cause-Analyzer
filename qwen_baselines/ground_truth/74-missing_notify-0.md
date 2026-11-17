# Ground Truth: Mutant-P74-missing_notify-0

| Field | Value |
| --- | --- |
| Case ID | Mutant-P74-missing_notify-0 |
| CONCUR problem name | n/a (the `topic` field is empty; original `prompt_id` is 74) |
| Model that generated the code | Qwen (original program, prompt_id 74). Mutated by `mutate_concurrency.py` (operator `missing_notify`, `74-missing_notify-0`) |
| JPF version / config file | JavaPathfinder core v8.0 (rev 2345caaa002e15c6147d001d1ccd71e4b538f8e9, from the run banner in the same results file); max_depth 3000; config file n/a |
| Annotator / date | auto-generated from the mutation metadata and the JPF log (`make_ground_truth.py`) / 2026-10-04 |
| Confidence | high. The only edit is the removed `notifyAll();`, and JPF reports a deadlock with a thread left WAITING and the setter thread TERMINATED, which is the lost-wake-up signature. |
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

Communication deadlock (lost notification): a thread waits on a condition whose signal is never sent.

---

## 2. JPF evidence

* **Violated property / error message:**

  `gov.nasa.jpf.vm.NotDeadlockedProperty`: `deadlock encountered`

* **Location (file:line):**

  n/a. JPF prints thread states only. The removed call was in `Sleeper.setAsleep()`; the waiter is in `Sleeper.tryToSleep()`.

* **Counterexample summary (threads, key steps):**

  1. JPF starts on `Main.main()` as the system under test.
  2. At the deadlock JPF lists these thread states (table below).
  3. One thread is WAITING inside `wait()`, the thread that set the flag has TERMINATED, `main` is WAITING (in `join`).
  4. Search ends at error #1 (states new=8,visited=0,backtracked=0,end=1, maxDepth 8, 6377 instructions).

  | Thread | JPF status | lockCount |
  | --- | --- | --- |
  | main (id 0) | WAITING | 0 |
  | Thread-1 (id 1) | WAITING | 1 |
  | Thread-2 (id 2) | TERMINATED | 0 |

---

## 3. Root cause

**Injected mutation (known by construction):**

The call `notifyAll();` was removed from `Sleeper.setAsleep()`; the state change is still made, but no waiting thread is woken.

**Shared state** *(variable / object / lock):*

the monitor of `Sleeper` and the condition it guards (the state tested before `wait()` in `tryToSleep()`)

**Accesses involved**

| Thread | Method | Line | Operation (R/W/lock/wait/notify) |
| --- | --- | --- | --- |
| waiter | `Sleeper.tryToSleep` | 4 | wait |
| setter | `Sleeper.setAsleep` | 10 | write condition; `notifyAll();` was removed here |

Facts come from the mutated source and the thread states in the JPF log.

Line = declaration line of the method in the mutated source.

**Guarantee that is missing** *(what should be atomic, ordered, or protected):*

A signal (notify/notifyAll) after the condition changes, so every thread waiting on that condition is woken.

**Buggy interleaving** *(2 to 4 steps)*

1. The waiter enters `tryToSleep()`, finds the condition false and calls `wait()` (releasing the monitor).
2. The setter runs `setAsleep()`: it sets the condition but no longer notifies.
3. The waiter stays WAITING forever; `main` waits in `join` for it. No thread can run.

**Why this produces the JPF symptom:**

In schedules where the waiter reaches `wait()` before the setter runs, no wake-up is ever sent. All remaining threads are blocked or waiting, which JPF reports as a deadlock.

---

## 4. Suggested solution

**Fix type**

* [ ] Add or widen synchronization (synchronized / lock)
* [ ] Use an atomic or concurrent class
* [ ] Add volatile
* [ ] Change lock order / lock granularity
* [x] Fix wait/notify (condition loop, notifyAll, missing signal)
* [ ] Thread confinement or immutability
* [ ] Other

**Where to apply it** *(file:line range)*:

`Sleeper.setAsleep()`; mutated source, line ~10.

**Description of the fix:**

Restore `notifyAll();` after the state change (undo the mutation).

**Code sketch**

```java
// before (mutated, buggy)

        asleep = true;

    }
```

```java
// after (fix = original program)

        asleep = true;
        notifyAll();
    }
```

**Why it removes the symptom:**

The waiter is woken after the condition becomes true, re-checks it in its loop and returns.

**Validation:**

The fixed version is the unmodified original program (prompt_id 74 in `codes.json`), taken as passing JPF per the dataset. This was not re-run here.

**Other acceptable fixes** *(there is often more than one)*:

* Use `notifyAll()` instead of `notify()` if several waiters could exist. Not tested.
* Use a `CountDownLatch` or `Condition` for the hand-over (a larger change).

**Invalid or superficial fixes for this bug:**

* Adding `Thread.sleep()` before `wait()`
* Replacing `wait()` with a timed `wait(ms)` without a condition re-check
* Making the setter method not `synchronized`
* Removing or merging threads, or shrinking the workload, to hide the failure

**Reference solution** *(CONCUR ground_truth.csv row, if any):*

The original program, prompt_id 74 (`codes.json`).

---

## 5. Second annotator check *(about 10 cases)*

| Key field | Annotator 1 | Annotator 2 | Agree? |
| --- | --- | --- | --- |
| Class / pattern | Deadlock: Communication deadlock (lost notification) | n/a | n/a |
| Shared state | the monitor of `Sleeper` and the condition it guards (the state tested before `wait()` in `tryToSleep()`) | n/a | n/a |
| Minimal fix | Restore `notifyAll();` after the state change (undo the mutation) | n/a | n/a |

Notes / disagreements:

* This case is auto-generated: the root cause is the injected mutation, so no annotator judgement was involved. No second annotator was used.
* JPF stops at the first error it finds; other defects introduced by the same mutation, if any, would not appear in this log.
