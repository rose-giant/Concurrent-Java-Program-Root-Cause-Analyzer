import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class Main {
    public static void main(String[] args) throws Exception {
        Hoard hoardA = new SimpleHoard(100);
        Hoard hoardB = new SimpleHoard(100);
        ExecutorService executor = Executors.newFixedThreadPool(2);
        executor.submit(() -> {
            try {
                transferGems(hoardA, hoardB, new GemAmount(10));
            } catch (InsufficientGemsException e) {
                System.out.println(e.getMessage());
            }
        });
        executor.submit(() -> {
            try {
                transferGems(hoardB, hoardA, new GemAmount(5));
            } catch (InsufficientGemsException e) {
                System.out.println(e.getMessage());
            }
        });
        executor.shutdown();
        executor.awaitTermination(5, TimeUnit.SECONDS);
        System.out.println("Done");
    }

    interface Hoard {
        int getBalance();
        void withdraw(int amount);
        void deposit(int amount);
    }

    interface GemAmount {
        int getValue();
    }

    static class SimpleGemAmount implements GemAmount {
        private final int value;
        SimpleGemAmount(int value) { this.value = value; }
        public int getValue() { return value; }
    }

    static class SimpleHoard implements Hoard {
        private int balance;
        SimpleHoard(int balance) { this.balance = balance; }
        public synchronized int getBalance() { return balance; }
        public synchronized void withdraw(int amount) { balance -= amount; }
        public synchronized void deposit(int amount) { balance += amount; }
    }

    static class InsufficientGemsException extends Exception {
        InsufficientGemsException(String msg) { super(msg); }
    }

    private static final Object tieLock = new Object();

    static class TransferRitual {
        static void execute(Hoard from, Hoard to, GemAmount amount) throws InsufficientGemsException {
            if (from.getBalance() < amount.getValue()) {
                throw new InsufficientGemsException("Insufficient gems");
            }
            from.withdraw(amount.getValue());
            to.deposit(amount.getValue());
        }
    }

    public static void transferGems(Hoard from, Hoard to, GemAmount amount) throws InsufficientGemsException {
        int fromHash = System.identityHashCode(from);
        int toHash = System.identityHashCode(to);
        if (fromHash < toHash) {
            synchronized (from) {
                synchronized (to) {
                    TransferRitual.execute(from, to, amount);
                }
            }
        } else if (fromHash > toHash) {
            synchronized (to) {
                synchronized (from) {
                    TransferRitual.execute(from, to, amount);
                }
            }
        } else {
            synchronized (tieLock) {
                synchronized (from) {
                    synchronized (to) {
                        TransferRitual.execute(from, to, amount);
                    }
                }
            }
        }
    }
}
