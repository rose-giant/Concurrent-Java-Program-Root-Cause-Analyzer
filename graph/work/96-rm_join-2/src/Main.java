class StripedMap {
    static final int N_LOCKS = 16;
    private final Node[] buckets;
    private final Object[] locks;
    static class Node {
        Object key;
        Object value;
        Node next;
        Node(Object key, Object value, Node next) {
            this.key = key;
            this.value = value;
            this.next = next;
        }
    }
    StripedMap(int bucketCount) {
        buckets = new Node[bucketCount];
        locks = new Object[N_LOCKS];
        for (int i = 0; i < N_LOCKS; i++) locks[i] = new Object();
    }
    int hashIndex(Object key) {
        return (key.hashCode() & 0x7fffffff) % buckets.length;
    }
    Object get(Object key) {
        int index = hashIndex(key);
        synchronized (locks[index % N_LOCKS]) {
            Node node = buckets[index];
            while (node != null) {
                if (node.key.equals(key)) return node.value;
                node = node.next;
            }
            return null;
        }
    }
    void put(Object key, Object value) {
        int index = hashIndex(key);
        synchronized (locks[index % N_LOCKS]) {
            buckets[index] = new Node(key, value, buckets[index]);
        }
    }
    void clear() {
        for (int i = 0; i < buckets.length; i++) {
            synchronized (locks[i % N_LOCKS]) {
                buckets[i] = null;
            }
        }
    }
}
public class Main {
    public static void main(String[] args) throws Exception {
        StripedMap map = new StripedMap(4);
        Thread t1 = new Thread(() -> {
            map.put(1, 2);
        });
        Thread t2 = new Thread(() -> {
            map.get(1);
        });
        Thread t3 = new Thread(() -> {
            map.put(3, 4);
        });
        Thread t4 = new Thread(() -> {
            map.clear();
        });
        t1.start();
        t2.start();
        t3.start();
        t4.start();
        t1.join();
        t2.join();
        t4.join();
    }
}
