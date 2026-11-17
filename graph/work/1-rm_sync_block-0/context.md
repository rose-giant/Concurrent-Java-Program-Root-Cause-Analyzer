# JPF evidence for case `1-rm_sync_block-0`

JPF reported no counterexample path for this case (no property violation, timeout, or the violation produced no replayable path).
## Source (formatted; line numbers match the trace)
```java
  1  public class CountingLanterns {
  2      private boolean asleep = false;
  3      private final Object asleepLock = new Object();
  4      public void tryToSleep() {
  5          while (true) {
  6              boolean isAsleep;
  7              {
  8                  isAsleep = asleep;
  9              }
 10              if (isAsleep) {
 11                  break;
 12              }
 13              countSomeSheep();
 14          }
 15      }
 16      private void countSomeSheep() {
 17          System.out.println("Tallying a lantern...");
 18          try {
 19              Thread.sleep(100);
 20          } catch (InterruptedException e) {
 21              Thread.currentThread().interrupt();
 22          }
 23      }
 24      public void setAsleep(boolean value) {
 25          synchronized (asleepLock) {
 26              this.asleep = value;
 27          }
 28      }
 29      public static void main(String[] args) {
 30          CountingLanterns traveler = new CountingLanterns();
 31          Thread t1 = new Thread(() -> traveler.tryToSleep());
 32          Thread t2 = new Thread(() -> {
 33              try {
 34                  Thread.sleep(500);
 35              } catch (InterruptedException e) {
 36                  Thread.currentThread().interrupt();
 37              }
 38              traveler.setAsleep(true);
 39          });
 40          t1.start();
 41          t2.start();
 42          try {
 43              t1.join();
 44              t2.join();
 45          } catch (InterruptedException e) {
 46              Thread.currentThread().interrupt();
 47          }
 48      }
 49  }
```

## State graph

states seen: 55, transitions: 122, end states: 1, truncated: False

