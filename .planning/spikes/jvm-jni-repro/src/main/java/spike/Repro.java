package spike;

import java.util.HashMap;
import java.util.Map;

import org.apache.arrow.adbc.core.AdbcConnection;
import org.apache.arrow.adbc.core.AdbcDatabase;
import org.apache.arrow.adbc.core.AdbcDriver;
import org.apache.arrow.adbc.core.AdbcStatement;
import org.apache.arrow.adbc.driver.jni.JniDriver;
import org.apache.arrow.adbc.driver.jni.JniDriverFactory;
import org.apache.arrow.memory.BufferAllocator;
import org.apache.arrow.memory.RootAllocator;
import org.apache.arrow.vector.ipc.ArrowReader;

/**
 * Reproducer: load Apache Arrow ADBC FlightSQL Go driver via the JNI shim from a JVM,
 * loop open/connect/query/close against a real Arrow Flight server (StarRocks sr-main),
 * see how many iterations until the JVM crashes with a Go runtime fault.
 *
 * <p>Run with both signal-chaining workarounds applied via env (the runner script does this):
 * <pre>
 *   LD_PRELOAD=&lt;jdk&gt;/lib/libjsig.so
 *   GODEBUG=asyncpreemptoff=1
 * </pre>
 *
 * <p>Optional system properties:
 * <ul>
 *   <li><code>repro.driver</code> path to libadbc_driver_flightsql.so (default: ./libadbc_driver_flightsql.so)</li>
 *   <li><code>repro.uri</code> grpc URI (default: grpc://127.0.0.1:9408)</li>
 *   <li><code>repro.username</code> default: root</li>
 *   <li><code>repro.password</code> default: empty</li>
 *   <li><code>repro.iterations</code> default: 500</li>
 *   <li><code>repro.threads</code> default: 1</li>
 *   <li><code>repro.query</code> default: SELECT 1 (tiny metadata-style query)</li>
 *   <li><code>repro.persistent</code> default: false. If true, reuse Database+Connection across iterations.</li>
 * </ul>
 */
public class Repro {

  static final String DEFAULT_QUERY = "SELECT 1";

  public static void main(String[] args) throws Exception {
    String driverPath = System.getProperty("repro.driver", "./libadbc_driver_flightsql.so");
    String uri = System.getProperty("repro.uri", "grpc://127.0.0.1:9408");
    String username = System.getProperty("repro.username", "root");
    String password = System.getProperty("repro.password", "");
    int iterations = Integer.parseInt(System.getProperty("repro.iterations", "500"));
    int threads = Integer.parseInt(System.getProperty("repro.threads", "1"));
    String query = System.getProperty("repro.query", DEFAULT_QUERY);
    boolean persistent = Boolean.parseBoolean(System.getProperty("repro.persistent", "false"));

    System.out.println("=== Apache ADBC FlightSQL JNI repro ===");
    System.out.println("driver:      " + driverPath);
    System.out.println("uri:         " + uri);
    System.out.println("username:    " + username);
    System.out.println("iterations:  " + iterations);
    System.out.println("threads:     " + threads);
    System.out.println("query:       " + query);
    System.out.println("persistent:  " + persistent);
    System.out.println("LD_PRELOAD:  " + System.getenv("LD_PRELOAD"));
    System.out.println("GODEBUG:     " + System.getenv("GODEBUG"));
    System.out.println("java.vm:     " + System.getProperty("java.vm.name") + " " + System.getProperty("java.vm.version"));
    System.out.println();

    long t0 = System.nanoTime();

    boolean heapPressure = Boolean.parseBoolean(System.getProperty("repro.heappressure", "false"));
    boolean forceGc = Boolean.parseBoolean(System.getProperty("repro.forcegc", "false"));
    boolean threadPool = Boolean.parseBoolean(System.getProperty("repro.pool", "false"));
    System.out.println("heapPressure: " + heapPressure);
    System.out.println("forceGc:      " + forceGc);
    System.out.println("threadPool:   " + threadPool);
    System.out.println();

    Thread pressureThread = null;
    if (heapPressure) {
      pressureThread = new Thread(Repro::heapPressureLoop, "heap-pressure");
      pressureThread.setDaemon(true);
      pressureThread.start();
    }

    // FE-like idle threads: many parked threads that occasionally wake up and allocate,
    // mirroring StarRocks FE's heartbeat / scheduler / statistics-collection thread pools.
    int idleThreads = Integer.parseInt(System.getProperty("repro.idleThreads", "0"));
    if (idleThreads > 0) {
      System.out.println("idleThreads: " + idleThreads);
      for (int i = 0; i < idleThreads; i++) {
        Thread t = new Thread(() -> {
          try {
            while (!Thread.currentThread().isInterrupted()) {
              Thread.sleep(200);
              // Tiny allocation to keep us in young gen
              byte[] junk = new byte[8192];
              junk[0] = 1;
            }
          } catch (InterruptedException ignored) {}
        }, "idle-" + i);
        t.setDaemon(true);
        t.start();
      }
    }

    if (threads <= 1) {
      runWorker(0, driverPath, uri, username, password, iterations, query, persistent, forceGc);
    } else if (threadPool) {
      // Pool-mode mimics StarRocks FE: small pool, many tasks. Threads park between tasks
      // (LinkedBlockingQueue.take() → parkNanos), so Go M's owning the JNI-attached threads get
      // stopm()/findRunnable() opportunities — this is when Go's mcache.prepareForSweep runs.
      java.util.concurrent.ExecutorService pool = java.util.concurrent.Executors.newFixedThreadPool(threads);
      java.util.concurrent.atomic.AtomicInteger doneCounter = new java.util.concurrent.atomic.AtomicInteger();
      for (int i = 0; i < iterations; i++) {
        final int taskId = i;
        pool.submit(() -> {
          try {
            runWorker(taskId, driverPath, uri, username, password, 1, query, persistent, forceGc);
            int done = doneCounter.incrementAndGet();
            if (done % 50 == 0) {
              System.out.printf("[pool] tasks done=%d%n", done);
            }
          } catch (Exception e) {
            System.err.println("[pool t=" + taskId + "] FAILED: " + e);
            e.printStackTrace(System.err);
          }
        });
      }
      pool.shutdown();
      pool.awaitTermination(30, java.util.concurrent.TimeUnit.MINUTES);
    } else {
      Thread[] tt = new Thread[threads];
      int perThread = iterations / threads;
      for (int t = 0; t < threads; t++) {
        final int id = t;
        tt[t] = new Thread(() -> {
          try {
            runWorker(id, driverPath, uri, username, password, perThread, query, persistent, forceGc);
          } catch (Exception e) {
            System.err.println("[t" + id + "] FAILED: " + e);
            e.printStackTrace(System.err);
          }
        }, "repro-" + t);
        tt[t].start();
      }
      for (Thread t : tt) t.join();
    }

    double seconds = (System.nanoTime() - t0) / 1e9;
    System.out.printf("%n=== Experiment 1 DONE in %.1fs (no crash) ===%n", seconds);

    runConnectionChurnExperiment(driverPath, uri, username, password);

    runThreadPoolChurnExperiment(driverPath, uri, username, password);

    runFePatternExperiment(driverPath, uri, username, password);

    System.out.printf("%n=== ALL EXPERIMENTS DONE (no crash) ===%n");
  }

  /**
   * Experiment 2: mimic StarRocks FE's per-benchmark-query metadata-probe pattern.
   * One long-lived AdbcDatabase, many short-lived AdbcConnections. Per benchmark
   * query, FE issues ~58 ADBC calls (debug file evidence: 5118 ADBC calls for 88
   * benchmark queries). This experiment reproduces that connection-churn rate.
   * No flags — runs unconditionally after Experiment 1.
   */
  static void runConnectionChurnExperiment(String driverPath, String uri,
                                           String username, String password) throws Exception {
    System.out.println();
    System.out.println("=== Experiment 2: FE-pattern connection churn ===");
    int outerIters = 88;     // matches benchmark's 88 ADBC ops in --runs 3
    int innerIters = 58;     // matches FE's ~58 ADBC calls per benchmark query
    int totalOps = outerIters * innerIters;
    System.out.printf("outer=%d × inner=%d → totalOps=%d (1 AdbcDatabase, fresh AdbcConnection per op)%n",
                      outerIters, innerIters, totalOps);
    long t0 = System.nanoTime();

    try (BufferAllocator allocator = new RootAllocator()) {
      AdbcDriver driver = new JniDriverFactory().getDriver(allocator);
      Map<String, Object> baseParams = new HashMap<>();
      baseParams.put(JniDriver.PARAM_DRIVER.getKey(), driverPath);
      baseParams.put(AdbcDriver.PARAM_URI.getKey(), uri);
      baseParams.put(AdbcDriver.PARAM_USERNAME.getKey(), username);
      baseParams.put(AdbcDriver.PARAM_PASSWORD.getKey(), password);

      try (AdbcDatabase db = driver.open(baseParams)) {
        int opCounter = 0;
        for (int q = 0; q < outerIters; q++) {
          for (int probe = 0; probe < innerIters; probe++) {
            try (AdbcConnection conn = db.connect();
                 AdbcStatement stmt = conn.createStatement()) {
              stmt.setSqlQuery("SELECT 1");
              AdbcStatement.QueryResult qr = stmt.executeQuery();
              try (ArrowReader reader = qr.getReader()) {
                while (reader.loadNextBatch()) {
                  reader.getVectorSchemaRoot().getRowCount();
                }
              }
            }
            opCounter++;
          }
          if ((q + 1) % 10 == 0) {
            System.out.printf("[exp2] outer=%d/%d  ops=%d/%d%n", q + 1, outerIters, opCounter, totalOps);
          }
        }
      }
    }

    double seconds = (System.nanoTime() - t0) / 1e9;
    System.out.printf("=== Experiment 2 DONE in %.1fs (no crash) ===%n", seconds);
  }

  /**
   * Experiment 3: same total op count as exp2, but distributed across many JVM
   * threads (fixed pool of 50). Each fresh JVM thread that crosses into Go for
   * the first time triggers Go thread registration (M allocation, signal-handler
   * install/chain, TLS setup). StarRocks FE crash dump shows m=12; exp2 stayed
   * at m=1. This experiment forces Go to register dozens of Ms, mimicking the
   * thread-pool churn pattern of `starrocks-mysql-nio-pool-N` workers.
   * No flags — runs unconditionally after Experiment 2.
   */
  static void runThreadPoolChurnExperiment(String driverPath, String uri,
                                           String username, String password) throws Exception {
    System.out.println();
    System.out.println("=== Experiment 3: thread-pool churn (force Go to register many Ms) ===");
    int poolSize = 50;
    int totalOps = 5104;     // matches exp2 for direct comparability
    System.out.printf("poolSize=%d  totalOps=%d (1 AdbcDatabase, fresh AdbcConnection per task, distributed across pool)%n",
                      poolSize, totalOps);
    long t0 = System.nanoTime();

    try (BufferAllocator allocator = new RootAllocator()) {
      AdbcDriver driver = new JniDriverFactory().getDriver(allocator);
      Map<String, Object> baseParams = new HashMap<>();
      baseParams.put(JniDriver.PARAM_DRIVER.getKey(), driverPath);
      baseParams.put(AdbcDriver.PARAM_URI.getKey(), uri);
      baseParams.put(AdbcDriver.PARAM_USERNAME.getKey(), username);
      baseParams.put(AdbcDriver.PARAM_PASSWORD.getKey(), password);

      try (AdbcDatabase db = driver.open(baseParams)) {
        java.util.concurrent.ExecutorService pool =
            java.util.concurrent.Executors.newFixedThreadPool(poolSize);
        java.util.concurrent.atomic.AtomicInteger doneCounter = new java.util.concurrent.atomic.AtomicInteger();
        java.util.concurrent.atomic.AtomicReference<Throwable> firstFailure = new java.util.concurrent.atomic.AtomicReference<>();

        for (int i = 0; i < totalOps; i++) {
          pool.submit(() -> {
            try (AdbcConnection conn = db.connect();
                 AdbcStatement stmt = conn.createStatement()) {
              stmt.setSqlQuery("SELECT 1");
              AdbcStatement.QueryResult qr = stmt.executeQuery();
              try (ArrowReader reader = qr.getReader()) {
                while (reader.loadNextBatch()) {
                  reader.getVectorSchemaRoot().getRowCount();
                }
              }
              int done = doneCounter.incrementAndGet();
              if (done % 500 == 0) {
                System.out.printf("[exp3] ops=%d/%d  thread=%s%n", done, totalOps, Thread.currentThread().getName());
              }
            } catch (Exception e) {
              firstFailure.compareAndSet(null, e);
            }
          });
        }
        pool.shutdown();
        if (!pool.awaitTermination(30, java.util.concurrent.TimeUnit.MINUTES)) {
          throw new IllegalStateException("exp3 thread pool did not terminate within 30 minutes");
        }
        if (firstFailure.get() != null) {
          throw new RuntimeException("exp3 had failures, first: " + firstFailure.get(), firstFailure.get());
        }
      }
    }

    double seconds = (System.nanoTime() - t0) / 1e9;
    System.out.printf("=== Experiment 3 DONE in %.1fs (no crash) ===%n", seconds);
  }

  /**
   * Experiment 4: mirror the StarRocks FE per-query pattern from ADBCMetadata.java.
   * Per outer iter:
   *   - open AdbcConnection (mimics ADBCMetadata.listDbNames / listTableNames / getTable)
   *   - call conn.getInfo() and drain (mimics getHierarchyModel probe)
   *   - run "SELECT * FROM tpch.lineitem LIMIT 1" with the EXACT leaked-reader close
   *     pattern from ADBCMetadata.java:449-456 (qr in try-with-resources, reader leaked).
   *   - close connection
   * That's 2 ops per connection, both on the same conn, with the FE close anti-pattern.
   * If exp4 crashes the spike, the leaked-reader pattern + multi-op-per-conn is the trigger.
   * No flags — runs unconditionally after Experiment 3.
   */
  static void runFePatternExperiment(String driverPath, String uri,
                                      String username, String password) throws Exception {
    System.out.println();
    System.out.println("=== Experiment 4: FE pattern (leaked-reader close + multi-op per conn) ===");
    int outerIters = 500;
    int opsPerOuter = 2;
    int totalOps = outerIters * opsPerOuter;
    System.out.printf("outer=%d × ops=%d → totalOps=%d (real query against tpch.lineitem, FE close pattern)%n",
                      outerIters, opsPerOuter, totalOps);
    long t0 = System.nanoTime();

    try (BufferAllocator allocator = new RootAllocator()) {
      AdbcDriver driver = new JniDriverFactory().getDriver(allocator);
      Map<String, Object> baseParams = new HashMap<>();
      baseParams.put(JniDriver.PARAM_DRIVER.getKey(), driverPath);
      baseParams.put(AdbcDriver.PARAM_URI.getKey(), uri);
      baseParams.put(AdbcDriver.PARAM_USERNAME.getKey(), username);
      baseParams.put(AdbcDriver.PARAM_PASSWORD.getKey(), password);

      try (AdbcDatabase db = driver.open(baseParams)) {
        int opCounter = 0;
        for (int q = 0; q < outerIters; q++) {
          try (AdbcConnection conn = db.connect()) {
            // op 1: getInfo() → mimics ADBCMetadata.getHierarchyModel probe
            try (ArrowReader infoReader = conn.getInfo()) {
              while (infoReader.loadNextBatch()) {
                infoReader.getVectorSchemaRoot().getRowCount();
              }
            }
            opCounter++;
            // op 2: SELECT with leaked-reader close (EXACT FE pattern from
            // ADBCMetadata.java:449-456 — qr in try-with-resources, reader leaked).
            try (AdbcStatement stmt = conn.createStatement()) {
              stmt.setSqlQuery("SELECT * FROM tpch.lineitem LIMIT 1");
              try (AdbcStatement.QueryResult qr = stmt.executeQuery()) {
                ArrowReader reader = qr.getReader();   // ← FE pattern: reader NOT in try-with-resources
                reader.loadNextBatch();
                reader.getVectorSchemaRoot().getSchema();
              }
            }
            opCounter++;
          }
          if ((q + 1) % 50 == 0) {
            System.out.printf("[exp4] outer=%d/%d  ops=%d/%d%n", q + 1, outerIters, opCounter, totalOps);
          }
        }
      }
    }

    double seconds = (System.nanoTime() - t0) / 1e9;
    System.out.printf("=== Experiment 4 DONE in %.1fs (no crash) ===%n", seconds);
  }

  static void runWorker(int workerId, String driverPath, String uri, String username,
                        String password, int iterations, String query, boolean persistent,
                        boolean forceGc) throws Exception {
    try (BufferAllocator allocator = new RootAllocator()) {
      AdbcDriver driver = new JniDriverFactory().getDriver(allocator);

      Map<String, Object> baseParams = new HashMap<>();
      baseParams.put(JniDriver.PARAM_DRIVER.getKey(), driverPath);
      baseParams.put(AdbcDriver.PARAM_URI.getKey(), uri);
      baseParams.put(AdbcDriver.PARAM_USERNAME.getKey(), username);
      baseParams.put(AdbcDriver.PARAM_PASSWORD.getKey(), password);

      if (persistent) {
        try (AdbcDatabase db = driver.open(baseParams);
             AdbcConnection conn = db.connect()) {
          for (int i = 0; i < iterations; i++) {
            doOneStatement(workerId, i, conn, query);
            if (forceGc) System.gc();
            progress(workerId, i);
          }
        }
      } else {
        for (int i = 0; i < iterations; i++) {
          try (AdbcDatabase db = driver.open(baseParams);
               AdbcConnection conn = db.connect()) {
            doOneStatement(workerId, i, conn, query);
          }
          if (forceGc) System.gc();
          progress(workerId, i);
        }
      }
    }
  }

  /** Background JVM heap pressure: allocate and discard arrays to force frequent JVM GC. */
  static void heapPressureLoop() {
    try {
      while (!Thread.currentThread().isInterrupted()) {
        // ~32 MB allocation per loop iter; thrashes G1
        byte[] junk = new byte[32 * 1024 * 1024];
        // Touch it so JIT doesn't elide
        junk[junk.length - 1] = 1;
        Thread.sleep(50);
      }
    } catch (InterruptedException ignored) {
      Thread.currentThread().interrupt();
    }
  }

  static void doOneStatement(int workerId, int iter, AdbcConnection conn, String query) throws Exception {
    // Mix in catalog-metadata calls to mirror StarRocks FE workload:
    //   FE catalog.listDbNames → AdbcConnectionGetObjects(depth=DBS)
    //   FE catalog.getTableSchema → AdbcConnectionGetTableSchema
    // These exercise different JNI/Go paths than ExecuteQuery and are what FE actually does most of.
    String mode = System.getProperty("repro.mode", "exec"); // exec | metadata | mixed

    if ("metadata".equals(mode) || ("mixed".equals(mode) && (iter % 2 == 0))) {
      // Get the schema of an existing table (information_schema.tables always exists)
      var schema = conn.getTableSchema(null, "information_schema", "tables");
      if (schema == null) throw new IllegalStateException("null schema");
      return;
    }

    boolean buggyClose = Boolean.parseBoolean(System.getProperty("repro.buggyClose", "false"));
    try (AdbcStatement stmt = conn.createStatement()) {
      stmt.setSqlQuery(query);
      if (buggyClose) {
        // FE's exact pattern: close qr, leak reader (no try-with-resources on reader)
        try (AdbcStatement.QueryResult qr = stmt.executeQuery()) {
          ArrowReader reader = qr.getReader();
          while (reader.loadNextBatch()) {
            int rows = reader.getVectorSchemaRoot().getRowCount();
            if (rows < 0) throw new IllegalStateException("negative rowcount?");
          }
        }
      } else {
        AdbcStatement.QueryResult qr = stmt.executeQuery();
        try (ArrowReader reader = qr.getReader()) {
          while (reader.loadNextBatch()) {
            int rows = reader.getVectorSchemaRoot().getRowCount();
            if (rows < 0) throw new IllegalStateException("negative rowcount?");
          }
        }
      }
    }
  }

  static void progress(int workerId, int iter) {
    if ((iter + 1) % 10 == 0) {
      System.out.printf("[t%d] iter=%d%n", workerId, iter + 1);
    }
  }
}
