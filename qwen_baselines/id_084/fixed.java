import java.util.*;

class Point {
    public final int x;
    public final int y;

    Point(int x, int y) {
        this.x = x;
        this.y = y;
    }
}

class DelegatingVehicleTracker {
    private final java.util.concurrent.ConcurrentHashMap<String, Point> locations;

    DelegatingVehicleTracker(Map<String, Point> initial) {
        locations = new java.util.concurrent.ConcurrentHashMap<>(initial);
    }

    Map<String, Point> getLocations() {
        return Collections.unmodifiableMap(locations);
    }

    Point getLocation(String id) {
        return locations.get(id);
    }

    void setLocation(String id, int x, int y) {
        if (locations.replace(id, new Point(x, y)) == null)
            throw new IllegalArgumentException();
    }

    Map<String, Point> getLocationsAsStatic() {
        return Collections.unmodifiableMap(new HashMap<>(locations));
    }
}

public class Main {
    public static void main(String[] args) throws Exception {
        Map<String, Point> initial = new HashMap<>();
        initial.put(String.valueOf(1), new Point(0, 0));

        final DelegatingVehicleTracker tracker =
            new DelegatingVehicleTracker(initial);

        Thread t1 = new Thread(new Runnable() {
            public void run() {
                tracker.setLocation(String.valueOf(1), 1, 1);
            }
        });

        Thread t2 = new Thread(new Runnable() {
            public void run() {
                tracker.getLocation(String.valueOf(1));
            }
        });

        Thread t3 = new Thread(new Runnable() {
            public void run() {
                tracker.getLocations();
            }
        });

        Thread t4 = new Thread(new Runnable() {
            public void run() {
                tracker.getLocationsAsStatic();
            }
        });

        Thread t5 = new Thread(new Runnable() {
            public void run() {
                tracker.getLocation(String.valueOf(2));
            }
        });

        t1.start();
        t2.start();
        t3.start();
        t4.start();
        t5.start();

        t1.join();
        t2.join();
        t3.join();
        t4.join();
        t5.join();
    }
}

