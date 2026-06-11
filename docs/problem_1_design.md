# Design notes — Problem 1: Snapshot ingestion into DuckDB

## Goal

Ingest cumulative snapshots of `cis_user_portfolio_histories` into two raw
tables in DuckDB:

* `raw.cis_user_portfolio_histories_snapshot` — full history (one row per
  `(business_key, snapshot_date)`).
* `raw.cis_user_portfolio_histories_latest` — current state (one row per
  `business_key`, holding the most recent snapshot we have seen).

Re-running ingestion, partially or fully, must never produce duplicates and
must never regress a newer row back to an older version.

---

## Assumptions

1. **Snapshots are cumulative, not delta.** Each CSV contains the full set
   of *current* rows at the snapshot date — there is no `op` column.
2. **Filename = snapshot date.** We extract the date from the filename
   (ISO `YYYY-MM-DD` or compact `YYYYMMDD`).
3. **Same business row across snapshots carries the same business key.**
   This is what allows MERGE to identify the "same row, newer version".
4. **Older snapshots may be loaded after newer ones.** The pipeline must
   not regress the `latest` table when an old snapshot is replayed.
5. **Schema drift is additive only.** New columns appear; columns are never
   renamed or dropped within the scope of this prototype. (Production
   would also handle rename/drop via an explicit schema-registry check.)
6. **`risk_score` in the third sample file is intentional drift** to prove
   the schema-drift path works end-to-end.
7. **Single source, single table.** No multi-table joins inside the
   ingestion layer — those belong to dbt staging.

---

## Business key — declared, not detected

The pipeline does **not** auto-detect the business key. The key is
declared in `IngestionConfig.business_key` (default `("id",)`):

```python
IngestionConfig(business_key=("user_id", "portfolio_id"))  # composite
```

or via TOML override:

```toml
[ingestion]
business_key = ["user_id", "portfolio_id"]
```

At merge time, the merger validates every declared column is present on
the incoming snapshot (`ValueError` otherwise) before computing the
synthetic hash column (`_bk_hash`, sha256 over the key columns joined by
ASCII unit separator). Both MERGE statements join on this column. This:

* keeps the ON clause stable regardless of key column count,
* keeps history/latest table shapes identical,
* makes a future composite-key change a schema migration, not a code
  change.

### Why not auto-detect?

A `detect_business_key` utility exists in `ingest/utils.py` for ad-hoc
profiling (regex on id-shaped names → cardinality-ratio filter → single
vs composite pick) but it is intentionally **not** called from the
pipeline. Reasons:

* In production, the key is a data contract — declared in a schema
  registry / dbt sources / TOML — not guessed from filenames.
* Auto-detection can silently pick a foreign-key column (low but
  non-zero cardinality, id-shaped name) and corrupt MERGE semantics on
  slow-changing attributes.
* Explicit declaration is auditable; a profiler output is not.

The utility remains available for one-off inspection tasks.

### First-snapshot validation

The first snapshot's key is cached on the merger; subsequent snapshots
must contain the same key columns. `_add_business_key_hash` raises
`ValueError` if any declared key column is missing.

---

## Merge strategy

Both tables use DuckDB's native `MERGE INTO ... USING ... WHEN MATCHED /
WHEN NOT MATCHED` syntax.

### History table — `raw.cis_user_portfolio_histories_snapshot`

```sql
MERGE INTO raw.cis_user_portfolio_histories_snapshot AS t
USING _staged_history AS s
  ON t."_bk_hash"     = s."_bk_hash"
 AND t."snapshot_date" = s."snapshot_date"
WHEN MATCHED     THEN UPDATE SET <data_cols = s.data_cols>
WHEN NOT MATCHED THEN INSERT
```

Grain: `(_bk_hash, snapshot_date)`. Re-running with the same snapshot
updates the existing row in place; new `(key, snapshot_date)` pairs
insert. Result: no duplicates, ever.

### Latest table — `raw.cis_user_portfolio_histories_latest`

```sql
MERGE INTO raw.cis_user_portfolio_histories_latest AS t
USING _staged_latest AS s
  ON t."_bk_hash" = s."_bk_hash"
WHEN MATCHED AND s."snapshot_date" >= t."snapshot_date"
  THEN UPDATE SET <all cols = s.cols>
WHEN NOT MATCHED THEN INSERT
```

Grain: `_bk_hash`. The `>=` is what protects us from out-of-order
replays: an older snapshot cannot overwrite a newer one. Equality
covers idempotent re-runs of the *current* snapshot.

---

## Idempotency strategy

The pipeline satisfies all three classic idempotency scenarios:

| Scenario | Why it works |
|---|---|
| Re-run the same ingestion (no new data) | History MERGE on `(bk, snapshot_date)` matches existing rows and `UPDATE`s with identical values; Latest MERGE matches with `snapshot_date ==` and re-updates. |
| Add a new snapshot and re-run | New rows: `WHEN NOT MATCHED` inserts. Existing rows: `WHEN MATCHED AND s.snapshot_date > t.snapshot_date` updates. |
| Re-run after partial load (some snapshots already in DB) | Each snapshot is processed independently; MERGE guarantees convergence regardless of order. |

No `DELETE`, no `TRUNCATE`, no temp-table swap. Pure MERGE.

---

## Schema drift handling

Two cases, both defensive:

* **New column in incoming snapshot:** `ALTER TABLE … ADD COLUMN <name>
  <type>` is run before MERGE. Type is inferred from the pandas dtype via
  a small mapper (`_duckdb_dtype`).
* **Column missing in incoming snapshot:** the `_align_columns` helper
  fills `NULL` for that column in the staged DataFrame. This means
  replaying an old snapshot does not corrupt newer rows that *do* have
  the column.

We never `DROP COLUMN` — additive-only is a hard contract for raw tables.

---

## Alternative approaches considered

### 1. Delete-and-replace per snapshot_date

```sql
DELETE FROM raw.history WHERE snapshot_date = ?;
INSERT INTO raw.history SELECT * FROM staged WHERE snapshot_date = ?;
```

**Pros:** trivially correct, easy to reason about.
**Cons:** not safe for concurrent reads (a window where rows are gone),
loses row-level lineage, slower than MERGE on large tables.

### 2. Append + dedupe view

Append everything, then define `latest` as a view with `ROW_NUMBER()
OVER (PARTITION BY bk ORDER BY snapshot_date DESC) = 1`.

**Pros:** pure-append is the cheapest write path.
**Cons:** `latest` query cost grows linearly with history; not viable
beyond ~10M rows; no MERGE semantics to brag about during presentation.

### 3. dlt

`dlt` would have given us merge-on-key, schema evolution, and
state-tracking for free. Evaluated separately and dropped from the
prototype to keep the dep surface minimal; the same concepts (auto
key detection, MERGE, drift handling) translate directly if we adopt
it in production.

### 4. dbt snapshots (SCD2)

**Pros:** gives history *and* "as-of" queries for free.
**Cons:** belongs in the dbt layer (Problem 2). Raw ingestion should
faithfully mirror the source, not interpret it.

---

## Mapping to production (Athena + Iceberg)

The local prototype maps one-to-one to the production stack:

| Local | Production |
|---|---|
| `SnapshotLoader` reading local CSVs | Dagster S3 sensor / asset |
| `DuckDBMerger.merge_snapshot` | Athena/Iceberg native `MERGE INTO` (primary key = business key, merge key = snapshot_date) |
| `raw.<table>_snapshot` (history) | Athena/Iceberg table with snapshot retention via `ALTER TABLE … DELETE` on snapshot TTL |
| `raw.<table>_latest` (current state) | Athena/Iceberg "current" table maintained by Iceberg `MERGE INTO` (native since Iceberg 0.14) |
| `_bk_hash` column | Same — preserves Iceberg row-level MERGE performance with composite keys |
| `ALTER TABLE ADD COLUMN` (drift) | Iceberg schema evolution (native additive) |
| Manual `python -m ingest.run` | Dagster asset, sensor on `s3://bucket/snapshots/` |
| Local `duckdb/analytics.duckdb` | Athena workgroup + Glue catalog |

Key invariants that survive the migration:

* **Idempotent MERGE on (bk, snapshot_date).** Iceberg's row-level
  `MERGE INTO` is the same shape.
* **Additive-only schema drift.** Iceberg's schema evolution is also
  additive-only — the contract holds.
* **Latest snapshot wins.** Iceberg `MERGE WHEN MATCHED AND s.snapshot_date > t.snapshot_date`
  is a direct port.
* **Filename-as-snapshot-date** is replaced by S3 event metadata in
  production; the parsing contract stays the same.

---

## Failure modes considered

| Failure | Behaviour |
|---|---|
| Snapshot file with no parseable date | `extract_snapshot_date` raises `ValueError` → pipeline aborts before any writes. |
| Snapshot missing business key column | `_add_business_key_hash` raises `ValueError` → pipeline aborts before any writes. |
| DuckDB file locked | `duckdb.connect` raises; surfaces to operator / orchestrator. |
| Snapshot column has new dtype vs existing table | Treated as additive drift: new column added with the new dtype. We do not attempt to coerce. |
| Empty snapshot | Skipped with a `WARNING` log; counts stay aligned. |
| Re-run with one snapshot removed from disk | The history row from that snapshot is preserved (we never delete). The latest row stays as the most-recent remaining snapshot. |
