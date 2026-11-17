import java.util.Collections;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public class Main {
    public static void main(String[] args) {
        Map<String, String> initial = new HashMap<>();
        initial.put("P1", "Warehouse");
        initial.put("P2", "Transit");
        DelegatingParcelTracker tracker = new DelegatingParcelTracker(initial);
        Thread t1 = new Thread(() -> {
            tracker.assignPosition("P1", "Delivered");
            System.out.println("P1 position: " + tracker.retrievePosition("P1"));
        });
        Thread t2 = new Thread(() -> {
            Map<String, String> snapshot = tracker.getAllPositionsStatic();
            System.out.println("Snapshot: " + snapshot);
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

class DelegatingParcelTracker {
    private final ConcurrentHashMap<String, String> positions;

    public DelegatingParcelTracker(Map<String, String> initial) {
        this.positions = new ConcurrentHashMap<>(initial);
    }

    public String retrievePosition(String packageId) {
        return positions.get(packageId);
    }

    public boolean assignPosition(String packageId, String position) {
        if (!positions.containsKey(packageId)) {
            return false;
        }
        positions.put(packageId, position);
        return true;
    }

    public Map<String, String> getAllPositionsLive() {
        return Collections.unmodifiableMap(positions);
    }

    public Map<String, String> getAllPositionsStatic() {
        return Collections.unmodifiableMap(new HashMap<>(positions));
    }
}
