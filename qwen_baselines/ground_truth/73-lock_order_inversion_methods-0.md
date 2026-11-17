# Ground Truth: Mutant-P73-lock_order_inversion_methods-0

| Field | Value |
| --- | --- |
| Case ID | Mutant-P73-lock_order_inversion_methods-0 |
| CONCUR problem name | n/a (the `topic` field is empty; original `prompt_id` is 73) |
| Model that generated the code | Qwen (original program, prompt_id 73). Mutated by `mutate_concurrency.py` (operator `lock_order_inversion_methods`, `73-lock_order_inversion_methods-0`) |
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

  n/a. JPF prints thread states only, no blocking frames. The inverted sites are `IntHolder.get()` and `IntHolder.set()`.

* **Counterexample summary (threads, key steps):**

  1. JPF starts on `Main.main()` as the system under test.
  2. At the deadlock JPF lists these thread states (table below).
  3. Two threads are BLOCKED on a monitor and `main` is WAITING (in `join`).
  4. Search ends at error #1 (states new=33,visited=13,backtracked=38,end=3, maxDepth 14, 6630 instructions).

  | Thread | JPF status | lockCount |
  | --- | --- | --- |
  | main (id 0) | WAITING | 0 |
  | Thread-1 (id 1) | BLOCKED | 0 |
  | Thread-2 (id 2) | BLOCKED | 0 |

---

## 3. Root cause

**Injected mutation (known by construction):**

`get()` now takes `this` then `__auxLock`; `set()` now takes `__auxLock` then `this`. Both methods still exclude each other, but the acquisition orders are opposite.

**Shared state** *(variable / object / lock):*

the instance monitor of `IntHolder` (`this`) and the injected static lock `IntHolder.__auxLock`

**Accesses involved**

| Thread | Method | Line | Operation (R/W/lock/wait/notify) |
| --- | --- | --- | --- |
| thread running `get()` | `IntHolder.get` | 30 | lock `this`, then lock `IntHolder.__auxLock` |
| thread running `set()` | `IntHolder.set` | 34 | lock `IntHolder.__auxLock`, then lock `this` |

Lock-order facts come from the mutated source. The thread-to-method assignment is not printed by JPF.

Line = declaration line of the method in the mutated source.

**Guarantee that is missing** *(what should be atomic, ordered, or protected):*

A global lock-acquisition order: every code path that needs both locks must take them in the same order.

**Buggy interleaving** *(2 to 4 steps)*

1. One thread enters `get()` and acquires `this`.
2. Another thread enters `set()` and acquires `__auxLock`.
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

`IntHolder.get()` and `IntHolder.set()`, and the injected `__auxLock` field; mutated source, lines ~30, ~34.

**Description of the fix:**

Undo the mutation: remove the injected `__auxLock` and its `synchronized` wrappers, restoring the `synchronized` modifier on `set()` (and keeping it on `get()`). Every access again needs one lock only.

**Code sketch**

```java
// before (mutated, buggy)

class IntHolder { private static final Object __auxLock = new Object();
    private int value;

    public synchronized int get() { synchronized (__auxLock) {
        return value;
     } }

    public void set(int v) { synchronized (__auxLock) { synchronized (this) {
        value = v;
     } } }
}
```

```java
// after (fix = original program)

class IntHolder {
    private int value;

    public synchronized int get() {
        return value;
    }

    public synchronized void set(int v) {
        value = v;
    }
}
```

**Why it removes the symptom:**

With a single lock there is no circular wait, so no deadlock state is reachable.

**Validation:**

The fixed version is the unmodified original program (prompt_id 73 in `codes.json`), taken as passing JPF per the dataset. This was not re-run here.

**Other acceptable fixes** *(there is often more than one)*:

* Keep both locks but make both methods take them in the same order (`this` then `__auxLock`). Not tested.
* Use a single lock object for both methods (any one lock all the code shares).

**Invalid or superficial fixes for this bug:**

* Adding a third lock or more nesting
* Making one method `synchronized` on a different object without fixing the order
* Adding `Thread.sleep()` or other timing changes
* Removing or merging threads, or shrinking the workload, to hide the failure

**Reference solution** *(CONCUR ground_truth.csv row, if any):*

The original program, prompt_id 73 (`codes.json`).

---

## 5. Second annotator check *(about 10 cases)*

| Key field | Annotator 1 | Annotator 2 | Agree? |
| --- | --- | --- | --- |
| Class / pattern | Deadlock: Resource deadlock (lock ordering) | n/a | n/a |
| Shared state | the instance monitor of `IntHolder` (`this`) and the injected static lock `IntHolder.__auxLock` | n/a | n/a |
| Minimal fix | Undo the mutation: remove the injected `__auxLock` and its `synchronized` wrappers, restoring the `synchronized` modifier on `set()` (and keeping it on `get()`) | n/a | n/a |

Notes / disagreements:

* This case is auto-generated: the root cause is the injected mutation, so no annotator judgement was involved. No second annotator was used.
* JPF stops at the first error it finds; other defects introduced by the same mutation, if any, would not appear in this log.
