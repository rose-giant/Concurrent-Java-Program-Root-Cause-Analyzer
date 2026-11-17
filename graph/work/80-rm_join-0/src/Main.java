import java.math.BigInteger;
import java.util.*;
class OneValueCache {
    private final BigInteger lastNumber;
    private final BigInteger[] lastFactors;
    OneValueCache(BigInteger number, BigInteger[] factors) {
        lastNumber = number;
        lastFactors = Arrays.copyOf(factors, factors.length);
    }
    BigInteger[] getFactors(BigInteger number) {
        if (!lastNumber.equals(number)) return null;
        return Arrays.copyOf(lastFactors, lastFactors.length);
    }
}
class Factorizer {
    private volatile OneValueCache cache = new OneValueCache(BigInteger.ONE, new BigInteger[] {
        BigInteger.ONE
    });
    synchronized BigInteger[] service(BigInteger input) {
        BigInteger[] factors = cache.getFactors(input);
        if (factors == null) {
            factors = new BigInteger[] {
                input
            };
            cache = new OneValueCache(input, factors);
        }
        return factors;
    }
}
public class Main {
    public static void main(String[] args) throws Exception {
        Factorizer factorizer = new Factorizer();
        Thread t1 = new Thread(() -> {
            factorizer.service(BigInteger.ONE);
        });
        Thread t2 = new Thread(() -> {
            factorizer.service(BigInteger.valueOf(2));
        });
        t1.start();
        t2.start();
        t2.join();
    }
}
