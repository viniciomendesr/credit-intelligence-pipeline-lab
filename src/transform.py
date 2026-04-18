"""SQL model execution layer: reads .sql files, runs via DuckDB, writes Parquet."""

import duckdb
from pathlib import Path

ROOT = Path(__file__).parent.parent
MODELS_DIR = ROOT / "models"


def run_model(model_name: str, output_path: str | Path) -> None:
    """Execute a SQL model file via DuckDB and materialise the result as Parquet.

    Always registers stg_credit_applications as a view first so any mart that
    references that name resolves correctly — mirrors how dbt handles staging
    dependencies at runtime.

    Idempotent: running twice produces the same output without errors because
    CREATE OR REPLACE VIEW and to_parquet() with an existing path both overwrite
    safely.
    """
    con = duckdb.connect()

    out_dir = Path(output_path)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Register staging as a view so marts can reference it by name
    stg_sql = (MODELS_DIR / "stg_credit_applications.sql").read_text()
    con.execute(f"CREATE OR REPLACE VIEW stg_credit_applications AS {stg_sql}")

    sql = (MODELS_DIR / f"{model_name}.sql").read_text()
    result = con.execute(sql).df()

    out = out_dir / f"{model_name}.parquet"
    result.to_parquet(out, index=False)

    print(f"'{model_name}': {len(result)} registros → {out}")
