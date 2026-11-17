public class BarrierTimer implements Runnable {
    private boolean started;
    private long startTime;
    private long endTime;
    public synchronized void run() {
        long now = System.nanoTime();
        if (!started) {
            started = true;
            startTime = now;
        } else {
            endTime = now;
        }
    }
    public synchronized void clear() {
        started = false;
    }
    public synchronized long getTime() {
        return endTime - startTime;
    }
    public static void main(String[] args) throws Exception {
        BarrierTimer timer = new BarrierTimer();
        Thread t1 = new Thread(() -> {
            timer.run();
        });
        Thread t2 = new Thread(() -> {
            timer.run();
        });
        t1.start();
        t2.start();
        t2.join();
        timer.getTime();
        timer.clear();
    }
}
