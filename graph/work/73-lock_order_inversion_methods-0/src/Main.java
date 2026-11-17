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
    private static final Object __auxLock = new Object();
    private int value;
    public synchronized int get() {
        synchronized (__auxLock) {
            return value;
        }
    }
    public void set(int v) {
        synchronized (__auxLock) {
            synchronized (this) {
                value = v;
            }
        }
    }
}
