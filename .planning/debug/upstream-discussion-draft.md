# Draft — arrow-adbc Discussion

**Suggested title:** `JVM crashes loading Go-based ADBC drivers under sustained load — field report + working config`

**Format:** GitHub Discussion. Field report, not a fix proposal. I have not changed JNI shim code; I report what I observed and ask for guidance.

**Length target:** ~350 words.

---

## Context

I've been working on an ADBC catalog connector for StarRocks (using `JniDriverFactory` on the JVM side; not yet upstream). This report is from running it under sustained TPC-H load against an Arrow Flight target.

## TL;DR

Loading a Go-based ADBC driver (FlightSQL in my case) into a long-lived JVM via `JniDriverFactory` and running sustained workloads crashes the JVM with one of three signatures from what looks like the same bug class. I found a deployment configuration that holds at >800 sequential ADBC ops, but I haven't touched the JNI shim itself. Posting this as a field report and to ask whether anyone has hit it / has guidance on where to look.

## Setup

- Host: StarRocks FE (long-lived JVM, server workload, hundreds of threads)
- Driver: `libadbc_driver_flightsql.so` loaded via `org.apache.arrow.adbc.driver.jni.JniDriverFactory`
- Workload: TPC-H SF1 over Arrow Flight, ~50 ADBC calls per query × 88 queries per benchmark run
- Behavior: crashes within tens of ADBC operations on stock build; stable past 800 ops with the workarounds below

## Three crash signatures, looks like one bug class

1. `fatal error: found pointer to free object` in `runtime.bgsweep` — GC sweep finds zombie heap entries
2. `SIGSEGV at addr=0x118` in `runtime.(*unwinder).next` — stack walker derefs null when scanning a goroutine mid-cgo-callback
3. `runtime.memmove` in `bytes.(*Buffer).Write` from gRPC `hpack.(*Encoder).WriteField` — gRPC `loopyWriter` writes into a freed Go buffer while encoding HTTP/2 headers for a new stream

All three look like the Go runtime catching freed-but-still-referenced state. Variation seems timing-driven: whichever goroutine happens to be running when the corruption surfaces.

## What works (deployment hygiene only)

I have not modified the JNI shim. I pinned a known-good build of the FlightSQL `.so` and added two env vars at JVM launch:

```bash
LD_PRELOAD=$JAVA_HOME/lib/libjsig.so       # JDK-shipped signal chaining
GODEBUG=asyncpreemptoff=1                   # disable Go SIGURG-based preemption
```

I also added a caller-side connection pool so the JVM doesn't churn `JniConnection` wrappers. With this combination I run 10× sustained benchmark cycles (≈880 ADBC ops) cleanly. Without it, crash within tens of ops.

## What I suspect, but have not verified

The shape of the failures is consistent with the JVM Cleaner reclaiming `JniConnection` / `NativeConnectionHandle` wrappers in some order that doesn't match ADBC's C-ABI release-order requirements (statements before connections, connections before database). gRPC stream/transport goroutines from the Go-side driver finish their unwind shortly after `Close()` returns; if the JVM Cleaner pipeline is in the middle of reclaiming those wrappers around the same time, the Go heap state they touch may already be inconsistent. This is just a hypothesis — I haven't built a fix to test it.

## Why I think upstream hasn't seen this

`JniDriverTest.java` covers happy-path open/close cycles only. No sustained-load run, no Go-based driver in the test set, no `System.gc()` pressure between iterations. A bug at this layer wouldn't surface there.

## Asks

1. Has anyone hit this signature class on the JNI driver before? Known issues / threads to point at?
2. Is the Cleaner / release-order angle worth investigating, or am I looking at the wrong layer?
3. Would a sustained-load test in `JniDriverTest` (Go-based driver + many connect/close cycles + explicit GC between) be welcome as a contribution? Happy to put one up regardless.
4. Is a deployment doc note (libjsig + GODEBUG when JNI-loading Go drivers) something the project wants?

Reproducer (StarRocks FE setup + a small spike JAR) available; happy to share if useful.
