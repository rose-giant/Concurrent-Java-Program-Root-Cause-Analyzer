class CasCounter {
    private final SimulatedCAS cas = new SimulatedCAS();
    public int getValue() {
        return cas.get();
    }
    public int increment() {
        int oldValue;
        do {
            oldValue = cas.get();
        }
        while (cas.compareAndSwap(oldValue, oldValue + 1) != oldValue);
        return oldValue + 1;
    }
    static class SimulatedCAS {
        private static final Object __auxLock = new Object();
        private int value;
        public synchronized int get() {
            synchronized (__auxLock) {
                return value;
            }
        }
        public int compareAndSwap(int expectedValue, int newValue) {
            synchronized (__auxLock) {
                synchronized (this) {
                    int oldValue = value;
                    if (oldValue == expectedValue) value = newValue;
                    return oldValue;
                }
            }
        }
    }
    public static void main(String[] args) throws Exception {
        CasCounter counter = new CasCounter();
        Thread t1 = new Thread(() -> {
            counter.increment();
        });
        Thread t2 = new Thread(() -> {
            counter.increment();
        });
        t1.start();
        t2.start();
        t1.join();
        t2.join();
    }
}
