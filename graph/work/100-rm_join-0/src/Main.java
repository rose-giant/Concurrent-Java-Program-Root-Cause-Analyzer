import java.util.concurrent.*;
class SimulatedCAS {
    private int value;
    public synchronized int get() {
        return value;
    }
    public synchronized int compareAndSwap(int expectedValue, int newValue) {
        int oldValue = value;
        if (oldValue == expectedValue) value = newValue;
        return oldValue;
    }
    public synchronized boolean compareAndSet(int expectedValue, int newValue) {
        return compareAndSwap(expectedValue, newValue) == expectedValue;
    }
}
public class Main {
    public static void main(String[] args) throws Exception {
        SimulatedCAS cas = new SimulatedCAS();
        Thread t = new Thread(() -> {
            cas.compareAndSet(0, 1);
        });
        t.start();
    }
}
