public class Main {
    public static void main(String[] args) throws Exception {
        IntHolder holder = new IntHolder();
        Thread t1 = new Thread(new Runnable() {
            @Override public void run() {
                holder.set(1);
            }
        });
        Thread t2 = new Thread(new Runnable() {
            @Override public void run() {
                holder.get();
            }
        });
        t1.start();
        t2.start();
        t1.join();
        t2.join();
    }
}
class IntHolder {
    private static final Object __wrongLock = new Object();
    private int value;
    public synchronized int get() {
        return value;
    }
    public void set(int v) {
        synchronized (__wrongLock) {
            value = v;
        }
    }
}
