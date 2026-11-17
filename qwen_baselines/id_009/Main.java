import java.util.Collections;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public class Main {
    public static void main(String[] args) {
        Map<String, String> initial = new HashMap<>();
        initial.put("R1", "Zone A");
        initial.put("R2", "Zone B");
        DelegatingRobotTracker tracker = new DelegatingRobotTracker(initial);
        Thread t1 = new Thread(() -> {
            tracker.modifyCoordinates("R1", "Zone C");
            System.out.println("R1 coordinates: " + tracker.checkCoordinates("R1"));
        });
        Thread t2 = new Thread(() -> {
            Map<String, String> snapshot = tracker.getAllCoordinatesStatic();
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

class DelegatingRobotTracker {
    private final ConcurrentHashMap<String, String> coordinates;

    public DelegatingRobotTracker(Map<String, String> initial) {
        this.coordinates = new ConcurrentHashMap<>(initial);
    }

    public String checkCoordinates(String robotId) {
        return coordinates.get(robotId);
    }

    public boolean modifyCoordinates(String robotId, String coord) {
        if (!coordinates.containsKey(robotId)) {
            return false;
        }
        coordinates.put(robotId, coord);
        return true;
    }

    public Map<String, String> getAllCoordinatesLive() {
        return Collections.unmodifiableMap(coordinates);
    }

    public Map<String, String> getAllCoordinatesStatic() {
        return Collections.unmodifiableMap(new HashMap<>(coordinates));
    }
}
