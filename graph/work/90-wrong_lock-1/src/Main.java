import java.math.BigInteger;
import java.util.*;
import java.util.concurrent.*;
class PrimeGenerator implements Runnable {
    private static final Object __wrongLock = new Object();
    private volatile boolean cancelled;
    private final List<BigInteger> primes = Collections.synchronizedList(new ArrayList<>());
    public void run() {
        BigInteger current = BigInteger.ONE;
        long end = System.currentTimeMillis() + 1000;
        while (!isCancelled() && System.currentTimeMillis() < end) {
            current = current.nextProbablePrime();
            primes.add(current);
        }
    }
    boolean isCancelled() {
        synchronized (__wrongLock) {
            return cancelled;
        }
    }
    synchronized void cancel() {
        cancelled = true;
    }
    List<BigInteger> getPrimes() {
        return primes;
    }
}
public class Main {
    public static void main(String[] args) throws Exception {
        ExecutorService es = Executors.newFixedThreadPool(1);
        PrimeGenerator generator = new PrimeGenerator();
        Future<?> future = es.submit(generator);
        Thread.sleep(1000);
        generator.cancel();
        future.get();
        es.shutdown();
        generator.getPrimes();
    }
}
