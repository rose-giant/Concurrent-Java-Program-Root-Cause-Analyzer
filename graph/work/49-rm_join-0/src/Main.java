import java.util.HashMap;
import java.util.Map;
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
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }
}
class CrystalCache {
    private final Map<String, String> map;
    public CrystalCache(Map<String, String> map) {
        this.map = new HashMap<>(map);
    }
    public synchronized String put(String key, String value) {
        return map.put(key, value);
    }
    public synchronized String remove(Object key) {
        return map.remove(key);
    }
    public synchronized void putAll(Map<String, String> m) {
        map.putAll(m);
    }
    public synchronized void clear() {
        map.clear();
    }
    public synchronized String get(Object key) {
        return map.get(key);
    }
    public synchronized int size() {
        return map.size();
    }
    public synchronized boolean isEmpty() {
        return map.isEmpty();
    }
    public synchronized boolean containsKey(Object key) {
        return map.containsKey(key);
    }
    public synchronized boolean containsValue(Object value) {
        return map.containsValue(value);
    }
}
