package dev.a2flow.management.support;

import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

/** Fixed worker and queue bounds; saturation is reported by RejectedExecutionException. */
public final class BoundedExecutors {
    private BoundedExecutors() { }
    public static ExecutorService fixed(int workers, String threadNamePattern) {
        AtomicInteger sequence = new AtomicInteger();
        return new ThreadPoolExecutor(workers, workers, 0, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(workers * 16), runnable -> {
                    Thread thread = new Thread(runnable, String.format(threadNamePattern, sequence.incrementAndGet()));
                    thread.setDaemon(true);
                    return thread;
                }, new ThreadPoolExecutor.AbortPolicy());
    }
}
