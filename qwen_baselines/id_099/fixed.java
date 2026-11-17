import java.util.*;
import java.util.concurrent.*;

class ReadWriteMap<K, V> {
    private final Map<K, V> map;

    ReadWriteMap(Map<K, V> map) {
        this.map = map;
    }

    public synchronized V put(K key, V value) {
        return map.put(key, value);
    }

    public synchronized V remove(Object key) {
        return map.remove(key);
    }

    public synchronized void putAll(Map<? extends K, ? extends V> m) {
        map.putAll(m);
    }

    public synchronized void clear() {
        map.clear();
    }

    public synchronized V get(Object key) {
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

public class Main {
    public static void main(String[] args) throws Exception {
        ReadWriteMap<Integer, Integer> map =
            new ReadWriteMap<>(new HashMap<>());

        ExecutorService es = Executors.newFixedThreadPool(3);

        es.execute(() -> {
            map.put(1, 1);
        });

        es.execute(() -> {
            map.get(1);
        });

        es.execute(() -> {
            map.size();
        });

        es.shutdown();
        es.awaitTermination(1, TimeUnit.SECONDS);
    }
}
