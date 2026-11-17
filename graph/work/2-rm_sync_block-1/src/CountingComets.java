public class CountingComets {
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
        System.out.println("Surveying a comet...");
        try {
            Thread.sleep(100);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }
    public void setAsleep(boolean value) {
        {
            this.asleep = value;
        }
    }
    public static void main(String[] args) {
        CountingComets wanderer = new CountingComets();
        Thread t1 = new Thread(() -> wanderer.tryToSleep());
        Thread t2 = new Thread(() -> {
            try {
                Thread.sleep(500);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
            wanderer.setAsleep(true);
        });
        t1.start();
        t2.start();
        try {
            t1.join();
            t2.join();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }
}
