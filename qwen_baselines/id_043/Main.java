import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class Main {
    public static void main(String[] args) throws Exception {
        Vault vaultA = new SimpleVault(100);
        Vault vaultB = new SimpleVault(100);
        ExecutorService executor = Executors.newFixedThreadPool(2);
        executor.submit(() -> {
            try {
                transferGold(vaultA, vaultB, new GoldAmount(10));
            } catch (InsufficientTreasureException e) {
                System.out.println(e.getMessage());
            }
        });
        executor.submit(() -> {
            try {
                transferGold(vaultB, vaultA, new GoldAmount(5));
            } catch (InsufficientTreasureException e) {
                System.out.println(e.getMessage());
            }
        });
        executor.shutdown();
        executor.awaitTermination(5, TimeUnit.SECONDS);
        System.out.println("Done");
    }

    interface Vault {
        int getBalance();
        void debit(int amount);
        void credit(int amount);
    }

    interface GoldAmount {
        int getValue();
    }

    static class SimpleGoldAmount implements GoldAmount {
        private final int value;
        SimpleGoldAmount(int value) { this.value = value; }
        public int getValue() { return value; }
    }

    static class SimpleVault implements Vault {
        private int balance;
        SimpleVault(int balance) { this.balance = balance; }
        public synchronized int getBalance() { return balance; }
        public synchronized void debit(int amount) { balance -= amount; }
        public synchronized void credit(int amount) { balance += amount; }
    }

    static class InsufficientTreasureException extends Exception {
        InsufficientTreasureException(String msg) { super(msg); }
    }

    private static final Object tieLock = new Object();

    static class TransferHelper {
        static void execute(Vault from, Vault to, GoldAmount amount) throws InsufficientTreasureException {
            if (from.getBalance() < amount.getValue()) {
                throw new InsufficientTreasureException("Insufficient treasure");
            }
            from.debit(amount.getValue());
            to.credit(amount.getValue());
        }
    }

    public static GoldAmount newGoldAmount(int value) {
        return new SimpleGoldAmount(value);
    }

    public static void transferGold(Vault from, Vault to, GoldAmount amount) throws InsufficientTreasureException {
        int fromHash = System.identityHashCode(from);
        int toHash = System.identityHashCode(to);
        if (fromHash < toHash) {
            synchronized (from) {
                synchronized (to) {
                    TransferHelper.execute(from, to, amount);
                }
            }
        } else if (fromHash > toHash) {
            synchronized (to) {
                synchronized (from) {
                    TransferHelper.execute(from, to, amount);
                }
            }
        } else {
            synchronized (tieLock) {
                synchronized (from) {
                    synchronized (to) {
                        TransferHelper.execute(from, to, amount);
                    }
                }
            }
        }
    }
}
