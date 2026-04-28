---
phase: "02"
status: deferred
subsystem: starrocks-be
tags: [adbc, postgresql, numeric, arrow-extension-type, starrocks-fix-needed]
discovered_at: 2026-04-28
---

# Postgres `numeric` over ADBC — known gap, deferred to StarRocks-side fix

## Symptom

17 postgres TPC-H queries fail with:

```
pymysql.err.ProgrammingError: (1064, 'No Arrow converter for arrow type extension
<arrow.opaque[storage_type=string, type_name=numeric, vendor_name=PostgreSQL]>
to StarRocks type VARCHAR: BE:10001')
```

Affected: `postgres/03-q{01,02,03,05,06,07,08,09,10,11,14,15,17,18,19,20,22}-*.sql`.

Each is annotated with `-- Skip: <reason>` so `tests/test_queries.py` skips them in
CI rather than failing. Once the StarRocks-side fix lands, removing the `-- Skip:`
line per file re-enables them.

The 5 postgres queries that pass (`q04, q12, q13, q16, q21`) are the ones whose
SELECT list and WHERE clauses don't surface a `NUMERIC` column to StarRocks. The
mysql versions of all 22 queries pass — the issue is specific to the ADBC PostgreSQL
driver's representation of `numeric`.

## Root cause

PostgreSQL `NUMERIC` is unbounded in precision, can hold NaN/Infinity, and aggregate
results (`SUM`, `AVG`, scaled arithmetic) lose any declared typmod. None of these
fit Arrow's `Decimal128`/`Decimal256` cleanly, so the ADBC PostgreSQL driver
conservatively wraps every `numeric` value as the Arrow extension type
`arrow.opaque[storage_type=string, type_name=numeric, vendor_name=PostgreSQL]`.
The actual digits travel as a string (`"15234.78"`) inside a wrapper that says
"this is opaque and means numeric to PostgreSQL."

StarRocks BE has no dispatch entry for this extension type — neither the trivial
passthrough to VARCHAR (which would unblock everything immediately) nor a
specialized string→DECIMAL parser. The error is raised at decode time, before the
SQL engine ever sees the value.

The error message even names the FE-decided target ("to StarRocks type VARCHAR"):
the FE chose VARCHAR as the conservative default mapping for the unknown source
type, and the BE refuses because its dispatcher doesn't know how to fulfill that
either.

## Why upstream-only isn't enough

A "fix it in the ADBC PG driver" approach (emit `Decimal128(p,s)` when the column
has a bounded typmod) handles direct table reads of bounded `NUMERIC(p,s)` columns,
but **cannot** handle:

- Unbounded `NUMERIC` columns (no typmod at all).
- Aggregate result columns: `SUM(price)` returns `numeric` with no precision/scale
  modifier — PG's planner types it as unconstrained. Almost every TPC-H query is
  aggregate-heavy.
- Expressions producing computed numeric values: `extendedprice * (1 - discount)`.
- NaN and ±Infinity, which `Decimal128` cannot represent at all.

So even with a maximally helpful PG driver, opaque-numeric arrives at StarRocks BE
for aggregate queries. The decoder has to live in StarRocks regardless.

## Recommended design (StarRocks-side fix)

### 1. BE: extension-type registry, vendor-agnostic

```cpp
struct ExtensionKey {
    arrow::Type::type storage_type;   // STRING, BINARY, FIXED_SIZE_BINARY, ...
    std::string       type_name;      // "numeric", "interval", "hugeint", ""
    std::string       vendor_name;    // "" = vendor-agnostic
};

class ExtensionDecoder {
public:
    virtual Status decode(const arrow::Array& src,
                          const TypeDescriptor& dst,   // user's declared StarRocks type
                          Column* out) = 0;
};

// Lookup order: most specific first
//   1. (storage, type_name, vendor_name)   — vendor override (rare)
//   2. (storage, type_name, "")            — conceptual default
//   3. (storage, "", "")                   — raw passthrough
```

`vendor_name` is **informational only** — log it, never branch on it. The day a
genuine per-vendor deviation appears, layer 1 lets you handle it without polluting
the conceptual default.

### 2. Initial decoders

| Key | Decoder | What it does |
|---|---|---|
| `(string, numeric, *)` | `StringToDecimalDecoder` | parse decimal string → user-declared `DECIMAL{32,64,128}` or VARCHAR |
| `(string, hugeint, *)` | `StringToInt128Decoder` | parse 128-bit int → LARGEINT or VARCHAR |
| `(string, interval, *)` | `StringToIntervalDecoder` | parse ISO-8601 → DATETIME diff or VARCHAR |
| `(string, *, *)` | **default** passthrough → VARCHAR | safe fallback, never errors |
| `(binary, *, *)` | **default** passthrough → VARBINARY | safe fallback |

None mention PostgreSQL by name. The numeric decoder handles PG, DuckDB, and any
future vendor that picks the same conceptual encoding.

### 3. Target-type contract

> The StarRocks column's declared type is the conversion target.
> The Arrow extension is the source format hint.

The `numeric` decoder doesn't care which vendor wrote it. It only cares: "I have a
string Arrow array; the user's declared StarRocks column is `DECIMAL128(15,2)`;
parse, scale-adjust, populate, overflow-check." If the declared column is VARCHAR,
the same decoder degrades to passthrough — no parsing, just copy the string bytes.

### 4. FE: catalog property to pick the default target

```sql
CREATE EXTERNAL CATALOG sr_postgres
PROPERTIES (
    'driver' = 'adbc',
    'opaque_numeric_target' = 'DECIMAL128(38, 9)',  -- or VARCHAR for raw debug
    ...
);
```

Default: `DECIMAL128(38, 9)` — lossy at the extreme tails, but TPC-H-correct for
typical workloads. The FE writes this into table metadata at catalog refresh, and
the BE decoder honors it. Users who want to inspect raw strings (debugging,
ad-hoc data exploration) can pick VARCHAR.

This also matches the JDBC catalog's existing fallback behavior — JDBC silently
truncates unbounded NUMERIC into `DECIMAL128(38, ?)` today via
`BigDecimal.toString()` + parse. ADBC ending up at the same correctness corner is
a feature, not a regression.

### 5. Why **not** session-level magic implicit casts

A flag like `SET cast_opaque_numeric_to=decimal128` that rewrites column types at
binding time was considered and rejected. Type-rewrite rules driven by metadata
the user can't see in the query text are a maintenance trap — same query, two
sessions, two answers, silent failure. The catalog-property + decoder approach
gives a deterministic per-catalog choice that the optimizer can also reason about.

## What "letting StarRocks handle VARCHAR" buys you

StarRocks already implements MySQL-style implicit string→DOUBLE coercion in
arithmetic and aggregate contexts. Once the BE passthrough decoder exists, the
queries will *evaluate* without explicit `CAST` — but the implicit cast goes to
DOUBLE, not DECIMAL. For TPC-H this gives results that match within ~1e-10 but
fail strict validation (TPC-H reference results assume fixed-point decimals).

So the BE passthrough decoder is sufficient to make the queries *run*; the
DECIMAL decoder + FE catalog property is what makes the answers *certify*.

## Order of fixes

1. **BE: opaque-string passthrough decoder.** One default registry entry. Smallest
   diff, unblocks every failing query immediately with VARCHAR semantics. Aggregate
   results land as VARCHAR-of-decimal-text and queries evaluate via implicit-cast
   (lossy, DOUBLE).
2. **BE: `(string, numeric)` → DECIMAL decoder.** Activated when FE points at a
   DECIMAL target. No vendor branching.
3. **FE: ADBC catalog `opaque_numeric_target` property.** Source typmods honored
   where bounded, `DECIMAL128(38, 9)` default otherwise. Aggregates always ride on
   the BE decoder via the catalog default.

(1) makes 17 tests stop failing. (1)+(2)+(3) makes the answers TPC-H-certifiable.

## Performance expectation

For numeric columns specifically, opaque-string decode is **roughly comparable to
the JDBC catalog path** — both end up parsing decimal strings into fixed-point
representations. Per-row, the costs are similar; ADBC saves on per-row JNI and JVM
allocation but spends the same on string parsing.

For mixed-type queries (the common case — a TPC-H query touches integers, dates,
varchars, and decimals), the rest of the columns still ride the ADBC zero-copy
fast path. Net is solidly better than JDBC overall, even with the slow numeric
sub-path.

## Verification plan once StarRocks fix lands

1. Strip `-- Skip: ...` lines from the 17 postgres queries.
2. Re-run `STARROCKS_HOST=127.0.0.1 STARROCKS_PORT=9030 .venv/bin/pytest tests/ -v`.
3. With BE passthrough decoder only: all 17 should run; row counts may need
   adjustment if VARCHAR-context implicit-cast changes ordering (unlikely for
   simple SUM/AVG queries).
4. With BE DECIMAL decoder + FE catalog property at `DECIMAL128(38, 9)`: row counts
   should match the mysql versions of the same queries (already passing in this
   suite).

## Out of scope for Phase 02

This phase delivered SF1 data + 22 TPC-H queries per backend. The verification
revealed the gap above; closing it is StarRocks engine work, not a Phase 02
deliverable. Tracked here so it's not lost.
