"""Simple append-only ingestion of snapshot CSVs into DuckDB.

Each snapshot file is appended to ``raw.<history_table>`` with an
``ingested_at`` column parsed from the filename. No deduplication —
that is deferred to the dbt transformation layer.
"""
from __future__ import annotations

import duckdb
import pandas as pd

from ingest.config import IngestionConfig
from ingest.utils import setup_logging


class DuckDBMerger:
    """Append snapshot DataFrames into a single DuckDB table."""

    def __init__(self, conn: duckdb.DuckDBPyConnection, config: IngestionConfig):
        self.conn = conn
        self.config = config
        self.logger = setup_logging(config.log_level).getChild("merger")
        self._ensure_schema()

    @property
    def history_fqtn(self) -> str:
        return f"{self.config.raw_schema}.{self.config.history_table}"

    def _ensure_schema(self) -> None:
        self.conn.execute(f"CREATE SCHEMA IF NOT EXISTS {self.config.raw_schema}")
        # Drop existing table for a clean append-only load.
        self.conn.execute(f"DROP TABLE IF EXISTS {self.history_fqtn}")

    def _existing_columns(self, table: str) -> list[str]:
        try:
            parts = table.split(".")
            rows = self.conn.execute(
                f'DESCRIBE "{parts[0]}"."{parts[1]}"'
            ).fetchall()
        except duckdb.CatalogException:
            return []
        return [r[0] for r in rows]

    @staticmethod
    def _duckdb_dtype(col_name: str, series: pd.Series) -> str:
        if col_name == "snapshot_date":
            return "DATE"
        if col_name == "ingestion_timestamp":
            return "TIMESTAMP"
        if col_name == "ingested_at":
            return "TIMESTAMP"
        if isinstance(series.dtype, pd.ArrowDtype):
            if pd.api.types.is_integer_dtype(series):
                return "BIGINT"
            if pd.api.types.is_float_dtype(series):
                return "DOUBLE"
            if pd.api.types.is_bool_dtype(series):
                return "BOOLEAN"
            if pd.api.types.is_datetime64_any_dtype(series):
                return "TIMESTAMP"
            return "VARCHAR"
        if pd.api.types.is_integer_dtype(series):
            return "BIGINT"
        if pd.api.types.is_float_dtype(series):
            return "DOUBLE"
        if pd.api.types.is_bool_dtype(series):
            return "BOOLEAN"
        if pd.api.types.is_datetime64_any_dtype(series):
            return "TIMESTAMP"
        return "VARCHAR"

    def _create_table(self, fqtn: str, df: pd.DataFrame) -> None:
        col_defs: list[str] = []
        for c in df.columns:
            col_defs.append(f'"{c}" {self._duckdb_dtype(c, df[c])}')
        ddl = (
            f"CREATE TABLE IF NOT EXISTS {fqtn} (\n  "
            + ",\n  ".join(col_defs)
            + "\n)"
        )
        self.conn.execute(ddl)
        self.logger.info("Created table %s (%d cols)", fqtn, len(col_defs))

    def _handle_schema_drift(self, fqtn: str, df: pd.DataFrame) -> None:
        existing = set(self._existing_columns(fqtn))
        new_cols = [c for c in df.columns if c not in existing]
        for c in new_cols:
            dtype = self._duckdb_dtype(c, df[c])
            self.conn.execute(f'ALTER TABLE {fqtn} ADD COLUMN "{c}" {dtype}')
            self.logger.warning(
                "Schema drift: added column %s (%s) to %s", c, dtype, fqtn
            )

    @staticmethod
    def _align_columns(df: pd.DataFrame, target_cols: list[str]) -> pd.DataFrame:
        """Reorder/reshape df so its columns == target_cols (missing -> NULL)."""
        if len(df) == 0:
            return pd.DataFrame(
                {c: pd.Series(dtype="object") for c in target_cols}
            )
        data = {}
        for c in target_cols:
            data[c] = df[c] if c in df.columns else [None] * len(df)
        return pd.DataFrame(data, index=df.index)

    def truncate_insert_csv(
        self, csv_path: Path, table_name: str
    ) -> dict:
        """Truncate-insert a standalone CSV into raw.<table_name>.

        Drops and recreates the table each run (same semantics as snapshots).
        """
        fqtn = f"{self.config.raw_schema}.\"{table_name}\""
        self.logger.info("Loading CSV %s -> %s", csv_path, fqtn)

        df = pd.read_csv(csv_path, dtype_backend="pyarrow")
        df.columns = [str(c).strip() for c in df.columns]
        obj_cols = [
            c for c in df.columns
            if pd.api.types.is_string_dtype(df[c]) or df[c].dtype == object
        ]
        for c in obj_cols:
            df[c] = df[c].astype("string").str.strip()

        rows = len(df)
        self.conn.execute(f"DROP TABLE IF EXISTS {fqtn}")
        self._create_table(fqtn, df)
        self.conn.register("_staged", df)
        col_list = ", ".join(f'"{c}"' for c in df.columns)
        self.conn.execute(
            f"INSERT INTO {fqtn} ({col_list}) SELECT {col_list} FROM _staged"
        )
        self.conn.unregister("_staged")
        self.logger.info("Loaded %s: %d rows", fqtn, rows)
        return {"table": table_name, "rows": rows}

    def append_snapshot(self, snapshot_df: pd.DataFrame) -> dict:
        """Append one snapshot DataFrame into the history table.

        Returns a metrics dict.
        """
        if snapshot_df.empty:
            self.logger.warning("Empty snapshot DataFrame; skipping.")
            return {"rows_input": 0, "history_fqtn": self.history_fqtn}

        df = snapshot_df.copy()
        rows_input = len(df)

        # Ensure table exists + handle drift.
        if not self._existing_columns(self.history_fqtn):
            self._create_table(self.history_fqtn, df)
        else:
            self._handle_schema_drift(self.history_fqtn, df)

        history_cols = self._existing_columns(self.history_fqtn)
        df_aligned = self._align_columns(df, history_cols)

        self.conn.register("_staged", df_aligned)
        col_list = ", ".join(f'"{c}"' for c in history_cols)
        self.conn.execute(
            f"INSERT INTO {self.history_fqtn} ({col_list}) "
            f"SELECT {col_list} FROM _staged"
        )
        self.conn.unregister("_staged")

        self.logger.info(
            "Appended snapshot rows=%d -> %s", rows_input, self.history_fqtn
        )
        return {"rows_input": rows_input, "history_fqtn": self.history_fqtn}
