public class CountingLanterns {
    private boolean asleep = false;
    private final Object asleepLock = new Object();
    public void tryToSleep() {
        while (true) {
            boolean isAsleep;
            synchronized (asleepLock) {
                isAsleep = asleep;
            }
            if (isAsleep) {
                break;
            }
            countSomeSheep();
        }
    }
    private void countSomeSheep() {
        System.out.println("Tallying a lantern...");
        try {
            Thread.sleep(100);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }
    public void setAsleep(boolean value) {
        synchronized (asleepLock) {
            this.asleep = value;
        }
    }
    public static void main(String[] args) {
        CountingLanterns traveler = new CountingLanterns();
        Thread t1 = new Thread(() -> traveler.tryToSleep());
        Thread t2 = new Thread(() -> {
            try {
                Thread.sleep(500);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
            traveler.setAsleep(true);
        });
        t1.start();
        t2.start();
        try {
            t2.join();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }
}
