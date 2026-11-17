import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class Main {
    public static void main(String[] args) throws Exception {
        VaultNode nodeA = new SimpleVaultNode(100);
        VaultNode nodeB = new SimpleVaultNode(100);
        ExecutorService executor = Executors.newFixedThreadPool(2);
        executor.submit(() -> {
            try {
                transferCrystals(nodeA, nodeB, new CrystalAmount(10));
            } catch (InsufficientCrystalsException e) {
                System.out.println(e.getMessage());
            }
        });
        executor.submit(() -> {
            try {
                transferCrystals(nodeB, nodeA, new CrystalAmount(5));
            } catch (InsufficientCrystalsException e) {
                System.out.println(e.getMessage());
            }
        });
        executor.shutdown();
        executor.awaitTermination(5, TimeUnit.SECONDS);
        System.out.println("Done");
    }

    interface VaultNode {
        int getBalance();
        void withdraw(int amount);
        void deposit(int amount);
    }

    interface CrystalAmount {
        int getValue();
    }

    static class SimpleCrystalAmount implements CrystalAmount {
        private final int value;
        SimpleCrystalAmount(int value) { this.value = value; }
        public int getValue() { return value; }
    }

    static class SimpleVaultNode implements VaultNode {
        private int balance;
        SimpleVaultNode(int balance) { this.balance = balance; }
        public synchronized int getBalance() { return balance; }
        public synchronized void withdraw(int amount) { balance -= amount; }
        public synchronized void deposit(int amount) { balance += amount; }
    }

    static class InsufficientCrystalsException extends Exception {
        InsufficientCrystalsException(String msg) { super(msg); }
    }

    private static final Object tieLock = new Object();

    static class TransferRite {
        static void execute(VaultNode from, VaultNode to, CrystalAmount amount) throws InsufficientCrystalsException {
            if (from.getBalance() < amount.getValue()) {
                throw new InsufficientCrystalsException("Insufficient crystals");
            }
            from.withdraw(amount.getValue());
            to.deposit(amount.getValue());
        }
    }

    public static void transferCrystals(VaultNode from, VaultNode to, CrystalAmount amount) throws InsufficientCrystalsException {
        int fromHash = System.identityHashCode(from);
        int toHash = System.identityHashCode(to);
        if (fromHash < toHash) {
            synchronized (from) {
                synchronized (to) {
                    TransferRite.execute(from, to, amount);
                }
            }
        } else if (fromHash > toHash) {
            synchronized (to) {
                synchronized (from) {
                    TransferRite.execute(from, to, amount);
                }
            }
        } else {
            synchronized (tieLock) {
                synchronized (from) {
                    synchronized (to) {
                        TransferRite.execute(from, to, amount);
                    }
                }
            }
        }
    }
}
