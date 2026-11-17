import java.util.concurrent.*; 

class Sleeper { 
    volatile boolean asleep; 
    
    void tryToSleep() { 
        while (!asleep) countSomeSheep(); 
        } 
        
        void countSomeSheep() { 
            try { 
                Thread.sleep(1); 
            } catch (InterruptedException e) { 
                Thread.currentThread().interrupt(); 
                } 
                } 
                } 


public class Main { 
    public static void main(String[] args) throws Exception { 
        Sleeper sleeper = new Sleeper(); 
        ExecutorService es = Executors.newFixedThreadPool(2); 
        
        es.execute(() -> { 
            sleeper.tryToSleep(); 
        }); 
        
        es.execute(() -> { 
            try { 
                Thread.sleep(10); 
            } catch (InterruptedException e) { 
                Thread.currentThread().interrupt(); 
            } sleeper.asleep = true; 
        }); 
        
        es.shutdown(); 
        es.awaitTermination(2, TimeUnit.SECONDS); 
    } 
}

//still problematic