import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;

public class Main {
    public static void main(String[] args) {
        List<Rune> candidates = new ArrayList<>();
        candidates.add(new Rune(Constellation.ARIES, Resonance.POSITIVE));
        candidates.add(new Rune(Constellation.ARIES, Resonance.NEGATIVE));
        candidates.add(new Rune(Constellation.LEO, Resonance.POSITIVE));
        candidates.add(new Rune(Constellation.LEO, Resonance.NEGATIVE));
        Thread t1 = new Thread(() -> {
            int count = channelTheGrimoire(candidates);
            System.out.println("Harmonies formed: " + count);
        });
        Thread t2 = new Thread(() -> {
            int count = channelTheGrimoire(candidates);
            System.out.println("Harmonies formed: " + count);
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

    static int channelTheGrimoire(List<Rune> candidates) {
        List<Rune> localRunes = new ArrayList<>(candidates);
        Collections.sort(localRunes, Comparator.comparing((Rune r) -> r.constellation).thenComparing(r -> r.resonance));
        int harmonyCount = 0;
        Grimoire grimoire = new Grimoire();
        for (int i = 0; i < localRunes.size() - 1; i++) {
            Rune a = localRunes.get(i);
            Rune b = localRunes.get(i + 1);
            if (a.constellation == b.constellation && a.resonance != b.resonance) {
                grimoire.crystallize(new Harmony(a, b));
                harmonyCount++;
                i++;
            }
        }
        return harmonyCount;
    }

    enum Constellation { ARIES, LEO }
    enum Resonance { POSITIVE, NEGATIVE }

    static class Rune {
        final Constellation constellation;
        final Resonance resonance;
        Rune(Constellation constellation, Resonance resonance) {
            this.constellation = constellation;
            this.resonance = resonance;
        }
    }

    static class Harmony {
        final Rune first;
        final Rune second;
        Harmony(Rune first, Rune second) {
            this.first = first;
            this.second = second;
        }
    }

    static class Grimoire {
        private final List<Harmony> harmonies = new ArrayList<>();
        void crystallize(Harmony h) {
            harmonies.add(h);
        }
    }
}
