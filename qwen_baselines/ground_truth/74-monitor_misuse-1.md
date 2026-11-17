# Ground Truth: Mutant-P74-monitor_misuse-1

| Field | Value |
| --- | --- |
| Case ID | Mutant-P74-monitor_misuse-1 |
| CONCUR problem name | n/a (the `topic` field is empty; original `prompt_id` is 74) |
| Model that generated the code | Qwen (original program, prompt_id 74). Mutated by `mutate_concurrency.py` (operator `monitor_misuse`, `74-monitor_misuse-1`) |
| JPF version / config file | JavaPathfinder core v8.0 (rev 2345caaa002e15c6147d001d1ccd71e4b538f8e9, from the run banner in the same results file); max_depth 3000; config file n/a |
| Annotator / date | auto-generated from the mutation metadata and the JPF log (`make_ground_truth.py`) / 2026-10-04 |
| Confidence | high. The only edit removes `synchronized` from a method that calls `wait()`, and JPF reports `IllegalMonitorStateException: wait() without holding lock` in that method. |
| Bug status | `injected-monitor-misuse-confirmed-by-JPF` |

---

## 1. Bug classification (ConFixAgent taxonomy)

**Family**

* [x] Non-deadlock
* [ ] Deadlock
* [ ] Other / out of scope (e.g. non-termination, unrelated exception, compile error)

**Non-deadlock class** *(only if non-deadlock)*

Monitor misuse (synchronization violation): `wait()` called without owning the monitor.

**Memory-access pattern**

Selected pattern: **none**

No data-race access pattern was reported; the failure is an uncaught exception from `Object.wait()`.

**Deadlock type**

n/a

---

## 2. JPF evidence

* **Violated property / error message:**

  `gov.nasa.jpf.vm.NoUncaughtExceptionsProperty`: `java.lang.IllegalMonitorStateException: notifyAll() without holding lock`

* **Location (file:line):**

  * `at java.lang.Object.notifyAll(gov.nasa.jpf.vm.JPF_java_lang_Object)`
  * `at Sleeper.setAsleep(Main.java:12)`
  * `at Main$$Lambda$1.run`

* **Counterexample summary (threads, key steps):**

  1. JPF starts on `Main.main()` as the system under test.
  2. The thread that calls `Sleeper.setAsleep()` reaches `wait()` without holding the monitor.
  3. `Object.wait()` throws `IllegalMonitorStateException`, uncaught in the thread.
  4. Search ends at error #1 (states new=8,visited=0,backtracked=0,end=0, maxDepth 8, 6376 instructions).

---

## 3. Root cause

**Injected mutation (known by construction):**

`synchronized` was removed from `Sleeper.setAsleep()`, which calls `wait()` (and/or `notify*()`).

**Shared state** *(variable / object / lock):*

the monitor of `Sleeper` (`this`), which `wait()` requires the caller to own

**Accesses involved**

| Thread | Method | Line | Operation (R/W/lock/wait/notify) |
| --- | --- | --- | --- |
| waiter | `Sleeper.setAsleep` | 10 | wait (monitor not held) |

Facts come from the JPF stack trace and the mutated source.

Line = declaration line of the method in the mutated source.

**Guarantee that is missing** *(what should be atomic, ordered, or protected):*

`wait()`, `notify()` and `notifyAll()` must be called while holding the monitor of the object they are called on.

**Buggy interleaving** *(2 to 4 steps)*

No interleaving is needed: the first thread to call `setAsleep()` and reach `wait()` fails immediately.

**Why this produces the JPF symptom:**

`Object.wait()` throws `IllegalMonitorStateException` when the caller does not own the monitor. The exception is not caught, so JPF reports `NoUncaughtExceptionsProperty`.

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

signature of `Sleeper.setAsleep()`; mutated source, line ~10.

**Description of the fix:**

Restore the `synchronized` modifier on `setAsleep()` (undo the mutation).

**Code sketch**

```java
// before (mutated, buggy)

    void setAsleep() {
        asleep = true;
```

```java
// after (fix = original program)

    synchronized void setAsleep() {
        asleep = true;
```

**Why it removes the symptom:**

The caller owns the monitor when it calls `wait()`.

**Validation:**

The fixed version is the unmodified original program (prompt_id 74 in `codes.json`), taken as passing JPF per the dataset. This was not re-run here.

**Other acceptable fixes** *(there is often more than one)*:

* Wrap the `wait()`/`notify*()` calls in `synchronized (this) { ... }` (equivalent).

**Invalid or superficial fixes for this bug:**

* Catching `IllegalMonitorStateException` and ignoring it
* Replacing `wait()` with `Thread.sleep()` polling
* Removing or merging threads, or shrinking the workload, to hide the failure

**Reference solution** *(CONCUR ground_truth.csv row, if any):*

The original program, prompt_id 74 (`codes.json`).

---

## 5. Second annotator check *(about 10 cases)*

| Key field | Annotator 1 | Annotator 2 | Agree? |
| --- | --- | --- | --- |
| Class / pattern | Non-deadlock: Monitor misuse (IllegalMonitorStateException) | n/a | n/a |
| Shared state | the monitor of `Sleeper` (`this`), which `wait()` requires the caller to own | n/a | n/a |
| Minimal fix | Restore the `synchronized` modifier on `setAsleep()` (undo the mutation) | n/a | n/a |

Notes / disagreements:

* This case is auto-generated: the root cause is the injected mutation, so no annotator judgement was involved. No second annotator was used.
* JPF stops at the first error it finds; other defects introduced by the same mutation, if any, would not appear in this log.
* Sibling mutants of the same program and operator: `74-monitor_misuse-0` → Uncaught Exception.
