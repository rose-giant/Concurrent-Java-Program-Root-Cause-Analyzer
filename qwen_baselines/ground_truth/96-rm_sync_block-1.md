# Ground Truth: Mutant-P96-rm_sync_block-1

| Field | Value |
| --- | --- |
| Case ID | Mutant-P96-rm_sync_block-1 |
| CONCUR problem name | n/a (the `topic` field is empty; original `prompt_id` is 96) |
| Model that generated the code | Qwen (original program, prompt_id 96). Mutated by `mutate_concurrency.py` (operator `rm_sync_block`, `96-rm_sync_block-1`) |
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

Selected pattern: **read/write** race on element 1 of a `StripedMap$Node[]`: Thread-2 READ in `StripedMap.get` vs Thread-4 WRITE in `StripedMap.clear`

This is the access pattern JPF reported for error #1. JPF stops at the first error, so other racing pairs may exist.

**Deadlock type**

n/a

---

## 2. JPF evidence

* **Violated property / error message:**

  `gov.nasa.jpf.listener.PreciseRaceDetector`: `race for array element [LStripedMap$Node;@1c4[1]`

* **Location (file:line):**

  * `StripedMap.get` (Thread-2) at Main.java:26
  * `StripedMap.clear` (Thread-4) at Main.java:43

* **Counterexample summary (threads, key steps):**

  1. JPF starts on `Main.main()` as the system under test.
  2. Thread-2 and Thread-4 reach the conflicting accesses listed above.
  3. Search ends at error #1 (states new=273,visited=307,backtracked=552,end=6, maxDepth 37, 13733 instructions).
  4. The mutated method `get()` is one of the two reported accesses, so JPF's report points directly at the injected defect.

---

## 3. Root cause

**Injected mutation (known by construction):**

The `synchronized (locks[index % N_LOCKS]) { ... }` wrapper was removed in `StripedMap.get()`; its body is unchanged but no longer holds `locks[index % N_LOCKS]`.

**Shared state** *(variable / object / lock):*

element 1 of a `StripedMap$Node[]`

**Accesses involved**

| Thread | Method | Line | Operation (R/W/lock/wait/notify) |
| --- | --- | --- | --- |
| Thread-2 | `StripedMap.get` | 26 | READ `aaload` |
| Thread-4 | `StripedMap.clear` | 43 | WRITE `aastore` |

* `StripedMap.get` (Thread-2): no synchronization in the method itself
* `StripedMap.clear` (Thread-4): contains `synchronized` block(s) on `locks[i % N_LOCKS]`

Line = line reported by JPF.

**Guarantee that is missing** *(what should be atomic, ordered, or protected):*

Mutual exclusion on the shared state: the other critical sections hold `locks[index % N_LOCKS]`, but `StripedMap.get()` no longer does, so there is no common lock between them.

**Buggy interleaving** *(2 to 4 steps)*

1. Thread-2 executes READ `aaload` in `StripedMap.get`; protection there: no synchronization in the method itself.
2. Thread-4 executes WRITE `aastore` in `StripedMap.clear`; protection there: contains `synchronized` block(s) on `locks[i % N_LOCKS]`.
3. The two accesses share no common lock and no happens-before edge. At least one is a write.
4. PreciseRaceDetector reports the race (error #1).

**Why this produces the JPF symptom:**

PreciseRaceDetector flags two accesses to the same location from different threads, at least one a write, that are not ordered by a common lock or other happens-before edge. The mutation removed the common guard (`locks[index % N_LOCKS]`, which the other sections still hold), so the checker finds such a pair in the explored schedules.

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

body of `StripedMap.get()`; mutated source, line ~23.

**Description of the fix:**

Re-wrap the removed statements in `synchronized (locks[index % N_LOCKS]) { ... }` (undo the mutation).

**Code sketch**

```java
// before (mutated, buggy)

        int index = hashIndex(key);
        {
            Node node = buckets[index];
```

```java
// after (fix = original program)

        int index = hashIndex(key);
        synchronized (locks[index % N_LOCKS]) {
            Node node = buckets[index];
```

**Why it removes the symptom:**

Restores one common guard for all conflicting accesses, so they are mutually exclusive and ordered; PreciseRaceDetector has nothing to report.

**Validation:**

The fixed version is the unmodified original program (prompt_id 96 in `codes.json`), taken as passing JPF per the dataset. This was not re-run here.

**Other acceptable fixes** *(there is often more than one)*:

* Any lock that **all** conflicting sections share works; the original choice is `locks[index % N_LOCKS]`. For example, changing every section to the same other lock is equivalent. Not tested.
* If the unprotected access is a single read or write of one field, `volatile` removes the data race but not any compound-action atomicity. Not tested.

**Invalid or superficial fixes for this bug:**

* Adding a lock around only the unprotected method but with a different lock object
* Making an unrelated method `synchronized`
* Adding `Thread.sleep()` or other timing changes
* Removing or merging threads, or shrinking the workload, to hide the failure

**Reference solution** *(CONCUR ground_truth.csv row, if any):*

The original program, prompt_id 96 (`codes.json`).

---

## 5. Second annotator check *(about 10 cases)*

| Key field | Annotator 1 | Annotator 2 | Agree? |
| --- | --- | --- | --- |
| Class / pattern | Non-deadlock: Data race | n/a | n/a |
| Shared state | element 1 of a `StripedMap$Node[]` | n/a | n/a |
| Minimal fix | Re-wrap the removed statements in `synchronized (locks[index % N_LOCKS]) { ... }` (undo the mutation) | n/a | n/a |

Notes / disagreements:

* This case is auto-generated: the root cause is the injected mutation, so no annotator judgement was involved. No second annotator was used.
* JPF stops at the first error it finds; other defects introduced by the same mutation, if any, would not appear in this log.
* Sibling mutants of the same program and operator: `96-rm_sync_block-0` → Race Condition; `96-rm_sync_block-2` → Race Condition.
