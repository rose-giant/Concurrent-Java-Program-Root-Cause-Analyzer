# Ground Truth: Mutant-P74-unguarded_wait-0

| Field | Value |
| --- | --- |
| Case ID | Mutant-P74-unguarded_wait-0 |
| CONCUR problem name | n/a (the `topic` field is empty; original `prompt_id` is 74) |
| Model that generated the code | Qwen (original program, prompt_id 74). Mutated by `mutate_concurrency.py` (operator `unguarded_wait`, `74-unguarded_wait-0`) |
| JPF version / config file | JavaPathfinder core v8.0 (rev 2345caaa002e15c6147d001d1ccd71e4b538f8e9, from the run banner in the same results file); max_depth 3000; config file n/a |
| Annotator / date | auto-generated from the mutation metadata and the JPF log (`make_ground_truth.py`) / 2026-10-04 |
| Confidence | high. The only edit removes the `while (!asleep)` guard around `wait()`, and JPF reports a deadlock with the waiter WAITING and the setter TERMINATED, which is the lost-wake-up signature. |
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

Communication deadlock (lost notification): `wait()` is no longer guarded by its condition.

---

## 2. JPF evidence

* **Violated property / error message:**

  `gov.nasa.jpf.vm.NotDeadlockedProperty`: `deadlock encountered`

* **Location (file:line):**

  n/a. JPF prints thread states only. The unguarded `wait()` is in `Sleeper.tryToSleep()`.

* **Counterexample summary (threads, key steps):**

  1. JPF starts on `Main.main()` as the system under test.
  2. At the deadlock JPF lists these thread states (table below).
  3. One thread is WAITING inside `wait()`, the other thread has TERMINATED, `main` is WAITING (in `join`).
  4. Search ends at error #1 (states new=20,visited=4,backtracked=14,end=3, maxDepth 11, 6464 instructions).

  | Thread | JPF status | lockCount |
  | --- | --- | --- |
  | main (id 0) | WAITING | 0 |
  | Thread-1 (id 1) | WAITING | 1 |
  | Thread-2 (id 2) | TERMINATED | 0 |

---

## 3. Root cause

**Injected mutation (known by construction):**

The guard `while (!asleep)` around `wait()` in `Sleeper.tryToSleep()` was removed, leaving an unconditional `wait()`.

**Shared state** *(variable / object / lock):*

the monitor of `Sleeper` and the condition `!asleep`

**Accesses involved**

| Thread | Method | Line | Operation (R/W/lock/wait/notify) |
| --- | --- | --- | --- |
| waiter | `Sleeper.tryToSleep` | 4 | wait (now unconditional) |
| setter | (method that sets `!asleep`) | n/a | write condition, notify |

Facts come from the mutated source and the thread states in the JPF log.

Line = declaration line of the method in the mutated source.

**Guarantee that is missing** *(what should be atomic, ordered, or protected):*

The condition must be tested in a loop around `wait()`, so a notification that arrived earlier is not lost.

**Buggy interleaving** *(2 to 4 steps)*

1. The setter runs first: it sets the condition and calls `notifyAll()` while nobody waits (the signal is lost).
2. The waiter enters `tryToSleep()` and calls `wait()` without checking the condition.
3. Nobody will notify again. The waiter stays WAITING; `main` waits in `join`. No thread can run.

**Why this produces the JPF symptom:**

In schedules where the setter finishes before the waiter reaches `wait()`, the only notification is already gone. All remaining threads are waiting, which JPF reports as a deadlock.

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

`Sleeper.tryToSleep()`; mutated source, line ~4.

**Description of the fix:**

Restore `while (!asleep) {` around `wait()` (undo the mutation).

**Code sketch**

```java
// before (mutated, buggy)

    synchronized void tryToSleep() throws InterruptedException {
        {
            wait();
```

```java
// after (fix = original program)

    synchronized void tryToSleep() throws InterruptedException {
        while (!asleep) {
            wait();
```

**Why it removes the symptom:**

If the condition is already true the thread skips `wait()`; otherwise it waits and re-checks after each wake-up.

**Validation:**

The fixed version is the unmodified original program (prompt_id 74 in `codes.json`), taken as passing JPF per the dataset. This was not re-run here.

**Other acceptable fixes** *(there is often more than one)*:

* Check the condition with an `if` before `wait()` (fixes this lost wake-up, but a loop is still needed against spurious wake-ups).
* Use a `CountDownLatch` or `Condition` for the hand-over (a larger change).

**Invalid or superficial fixes for this bug:**

* Adding `Thread.sleep()` before `wait()`
* Replacing `wait()` with a timed `wait(ms)` and no re-check
* Removing or merging threads, or shrinking the workload, to hide the failure

**Reference solution** *(CONCUR ground_truth.csv row, if any):*

The original program, prompt_id 74 (`codes.json`).

---

## 5. Second annotator check *(about 10 cases)*

| Key field | Annotator 1 | Annotator 2 | Agree? |
| --- | --- | --- | --- |
| Class / pattern | Deadlock: Communication deadlock (lost wake-up) | n/a | n/a |
| Shared state | the monitor of `Sleeper` and the condition `!asleep` | n/a | n/a |
| Minimal fix | Restore `while (!asleep) {` around `wait()` (undo the mutation) | n/a | n/a |

Notes / disagreements:

* This case is auto-generated: the root cause is the injected mutation, so no annotator judgement was involved. No second annotator was used.
* JPF stops at the first error it finds; other defects introduced by the same mutation, if any, would not appear in this log.
