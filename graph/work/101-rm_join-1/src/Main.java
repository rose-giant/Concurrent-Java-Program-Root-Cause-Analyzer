import java.util.concurrent.atomic.AtomicReference;
class ConcurrentStack<E> {
    static class Node<E> {
        E item;
        Node<E> next;
        Node(E item) {
            this.item = item;
        }
    }
    private final AtomicReference<Node<E>> top = new AtomicReference<>();
    void push(E item) {
        Node<E> newHead = new Node<>(item);
        Node<E> oldHead;
        do {
            oldHead = top.get();
            newHead.next = oldHead;
        }
        while (!top.compareAndSet(oldHead, newHead));
    }
    E pop() {
        Node<E> oldHead;
        Node<E> newHead;
        do {
            oldHead = top.get();
            if (oldHead == null) return null;
            newHead = oldHead.next;
        }
        while (!top.compareAndSet(oldHead, newHead));
        return oldHead.item;
    }
}
public class Main {
    public static void main(String[] args) throws Exception {
        ConcurrentStack<Integer> stack = new ConcurrentStack<>();
        Runnable task = () -> {
            for (int j = 0; j < 2; j++) {
                stack.push(j);
                System.out.print('P');
            }
            for (int j = 0; j < 2; j++) {
                stack.pop();
                System.out.print('O');
            }
        };
        Thread t1 = new Thread(task);
        Thread t2 = new Thread(task);
        t1.start();
        t2.start();
        t2.join();
        System.out.print('C');
    }
}
