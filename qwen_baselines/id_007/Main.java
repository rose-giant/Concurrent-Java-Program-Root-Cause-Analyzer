import java.util.Collections;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public class Main {
    public static void main(String[] args) {
        Map<String, String> initial = new HashMap<>();
        initial.put("G1", "Room1");
        initial.put("G2", "Room2");
        DelegatingDeviceTracker tracker = new DelegatingDeviceTracker(initial);
        Thread t1 = new Thread(() -> {
            tracker.updatePosition("G1", "Room3");
            System.out.println("G1 position: " + tracker.fetchPosition("G1"));
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

class DelegatingDeviceTracker {
    private final ConcurrentHashMap<String, String> positions;

    public DelegatingDeviceTracker(Map<String, String> initial) {
        this.positions = new ConcurrentHashMap<>(initial);
    }

    public String fetchPosition(String gadgetId) {
        return positions.get(gadgetId);
    }

    public boolean updatePosition(String gadgetId, String position) {
        if (!positions.containsKey(gadgetId)) {
            return false;
        }
        positions.put(gadgetId, position);
        return true;
    }

    public Map<String, String> getAllPositionsLive() {
        return Collections.unmodifiableMap(positions);
    }

    public Map<String, String> getAllPositionsStatic() {
        return Collections.unmodifiableMap(new HashMap<>(positions));
    }
}
