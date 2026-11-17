import java.util.*;
public class ServerStatusAfterSplit {
    private final Set<String> users = new HashSet<>();
    private final Set<String> queries = new HashSet<>();
    public void addUser(String u) {
        synchronized (users) {
            synchronized (queries) {
                users.add(u);
            }
        }
    }
    public void addQuery(String q) {
        synchronized (queries) {
            synchronized (users) {
                queries.add(q);
            }
        }
    }
    public void removeUser(String u) {
        synchronized (users) {
            users.remove(u);
        }
    }
    public void removeQuery(String q) {
        synchronized (queries) {
            queries.remove(q);
        }
    }
    public static void main(String[] args) throws Exception {
        ServerStatusAfterSplit status = new ServerStatusAfterSplit();
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
