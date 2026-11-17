class Counter {
    private static final Object __auxLock = new Object();
    private long value;
    public synchronized long getValue() {
        synchronized (__auxLock) {
            return value;
        }
    }
    public long increment() {
        synchronized (__auxLock) {
            synchronized (this) {
                if (value == Long.MAX_VALUE) throw new IllegalStateException(new String(new char[] {
                    'c', 'o', 'u', 'n', 't', 'e', 'r', ' ', 'o', 'v', 'e', 'r', 'f', 'l', 'o', 'w'
                }));
                return ++value;
            }
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
