# Ground Truth: Mutant-P3-lock_order_inversion_blocks-0

| Field | Value |
| --- | --- |
| Case ID | Mutant-P3-lock_order_inversion_blocks-0 |
| CONCUR problem name | n/a (the `topic` field is empty; original `prompt_id` is 3) |
| Model that generated the code | Qwen (original program, prompt_id 3). Mutated by `mutate_concurrency.py` (operator `lock_order_inversion_blocks`, `3-lock_order_inversion_blocks-0`) |
| JPF version / config file | JavaPathfinder core v8.0 (rev 2345caaa002e15c6147d001d1ccd71e4b538f8e9, from the run banner in the same results file); max_depth 3000; config file n/a |
| Annotator / date | auto-generated from the mutation metadata and the JPF log (`make_ground_truth.py`) / 2026-10-04 |
| Confidence | high. A single known edit nests two `synchronized` blocks in opposite orders, and JPF reports a deadlock. The exact lock cycle is derived from the mutation: JPF prints only thread states. |
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

Resource (lock-ordering) deadlock: nested monitors acquired in opposite orders.

---

## 2. JPF evidence

* **Violated property / error message:**

  `gov.nasa.jpf.vm.NotDeadlockedProperty`: `deadlock encountered`

* **Location (file:line):**

  n/a. JPF prints thread states only. The inverted sites are `CountingFireflies.tryToSleep()` and `CountingFireflies.setAsleep()`.

* **Counterexample summary (threads, key steps):**

  1. JPF starts on `CountingFireflies.main()` as the system under test.
  2. At the deadlock JPF lists these thread states (table below).
  3. Two threads are BLOCKED and `main` is WAITING (in `join`).
  4. Search ends at error #1 (states new=33,visited=5,backtracked=5,end=1, maxDepth 33, 6630 instructions).

  | Thread | JPF status | lockCount |
  | --- | --- | --- |
  | main (id 0) | WAITING | 0 |
  | Thread-1 (id 1) | BLOCKED | 0 |
  | Thread-2 (id 2) | BLOCKED | 0 |

---

## 3. Root cause

**Injected mutation (known by construction):**

`tryToSleep()` now nests `asleepLock` then `__auxLock`; `setAsleep()` now nests `__auxLock` then `asleepLock`. The nesting orders are opposite.

**Shared state** *(variable / object / lock):*

the locks `asleepLock` and `__auxLock`

**Accesses involved**

| Thread | Method | Line | Operation (R/W/lock/wait/notify) |
| --- | --- | --- | --- |
| thread running `tryToSleep()` | `CountingFireflies.tryToSleep` | n/a | lock `asleepLock`, then lock `aux` |
| thread running `setAsleep()` | `CountingFireflies.setAsleep` | n/a | lock `aux`, then lock `asleepLock` |

Lock-order facts come from the mutated source. The thread-to-method assignment is not printed by JPF.

The source is on a single line, so line numbers are not meaningful.

**Guarantee that is missing** *(what should be atomic, ordered, or protected):*

A global lock-acquisition order: code that needs both locks must always take them in the same order.

**Buggy interleaving** *(2 to 4 steps)*

1. One thread enters `tryToSleep()` and acquires `asleepLock`.
2. Another thread enters `setAsleep()` and acquires `__auxLock`.
3. The first waits for `__auxLock`, the second waits for `asleepLock`: circular wait.
   (derived from the mutation; JPF shows the BLOCKED threads)

**Why this produces the JPF symptom:**

JPF explores all schedules; one of them interleaves the two outer acquisitions before either inner acquisition. No thread can then run, which JPF reports as `NotDeadlockedProperty` violated.

---

## 4. Suggested solution

**Fix type**

* [ ] Add or widen synchronization (synchronized / lock)
* [ ] Use an atomic or concurrent class
* [ ] Add volatile
* [x] Change lock order / lock granularity
* [ ] Fix wait/notify (condition loop, notifyAll, missing signal)
* [ ] Thread confinement or immutability
* [ ] Other

**Where to apply it** *(file:line range)*:

`CountingFireflies.tryToSleep()` and `CountingFireflies.setAsleep()` (and the injected `__auxLock` field); single-line source (line numbers are not meaningful).

**Description of the fix:**

Undo the mutation: remove the extra inner `synchronized` wrapper that was added in each of the two methods and the injected `__auxLock` field, so each method again holds only its original lock.

**Code sketch**

```java
// before (mutated, buggy)

public class CountingFireflies {
    private static final Object __auxLock = new Object();
    private boolean asleep = false;
// ...
            synchronized (asleepLock) {
                synchronized (__auxLock) {
                    isAsleep = asleep;
                }
            }
// ...
    public void setAsleep(boolean value) {
        synchronized (__auxLock) {
            synchronized (asleepLock) {
                this.asleep = value;
            }
        }
```

```java
// after (fix = original program)

public class CountingFireflies {
    private boolean asleep = false;
// ...
            synchronized (asleepLock) {
                isAsleep = asleep;
            }
// ...
    public void setAsleep(boolean value) {
        synchronized (asleepLock) {
            this.asleep = value;
        }
```

**Why it removes the symptom:**

Each critical section holds one lock only, so there is no circular wait.

**Validation:**

The fixed version is the unmodified original program (prompt_id 3 in `codes.json`), taken as passing JPF per the dataset. This was not re-run here.

**Other acceptable fixes** *(there is often more than one)*:

* Keep the nesting but make both methods acquire the two locks in one fixed order. Not tested.
* Use one lock for both critical sections.

**Invalid or superficial fixes for this bug:**

* Adding a third lock or more nesting
* Only reordering inside one of the two methods and leaving the other unchanged in the opposite order
* Adding `Thread.sleep()` or other timing changes
* Removing or merging threads, or shrinking the workload, to hide the failure

**Reference solution** *(CONCUR ground_truth.csv row, if any):*

The original program, prompt_id 3 (`codes.json`).

---

## 5. Second annotator check *(about 10 cases)*

| Key field | Annotator 1 | Annotator 2 | Agree? |
| --- | --- | --- | --- |
| Class / pattern | Deadlock: Resource deadlock (lock ordering) | n/a | n/a |
| Shared state | the locks `asleepLock` and `__auxLock` | n/a | n/a |
| Minimal fix | Undo the mutation: remove the extra inner `synchronized` wrapper that was added in each of the two methods and the injected `__auxLock` field, so each method again holds only its original lock | n/a | n/a |

Notes / disagreements:

* This case is auto-generated: the root cause is the injected mutation, so no annotator judgement was involved. No second annotator was used.
* JPF stops at the first error it finds; other defects introduced by the same mutation, if any, would not appear in this log.
