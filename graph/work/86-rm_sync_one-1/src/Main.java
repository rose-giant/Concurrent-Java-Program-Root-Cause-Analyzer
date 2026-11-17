import java.util.*;
import java.util.concurrent.*;
class SafePoint {
    public volatile int x;
    public volatile int y;
    SafePoint(int x, int y) {
        this.x = x;
        this.y = y;
    }
}
class PublishingVehicleTracker {
    private final ConcurrentHashMap<String, SafePoint> locations;
    PublishingVehicleTracker(Map<String, SafePoint> initial) {
        locations = new ConcurrentHashMap<>(initial);
    }
    Map<String, SafePoint> getLocations() {
        return Collections.unmodifiableMap(locations);
    }
    synchronized SafePoint getLocation(String id) {
        SafePoint p = locations.get(id);
        return p == null ? null : new SafePoint(p.x, p.y);
    }
    void setLocation(String id, int x, int y) {
        SafePoint p = locations.get(id);
        if (p == null) throw new IllegalArgumentException();
        p.x = x;
        p.y = y;
    }
}
public class Main {
    public static void main(String[] args) throws Exception {
        Map<String, SafePoint> initial = new HashMap<>();
        initial.put(String.valueOf(1), new SafePoint(0, 0));
        PublishingVehicleTracker tracker = new PublishingVehicleTracker(initial);
        ExecutorService es = Executors.newFixedThreadPool(2);
        es.execute(() -> {
            tracker.setLocation(String.valueOf(1), 2, 2);
        });
        es.execute(() -> {
            tracker.getLocation(String.valueOf(1));
        });
        es.shutdown();
        es.awaitTermination(1, TimeUnit.SECONDS);
    }
}
