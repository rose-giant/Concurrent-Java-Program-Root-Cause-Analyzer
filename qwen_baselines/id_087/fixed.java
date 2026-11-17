import java.util.*;

class ImproveList<T> extends AbstractList<T> implements List<T> {
    private final List<T> list;

    ImproveList(List<T> backing) {
        list = backing;
    }

    public int size() {
        return list.size();
    }

    public T get(int index) {
        return list.get(index);
    }

    public synchronized T set(int index, T element) {
        return list.set(index, element);
    }

    public synchronized void add(int index, T element) {
        list.add(index, element);
    }

    public synchronized boolean add(T element) {
        return list.add(element);
    }

    public synchronized T remove(int index) {
        return list.remove(index);
    }

    public synchronized boolean remove(Object o) {
        return list.remove(o);
    }

    public synchronized boolean addAll(Collection<? extends T> c) {
        return list.addAll(c);
    }

    public synchronized boolean addAll(int index, Collection<? extends T> c) {
        return list.addAll(index, c);
    }

    public synchronized void clear() {
        list.clear();
    }

    public synchronized boolean putIfAbsent(T element) {
        boolean present = list.contains(element);
        if (!present)
            list.add(element);
        return !present;
    }
}

public class Main {
    public static void main(String[] args) throws Exception {
        ImproveList<Integer> list =
            new ImproveList<>(new ArrayList<>());

        Thread t1 = new Thread(() -> {
            list.add(1);
        });

        Thread t2 = new Thread(() -> {
            list.putIfAbsent(1);
        });

        t1.start();
        t2.start();

        t1.join();
        t2.join();
    }
}