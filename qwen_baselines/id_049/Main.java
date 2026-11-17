import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.locks.ReentrantReadWriteLock;

public class Main {
    public static void main(String[] args) {
        Map<String, String> base = new HashMap<>();
        base.put("R1", "Sword");
        CrystalCache cache = new CrystalCache(base);
        Thread t1 = new Thread(() -> {
            cache.put("R2", "Shield");
            System.out.println("Put R2");
        });
        Thread t2 = new Thread(() -> {
            String val = cache.get("R1");
            System.out.println("Get R1: " + val);
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

class CrystalCache {
    private final Map<String, String> map;
    private final ReentrantReadWriteLock lock = new ReentrantReadWriteLock();

    public CrystalCache(Map<String, String> map) {
        this.map = new HashMap<>(map);
    }

    public String put(String key, String value) {
        lock.writeLock().lock();
        try {
            return map.put(key, value);
        } finally {
            lock.writeLock().unlock();
        }
    }

    public String remove(Object key) {
        lock.writeLock().lock();
        try {
            return map.remove(key);
        } finally {
            lock.writeLock().unlock();
        }
    }

    public void putAll(Map<String, String> m) {
        lock.writeLock().lock();
        try {
            map.putAll(m);
        } finally {
            lock.writeLock().unlock();
        }
    }

    public void clear() {
        lock.writeLock().lock();
        try {
            map.clear();
        } finally {
            lock.writeLock().unlock();
        }
    }

    public String get(Object key) {
        lock.readLock().lock();
        try {
            return map.get(key);
        } finally {
            lock.readLock().unlock();
        }
    }

    public int size() {
        lock.readLock().lock();
        try {
            return map.size();
        } finally {
            lock.readLock().unlock();
        }
    }

    public boolean isEmpty() {
        lock.readLock().lock();
        try {
            return map.isEmpty();
        } finally {
            lock.readLock().unlock();
        }
    }

    public boolean containsKey(Object key) {
        lock.readLock().lock();
        try {
            return map.containsKey(key);
        } finally {
            lock.readLock().unlock();
        }
    }

    public boolean containsValue(Object value) {
        lock.readLock().lock();
        try {
            return map.containsValue(value);
        } finally {
            lock.readLock().unlock();
        }
    }
}
