"""Data contract tests for mart_credit_features.

Tests assert properties of the output data, not the code that produced it.
A passing suite means the mart satisfies its contract before being exposed
via API (Phase 3) or CI/CD pipeline (Phase 4).
"""

import pandas as pd
import pytest


@pytest.fixture
def mart():
    return pd.read_parquet("data/marts/mart_credit_features.parquet")


def test_no_nulls_in_critical_columns(mart):
    for col in ["applicant_id", "defaulted", "risk_tier", "total_late_payments"]:
        assert mart[col].isnull().sum() == 0, f"Nulos em {col}"


def test_risk_tier_valid_values(mart):
    valid = {"LOW", "MEDIUM", "HIGH"}
    actual = set(mart["risk_tier"].unique())
    assert actual.issubset(valid), f"Valores inválidos: {actual - valid}"


def test_late_payments_non_negative(mart):
    assert (mart["total_late_payments"] >= 0).all()
