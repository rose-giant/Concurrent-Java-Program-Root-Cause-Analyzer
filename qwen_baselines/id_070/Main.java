public class Main {
    public static void main(String[] args) {
        Thread t1 = new Thread(() -> {
            ArcaneSource source = new ArcaneSource();
            MysticWatcher watcher = MysticWatcher.summonInstance(source);
            System.out.println("Watcher created");
        });
        t1.start();
        try {
            t1.join();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }
}

interface ArcaneSource {
}

interface ArcaneListener {
    void onMysticEvent();
}

interface MysticEvent {
}

class MysticWatcher {
    private MysticWatcher() {
    }

    public static MysticWatcher summonInstance(ArcaneSource source) {
        MysticWatcher watcher = new MysticWatcher();
        ArcaneListener listener = new ArcaneListener() {
            public void onMysticEvent() {
                watcher.castSpell();
            }
        };
        return watcher;
    }

    void castSpell() {
        System.out.println("Spell cast");
    }
}
