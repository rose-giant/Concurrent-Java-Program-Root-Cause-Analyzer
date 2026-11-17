public class CountingFireflies {
    private volatile boolean asleep = false;

    public void tryToSleep() {
        while (!asleep) {
            countSomeSheep();
        }
    }

    private void countSomeSheep() {
        System.out.println("Observing a firefly...");
        try {
            Thread.sleep(100);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    public void setAsleep(boolean value) {
        this.asleep = value;
    }

    public static void main(String[] args) {
        CountingFireflies scout = new CountingFireflies();
        Thread t1 = new Thread(() -> scout.tryToSleep());
        Thread t2 = new Thread(() -> {
            try {
                Thread.sleep(500);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
            scout.setAsleep(true);
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
