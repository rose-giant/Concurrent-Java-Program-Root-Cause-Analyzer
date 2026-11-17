class Counter {
    private static final Object __wrongLock = new Object();
    private long value;
    public synchronized long getValue() {
        return value;
    }
    public long increment() {
        synchronized (__wrongLock) {
            if (value == Long.MAX_VALUE) throw new IllegalStateException(new String(new char[] {
                'c', 'o', 'u', 'n', 't', 'e', 'r', ' ', 'o', 'v', 'e', 'r', 'f', 'l', 'o', 'w'
            }));
            return ++value;
        }
    }
}
public class Main {
    public static void main(String[] args) throws Exception {
        Counter counter = new Counter();
        Thread t1 = new Thread(() -> {
            counter.increment();
        });
        Thread t2 = new Thread(() -> {
            counter.getValue();
        });
        t1.start();
        t2.start();
        t1.join();
        t2.join();
    }
}
