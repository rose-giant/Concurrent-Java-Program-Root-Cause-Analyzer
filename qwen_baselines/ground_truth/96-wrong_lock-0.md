# Ground Truth: Mutant-P96-wrong_lock-0

| Field | Value |
| --- | --- |
| Case ID | Mutant-P96-wrong_lock-0 |
| CONCUR problem name | n/a (the `topic` field is empty; original `prompt_id` is 96) |
| Model that generated the code | Qwen (original program, prompt_id 96). Mutated by `mutate_concurrency.py` (operator `wrong_lock`, `96-wrong_lock-0`) |
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

Selected pattern: **write/write** race on element 3 of a `StripedMap$Node[]`: Thread-3 WRITE in `StripedMap.put` vs Thread-4 WRITE in `StripedMap.clear`

This is the access pattern JPF reported for error #1. JPF stops at the first error, so other racing pairs may exist.

**Deadlock type**

n/a

---

## 2. JPF evidence

* **Violated property / error message:**

  `gov.nasa.jpf.listener.PreciseRaceDetector`: `race for array element [LStripedMap$Node;@1c5[3]`

* **Location (file:line):**

  * `StripedMap.put` (Thread-3) at Main.java:37
  * `StripedMap.clear` (Thread-4) at Main.java:43

* **Counterexample summary (threads, key steps):**

  1. JPF starts on `Main.main()` as the system under test.
  2. Thread-3 and Thread-4 reach the conflicting accesses listed above.
  3. Search ends at error #1 (states new=68,visited=26,backtracked=57,end=2, maxDepth 38, 8276 instructions).
  4. The mutated method `clear()` is one of the two reported accesses, so JPF's report points directly at the injected defect.

---

## 3. Root cause

**Injected mutation (known by construction):**

The critical section in `StripedMap.clear()` now locks the injected static lock `__wrongLock` instead of `locks[i % N_LOCKS]`. It still looks synchronized, but no other code uses `__wrongLock`, so it has no lock in common with the other accesses.

**Shared state** *(variable / object / lock):*

element 3 of a `StripedMap$Node[]`

**Accesses involved**

| Thread | Method | Line | Operation (R/W/lock/wait/notify) |
| --- | --- | --- | --- |
| Thread-3 | `StripedMap.put` | 37 | WRITE `aastore` |
| Thread-4 | `StripedMap.clear` | 43 | WRITE `aastore` |

* `StripedMap.put` (Thread-3): contains `synchronized` block(s) on `locks[index % N_LOCKS]`
* `StripedMap.clear` (Thread-4): contains `synchronized` block(s) on `__wrongLock`

Line = line reported by JPF.

**Guarantee that is missing** *(what should be atomic, ordered, or protected):*

A single lock shared by all conflicting accesses. `StripedMap.clear()` is guarded by `__wrongLock`, the others by `locks[i % N_LOCKS]`, so the guards do not exclude each other.

**Buggy interleaving** *(2 to 4 steps)*

1. Thread-3 executes WRITE `aastore` in `StripedMap.put`; protection there: contains `synchronized` block(s) on `locks[index % N_LOCKS]`.
2. Thread-4 executes WRITE `aastore` in `StripedMap.clear`; protection there: contains `synchronized` block(s) on `__wrongLock`.
3. The two accesses share no common lock and no happens-before edge. At least one is a write.
4. PreciseRaceDetector reports the race (error #1).

**Why this produces the JPF symptom:**

PreciseRaceDetector flags two accesses to the same location from different threads, at least one a write, that are not ordered by a common lock or other happens-before edge. The mutation replaced the common guard (`locks[i % N_LOCKS]`) of one critical section with an unrelated lock, so the checker finds such a pair in the explored schedules.

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

lock expression in `StripedMap.clear()` (and the injected `__wrongLock` field); mutated source, line ~40.

**Description of the fix:**

Change `synchronized (__wrongLock)` back to `synchronized (locks[i % N_LOCKS])` and remove the `__wrongLock` field (undo the mutation).

**Code sketch**

```java
// before (mutated, buggy)

class StripedMap { private static final Object __wrongLock = new Object();
    static final int N_LOCKS = 16;
// ...
        for (int i = 0; i < buckets.length; i++) {
            synchronized (__wrongLock) {
                buckets[i] = null;
```

```java
// after (fix = original program)

class StripedMap {
    static final int N_LOCKS = 16;
// ...
        for (int i = 0; i < buckets.length; i++) {
            synchronized (locks[i % N_LOCKS]) {
                buckets[i] = null;
```

**Why it removes the symptom:**

Restores one common guard for all conflicting accesses, so they are mutually exclusive and ordered; PreciseRaceDetector has nothing to report.

**Validation:**

The fixed version is the unmodified original program (prompt_id 96 in `codes.json`), taken as passing JPF per the dataset. This was not re-run here.

**Other acceptable fixes** *(there is often more than one)*:

* Make **every** critical section of the class use one common lock (for example `__wrongLock` everywhere); the original choice is `locks[i % N_LOCKS]`. Not tested.

**Invalid or superficial fixes for this bug:**

* Adding more synchronization on `__wrongLock` inside `clear()` only (still no common lock)
* Locking `__wrongLock` in addition to, but nested inside, the old lock in one method only
* Adding `Thread.sleep()` or other timing changes
* Removing or merging threads, or shrinking the workload, to hide the failure

**Reference solution** *(CONCUR ground_truth.csv row, if any):*

The original program, prompt_id 96 (`codes.json`).

---

## 5. Second annotator check *(about 10 cases)*

| Key field | Annotator 1 | Annotator 2 | Agree? |
| --- | --- | --- | --- |
| Class / pattern | Non-deadlock: Data race (inconsistent locking) | n/a | n/a |
| Shared state | element 3 of a `StripedMap$Node[]` | n/a | n/a |
| Minimal fix | Change `synchronized (__wrongLock)` back to `synchronized (locks[i % N_LOCKS])` and remove the `__wrongLock` field (undo the mutation) | n/a | n/a |

Notes / disagreements:

* This case is auto-generated: the root cause is the injected mutation, so no annotator judgement was involved. No second annotator was used.
* JPF stops at the first error it finds; other defects introduced by the same mutation, if any, would not appear in this log.
* Sibling mutants of the same program and operator: `96-wrong_lock-1` → Race Condition; `96-wrong_lock-2` → Race Condition.
