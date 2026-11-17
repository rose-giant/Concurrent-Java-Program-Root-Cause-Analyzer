class Counter {
    private long value;
    public long getValue() {
        return value;
    }
    public synchronized long increment() {
        if (value == Long.MAX_VALUE) throw new IllegalStateException(new String(new char[] {
            'c', 'o', 'u', 'n', 't', 'e', 'r', ' ', 'o', 'v', 'e', 'r', 'f', 'l', 'o', 'w'
        }));
        return ++value;
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
