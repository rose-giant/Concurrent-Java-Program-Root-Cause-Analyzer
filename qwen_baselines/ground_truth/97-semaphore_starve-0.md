# Ground Truth: Mutant-P97-semaphore_starve-0

| Field | Value |
| --- | --- |
| Case ID | Mutant-P97-semaphore_starve-0 |
| CONCUR problem name | n/a (the `topic` field is empty; original `prompt_id` is 97) |
| Model that generated the code | Qwen (original program, prompt_id 97). Mutated by `mutate_concurrency.py` (operator `semaphore_starve`, `97-semaphore_starve-0`) |
| JPF version / config file | JavaPathfinder core v8.0 (rev 2345caaa002e15c6147d001d1ccd71e4b538f8e9, from the run banner in the same results file); max_depth 3000; config file n/a |
| Annotator / date | auto-generated from the mutation metadata and the JPF log (`make_ground_truth.py`) / 2026-10-04 |
| Confidence | high. The only edit lowers the initial permit count by one, and JPF reports a deadlock with all three threads WAITING. |
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

Resource deadlock on a counting semaphore: `acquire()` can never be satisfied.

---

## 2. JPF evidence

* **Violated property / error message:**

  `gov.nasa.jpf.vm.NotDeadlockedProperty`: `deadlock encountered`

* **Location (file:line):**

  n/a. JPF prints thread states only. The mutated permit count is in the constructor of `BoundedBuffer`.

* **Counterexample summary (threads, key steps):**

  1. JPF starts on `Main.main()` as the system under test.
  2. At the deadlock JPF lists these thread states (table below).
  3. Both worker threads are WAITING (in `acquire()`), `main` is WAITING (in `join`).
  4. Search ends at error #1 (states new=8,visited=0,backtracked=0,end=1, maxDepth 8, 7113 instructions).

  | Thread | JPF status | lockCount |
  | --- | --- | --- |
  | main (id 0) | WAITING | 0 |
  | Thread-1 (id 1) | WAITING | 0 |
  | Thread-2 (id 2) | WAITING | 0 |

---

## 3. Root cause

**Injected mutation (known by construction):**

`new Semaphore(capacity)` was changed to `new Semaphore(Math.max(0, (capacity) - 1))`, so one permit fewer is available at start. With `new BoundedBuffer<>(1)` in `main`, the semaphore starts with 0 permits.

**Shared state** *(variable / object / lock):*

the `availableSpaces` and `availableItems` semaphores of `BoundedBuffer`

**Accesses involved**

| Thread | Method | Line | Operation (R/W/lock/wait/notify) |
| --- | --- | --- | --- |
| producer | `BoundedBuffer.put` | n/a | `availableSpaces.acquire()` blocks (no permit) |
| consumer | `BoundedBuffer.take` | n/a | `availableItems.acquire()` blocks (no item yet) |

Facts come from the mutated source and the thread states in the JPF log.

Line = declaration line of the method in the mutated source.

**Guarantee that is missing** *(what should be atomic, ordered, or protected):*

Enough initial permits for the first `put` to proceed, so that the first item can be produced and then consumed.

**Buggy interleaving** *(2 to 4 steps)*

1. The producer calls `put`: `availableSpaces.acquire()` finds no permit and blocks.
2. The consumer calls `take`: `availableItems.acquire()` blocks, because nothing was produced.
3. Each thread waits for a release that only the other can perform: circular wait; `main` waits in `join`.

**Why this produces the JPF symptom:**

No schedule can satisfy either `acquire()`, so every thread ends up waiting. JPF reports the state as a deadlock.

---

## 4. Suggested solution

**Fix type**

* [ ] Add or widen synchronization (synchronized / lock)
* [ ] Use an atomic or concurrent class
* [ ] Add volatile
* [ ] Change lock order / lock granularity
* [ ] Fix wait/notify (condition loop, notifyAll, missing signal)
* [ ] Thread confinement or immutability
* [x] Other: **Restore `new Semaphore(capacity)` (undo the mutation).**

**Where to apply it** *(file:line range)*:

semaphore initialisation in the constructor of `BoundedBuffer`; around line 13 of the mutated source.

**Description of the fix:**

Restore `new Semaphore(capacity)` (undo the mutation).

**Code sketch**

```java
// before (mutated, buggy)

        availableItems = new Semaphore(0);
        availableSpaces = new Semaphore(Math.max(0, (capacity) - 1));
    }
```

```java
// after (fix = original program)

        availableItems = new Semaphore(0);
        availableSpaces = new Semaphore(capacity);
    }
```

**Why it removes the symptom:**

The producer finds a free slot, proceeds, and releases `availableItems` for the consumer.

**Validation:**

The fixed version is the unmodified original program (prompt_id 97 in `codes.json`), taken as passing JPF per the dataset. This was not re-run here.

**Other acceptable fixes** *(there is often more than one)*:

* Any initial permit count that is at least the number of items the workload needs to buffer. Not tested.

**Invalid or superficial fixes for this bug:**

* Adding `tryAcquire()` with a timeout and ignoring failure
* Adding extra `release()` calls without justification
* Adding `Thread.sleep()` or other timing changes
* Removing or merging threads, or shrinking the workload, to hide the failure

**Reference solution** *(CONCUR ground_truth.csv row, if any):*

The original program, prompt_id 97 (`codes.json`).

---

## 5. Second annotator check *(about 10 cases)*

| Key field | Annotator 1 | Annotator 2 | Agree? |
| --- | --- | --- | --- |
| Class / pattern | Deadlock: Resource deadlock (semaphore) | n/a | n/a |
| Shared state | the `availableSpaces` and `availableItems` semaphores of `BoundedBuffer` | n/a | n/a |
| Minimal fix | Restore `new Semaphore(capacity)` (undo the mutation) | n/a | n/a |

Notes / disagreements:

* This case is auto-generated: the root cause is the injected mutation, so no annotator judgement was involved. No second annotator was used.
* JPF stops at the first error it finds; other defects introduced by the same mutation, if any, would not appear in this log.
