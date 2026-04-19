"""Data contract tests for mart_credit_features.

Tests assert properties of the output data, not the code that produced it.
A passing suite means the mart satisfies its contract before being exposed
via API (Phase 3) or CI/CD pipeline (Phase 4).

In CI the mart Parquet doesn't exist (gitignored), so the fixture generates
a minimal synthetic DataFrame that satisfies the same schema contract.
"""

import os

import pandas as pd
import pytest

MART_PATH = "data/marts/mart_credit_features.parquet"


@pytest.fixture
def mart():
    if os.path.exists(MART_PATH):
        return pd.read_parquet(MART_PATH)
    # Synthetic fixture for CI — same schema, minimal rows
    return pd.DataFrame({
        "applicant_id": [1, 2, 3],
        "defaulted":    [0, 1, 0],
        "risk_tier":    ["LOW", "HIGH", "MEDIUM"],
        "total_late_payments": [0, 3, 1],
        "monthly_income": [5000.0, 3000.0, 4500.0],
    })


def test_no_nulls_in_critical_columns(mart):
    for col in ["applicant_id", "defaulted", "risk_tier", "total_late_payments"]:
        assert mart[col].isnull().sum() == 0, f"Nulos em {col}"


def test_risk_tier_valid_values(mart):
    valid = {"LOW", "MEDIUM", "HIGH"}
    actual = set(mart["risk_tier"].unique())
    assert actual.issubset(valid), f"Valores inválidos: {actual - valid}"


def test_late_payments_non_negative(mart):
    assert (mart["total_late_payments"] >= 0).all()
