public class Main {
    public static void main(String[] args) {
        DragonScaleCounter counter = new DragonScaleCounter();
        Thread t1 = new Thread(() -> {
            for (int i = 0; i < 100; i++) {
                counter.growScale();
            }
            System.out.println("Thread 1 done");
        });
        Thread t2 = new Thread(() -> {
            for (int i = 0; i < 100; i++) {
                counter.growScale();
            }
            System.out.println("Thread 2 done");
        });
        t1.start();
        t2.start();
        try {
            t1.join();
            t2.join();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
        System.out.println("Scale count: " + counter.getScaleCount());
    }
}

class MysticCAS {
    private int value;

    public synchronized int get() {
        return value;
    }

    public synchronized int compareAndSwap(int expected, int newValue) {
        int old = value;
        if (value == expected) {
            value = newValue;
        }
        return old;
    }
}

class DragonScaleCounter {
    private final MysticCAS cas = new MysticCAS();

    public int getScaleCount() {
        return cas.get();
    }

    public void growScale() {
        int old;
        int newValue;
        do {
            old = cas.get();
            newValue = old + 1;
        } while (cas.compareAndSwap(old, newValue) != old);
    }
}
