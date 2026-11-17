import java.math.BigInteger;
import java.util.*;
import java.util.concurrent.*;
class PrimeGenerator implements Runnable {
    private static final Object __wrongLock = new Object();
    private boolean cancelled;
    // guarded by "this"
    private final List<BigInteger> primes = Collections.synchronizedList(new ArrayList<>());
    private final ExecutorService executor = Executors.newFixedThreadPool(1);
    private synchronized boolean isCancelled() {
        return cancelled;
    }
    private void setCancelled() {
        synchronized (__wrongLock) {
            cancelled = true;
        }
    }
    public void run() {
        BigInteger current = BigInteger.ONE;
        long end = System.currentTimeMillis() + 1000;
        while (!isCancelled() && primes.size() < 10 && System.currentTimeMillis() < end) {
            current = current.nextProbablePrime();
            primes.add(current);
        }
    }
    void start() {
        executor.submit(this);
    }
    void cancel() {
        setCancelled();
        // synchronized write
        executor.shutdown();
    }
    List<BigInteger> getPrimes() {
        return primes;
    }
}
public class Main {
    public static void main(String[] args) throws Exception {
        PrimeGenerator generator = new PrimeGenerator();
        generator.start();
        Thread.sleep(1000);
        generator.cancel();
        generator.getPrimes();
    }
}
