# Ground Truth: Mutant-P86-lock_order_inversion_methods-0

| Field | Value |
| --- | --- |
| Case ID | Mutant-P86-lock_order_inversion_methods-0 |
| CONCUR problem name | n/a (the `topic` field is empty; original `prompt_id` is 86) |
| Model that generated the code | Qwen (original program, prompt_id 86). Mutated by `mutate_concurrency.py` (operator `lock_order_inversion_methods`, `86-lock_order_inversion_methods-0`) |
| JPF version / config file | JavaPathfinder core v8.0 (rev 2345caaa002e15c6147d001d1ccd71e4b538f8e9, from the run banner in the same results file); max_depth 3000; config file n/a |
| Annotator / date | auto-generated from the mutation metadata and the JPF log (`make_ground_truth.py`) / 2026-10-04 |
| Confidence | high. A single known edit inverts the lock-acquisition order of two methods, and JPF reports a deadlock. The exact lock cycle is derived from the mutation: JPF prints only thread states, not which lock each thread waits for. |
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

Resource (lock-ordering) deadlock: two locks acquired in opposite orders by two methods.

---

## 2. JPF evidence

* **Violated property / error message:**

  `gov.nasa.jpf.vm.NotDeadlockedProperty`: `deadlock encountered`

* **Location (file:line):**

  n/a. JPF prints thread states only, no blocking frames. The inverted sites are `PublishingVehicleTracker.getLocation()` and `PublishingVehicleTracker.setLocation()`.

* **Counterexample summary (threads, key steps):**

  1. JPF starts on `Main.main()` as the system under test.
  2. At the deadlock JPF lists these thread states (table below).
  3. Two threads are BLOCKED on a monitor and `main` is WAITING (in `join`).
  4. Search ends at error #1 (states new=5570,visited=372,backtracked=2942,end=1, maxDepth 3000, 386637 instructions).

  | Thread | JPF status | lockCount |
  | --- | --- | --- |
  | pool-1-thread-1 (id 1) | BLOCKED | 0 |
  | pool-1-thread-2 (id 2) | BLOCKED | 0 |

---

## 3. Root cause

**Injected mutation (known by construction):**

`getLocation()` now takes `this` then `__auxLock`; `setLocation()` now takes `__auxLock` then `this`. Both methods still exclude each other, but the acquisition orders are opposite.

**Shared state** *(variable / object / lock):*

the instance monitor of `PublishingVehicleTracker` (`this`) and the injected static lock `PublishingVehicleTracker.__auxLock`

**Accesses involved**

| Thread | Method | Line | Operation (R/W/lock/wait/notify) |
| --- | --- | --- | --- |
| thread running `getLocation()` | `PublishingVehicleTracker.getLocation` | n/a | lock `this`, then lock `PublishingVehicleTracker.__auxLock` |
| thread running `setLocation()` | `PublishingVehicleTracker.setLocation` | n/a | lock `PublishingVehicleTracker.__auxLock`, then lock `this` |

Lock-order facts come from the mutated source. The thread-to-method assignment is not printed by JPF.

The source is on a single line, so line numbers are not meaningful.

**Guarantee that is missing** *(what should be atomic, ordered, or protected):*

A global lock-acquisition order: every code path that needs both locks must take them in the same order.

**Buggy interleaving** *(2 to 4 steps)*

1. One thread enters `getLocation()` and acquires `this`.
2. Another thread enters `setLocation()` and acquires `__auxLock`.
3. The first thread waits for `__auxLock`; the second waits for `this`. Neither can proceed (circular wait).
   (derived from the mutation; JPF shows the two BLOCKED threads)

**Why this produces the JPF symptom:**

JPF explores all schedules; one of them interleaves the two lock acquisitions as above. At that state no thread can run (no runnable thread, some not terminated), which JPF reports as `NotDeadlockedProperty` violated.

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

`PublishingVehicleTracker.getLocation()` and `PublishingVehicleTracker.setLocation()`, and the injected `__auxLock` field; single-line source (line numbers are not meaningful).

**Description of the fix:**

Undo the mutation: remove the injected `__auxLock` and its `synchronized` wrappers, restoring the `synchronized` modifier on `setLocation()` (and keeping it on `getLocation()`). Every access again needs one lock only.

**Code sketch**

```java
// before (mutated, buggy)

class PublishingVehicleTracker {
    private static final Object __auxLock = new Object();
    private final ConcurrentHashMap<String, SafePoint> locations;
// ...
    synchronized SafePoint getLocation(String id) {
        synchronized (__auxLock) {
            SafePoint p = locations.get(id);
            return p == null ? null : new SafePoint(p.x, p.y);
        }
    }
    void setLocation(String id, int x, int y) {
        synchronized (__auxLock) {
            synchronized (this) {
                SafePoint p = locations.get(id);
// ...
                p.y = y;
            }
        }
    }
```

```java
// after (fix = original program)

class PublishingVehicleTracker {
    private final ConcurrentHashMap<String, SafePoint> locations;
// ...
    synchronized SafePoint getLocation(String id) {
        SafePoint p = locations.get(id);
        return p == null ? null : new SafePoint(p.x, p.y);
    }
    synchronized void setLocation(String id, int x, int y) {
        SafePoint p = locations.get(id);
// ...
        p.y = y;
    }
```

**Why it removes the symptom:**

With a single lock there is no circular wait, so no deadlock state is reachable.

**Validation:**

The fixed version is the unmodified original program (prompt_id 86 in `codes.json`), taken as passing JPF per the dataset. This was not re-run here.

**Other acceptable fixes** *(there is often more than one)*:

* Keep both locks but make both methods take them in the same order (`this` then `__auxLock`). Not tested.
* Use a single lock object for both methods (any one lock all the code shares).

**Invalid or superficial fixes for this bug:**

* Adding a third lock or more nesting
* Making one method `synchronized` on a different object without fixing the order
* Adding `Thread.sleep()` or other timing changes
* Removing or merging threads, or shrinking the workload, to hide the failure

**Reference solution** *(CONCUR ground_truth.csv row, if any):*

The original program, prompt_id 86 (`codes.json`).

---

## 5. Second annotator check *(about 10 cases)*

| Key field | Annotator 1 | Annotator 2 | Agree? |
| --- | --- | --- | --- |
| Class / pattern | Deadlock: Resource deadlock (lock ordering) | n/a | n/a |
| Shared state | the instance monitor of `PublishingVehicleTracker` (`this`) and the injected static lock `PublishingVehicleTracker.__au… | n/a | n/a |
| Minimal fix | Undo the mutation: remove the injected `__auxLock` and its `synchronized` wrappers, restoring the `synchronized` modifier on `setLocation()` (and keeping it on `getLocation()`) | n/a | n/a |

Notes / disagreements:

* This case is auto-generated: the root cause is the injected mutation, so no annotator judgement was involved. No second annotator was used.
* JPF stops at the first error it finds; other defects introduced by the same mutation, if any, would not appear in this log.
