"""Data ingestion, validation, and staging for the credit pipeline."""

import hashlib
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from faker import Faker

fake = Faker("pt_BR")

ROOT = Path(__file__).parent.parent


def validate_dataframe(df: pd.DataFrame) -> dict:
    """Validate a credit applications DataFrame against business rules.

    Returns a dict with missing_pct (cols with nulls), violations (domain
    rule breaches with counts), and is_valid flag.
    Thresholds come from the EDA in 01_exploration.ipynb.
    """
    null_pct = (df.isnull().sum() / len(df) * 100).round(2)
    missing_pct = null_pct[null_pct > 0].to_dict()

    violations = {}

    if "age" in df.columns:
        bad = ((df["age"] < 18) | (df["age"] > 100)).sum()
        if bad:
            violations["age_invalid"] = int(bad)

    if "MonthlyIncome" in df.columns:
        bad = (df["MonthlyIncome"] < 0).sum()
        if bad:
            violations["income_negative"] = int(bad)

    if "DebtRatio" in df.columns:
        bad = (df["DebtRatio"] > 100).sum()
        if bad:
            violations["debt_ratio_high"] = int(bad)

    if "RevolvingUtilizationOfUnsecuredLines" in df.columns:
        bad = (df["RevolvingUtilizationOfUnsecuredLines"] > 1.5).sum()
        if bad:
            violations["utilization_high"] = int(bad)

    return {
        "missing_pct": missing_pct,
        "violations": violations,
        "is_valid": max(missing_pct.values(), default=0) < 30
        and sum(violations.values()) == 0,
    }


def fetch_from_api(n_records: int) -> list[dict]:
    """Simulate a credit bureau API call, returning n_records payloads.

    Schema per record:
      applicant_id  str  zero-padded 6-digit (APP-000001)
      cpf_hash      str  sha256[:16] of raw CPF — never PII in clear
      bureau_score  int  [300, 900]
      active_debts  int  [0, 15]
      requested_at  str  ISO timestamp within the last 365 days

    random.seed(42) guarantees the same n always produces the same dataset.
    Persists to data/raw/bureau_api.json before returning.
    """
    random.seed(42)
    base = datetime.now()
    records = []

    for i in range(n_records):
        cpf = fake.cpf().replace(".", "").replace("-", "")
        records.append(
            {
                "applicant_id": f"APP-{i + 1:06d}",
                "cpf_hash": hashlib.sha256(cpf.encode()).hexdigest()[:16],
                "bureau_score": random.randint(300, 900),
                "active_debts": random.randint(0, 15),
                "requested_at": (
                    base - timedelta(days=random.randint(0, 365))
                ).isoformat(),
            }
        )

    out_path = ROOT / "data" / "raw" / "bureau_api.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(records, f)

    return records


def merge_sources(csv_path: str | Path, json_path: str | Path) -> pd.DataFrame:
    """Merge CSV (Kaggle) + JSON (bureau API) into a single staging Parquet.

    Steps (order matters):
      1. Create absence flags BEFORE fillna — isnull() is always False after
      2. Impute MonthlyIncome with median (robust to heavy right tail seen in EDA)
      3. Impute NumberOfDependents with 0 (semantically: no dependents known)
      4. Persist as Parquet without index (index=False avoids extra column
         that would break DuckDB schema in Phase 2)

    Output: data/staging/credit_applications.parquet
    """
    df = pd.read_csv(csv_path, index_col=0)

    # Flags must be created before any fillna or isnull() will return all False
    df["income_missing"] = df["MonthlyIncome"].isnull().astype(int)
    df["dependents_missing"] = df["NumberOfDependents"].isnull().astype(int)

    # Median is robust to the extreme P99 outliers found in the EDA
    df["MonthlyIncome"] = df["MonthlyIncome"].fillna(df["MonthlyIncome"].median())
    df["NumberOfDependents"] = df["NumberOfDependents"].fillna(0)

    out_path = ROOT / "data" / "staging" / "credit_applications.parquet"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)

    print(f"Staging: {len(df)} registros → {out_path}")
    return df
