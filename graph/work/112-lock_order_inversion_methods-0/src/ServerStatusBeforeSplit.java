import java.util.*;
public class ServerStatusBeforeSplit {
    private static final Object __auxLock = new Object();
    private final Set<String> users = new HashSet<>();
    private final Set<String> queries = new HashSet<>();
    public synchronized void addUser(String u) {
        synchronized (__auxLock) {
            users.add(u);
        }
    }
    public void addQuery(String q) {
        synchronized (__auxLock) {
            synchronized (this) {
                queries.add(q);
            }
        }
    }
    public synchronized void removeUser(String u) {
        users.remove(u);
    }
    public synchronized void removeQuery(String q) {
        queries.remove(q);
    }
    public static void main(String[] args) throws Exception {
        ServerStatusBeforeSplit status = new ServerStatusBeforeSplit();
        Thread t1 = new Thread(() -> {
            status.addUser(String.valueOf(1));
        });
        Thread t2 = new Thread(() -> {
            status.addQuery(String.valueOf(2));
        });
        t1.start();
        t2.start();
        t1.join();
        t2.join();
    }
}
