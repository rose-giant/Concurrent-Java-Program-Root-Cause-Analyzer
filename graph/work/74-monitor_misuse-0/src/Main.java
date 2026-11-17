class Sleeper {
    private boolean asleep;
    void tryToSleep() throws InterruptedException {
        while (!asleep) {
            wait();
        }
    }
    synchronized void setAsleep() {
        asleep = true;
        notifyAll();
    }
}
public class Main {
    public static void main(String[] args) throws Exception {
        Sleeper sleeper = new Sleeper();
        Thread reader = new Thread(() -> {
            try {
                sleeper.tryToSleep();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });
        Thread writer = new Thread(sleeper::setAsleep);
        reader.start();
        writer.start();
        reader.join();
        writer.join();
    }
}
