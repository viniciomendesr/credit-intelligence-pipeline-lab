"""Testes da lógica determinística do decision_explainer_ml (SHAP nativo).

Treina um XGB mini in-fixture pra não depender de ``models/model.pkl``
(gitignored, não existe em CI). Testa apenas ``extract_context_ml`` —
``explain_decision_ml`` chama LLM e fica no eval (B5.3), não no pytest.
"""

import numpy as np
import pandas as pd
import pytest
from sklearn.calibration import CalibratedClassifierCV
from xgboost import XGBClassifier

from src.decision_explainer_ml import (
    _decision_from_prob,
    _validate_features,
    extract_context_ml,
)


@pytest.fixture
def mini_model_and_mart(tmp_path):
    """Cria mart sintético + treina XGB mini + serializa bundle."""
    import joblib

    n = 300
    rng = np.random.default_rng(0)
    features = [
        "age", "monthly_income", "revolving_utilization", "debt_ratio",
        "open_credit_lines", "dependents", "income_missing",
        "late_30_59_days", "late_60_89_days", "late_90_days",
        "total_late_payments",
    ]
    X_df = pd.DataFrame({
        "age":                   rng.integers(18, 80, n),
        "monthly_income":        rng.normal(5000, 2000, n).clip(500, None),
        "revolving_utilization": rng.uniform(0, 1, n),
        "debt_ratio":            rng.uniform(0, 2, n),
        "open_credit_lines":     rng.integers(0, 20, n),
        "dependents":            rng.integers(0, 5, n),
        "income_missing":        rng.choice([0, 1], n, p=[0.8, 0.2]),
        "late_30_59_days":       rng.integers(0, 5, n),
        "late_60_89_days":       rng.integers(0, 3, n),
        "late_90_days":          rng.integers(0, 3, n),
        "total_late_payments":   rng.integers(0, 10, n),
    })
    # Label correlacionado com late_90_days pra treino não virar random
    y = (X_df["late_90_days"] > 0).astype(int) | (rng.random(n) < 0.05).astype(int)

    # Modelo bem pequeno (rápido)
    base = XGBClassifier(
        n_estimators=20, max_depth=3, learning_rate=0.3,
        eval_metric="logloss", random_state=42, n_jobs=1,
    )
    calibrated = CalibratedClassifierCV(base, method="isotonic", cv=3)
    calibrated.fit(X_df, y)

    bundle = {
        "model": calibrated,
        "features": features,
        "trained_at": "2026-01-01T00:00:00",
        "git_sha": "test",
        "n_train": n,
        "scale_pos_weight": 1.0,
    }
    model_path = tmp_path / "model.pkl"
    joblib.dump(bundle, model_path)

    # Mart sintético com applicant_id
    mart = X_df.copy()
    mart["applicant_id"] = np.arange(n)
    mart["defaulted"] = y
    mart["risk_tier"] = "LOW"
    mart["loaded_at"] = pd.Timestamp("2026-01-01")
    mart["has_90day_default"] = (X_df["late_90_days"] > 0).astype(int)

    # Reset caches do módulo (se houver estado de teste anterior)
    import src.decision_explainer_ml as mod
    mod._BUNDLE = None
    mod._BOOSTER = None

    return str(model_path), mart


def test_decision_from_prob_thresholds():
    assert _decision_from_prob(0.10) == "APROVADO"
    assert _decision_from_prob(0.29) == "APROVADO"
    assert _decision_from_prob(0.30) == "APROVADO_COM_LIMITE"
    assert _decision_from_prob(0.59) == "APROVADO_COM_LIMITE"
    assert _decision_from_prob(0.60) == "NEGADO"
    assert _decision_from_prob(0.99) == "NEGADO"


def test_validate_features_raises_when_missing():
    df = pd.DataFrame({"a": [1], "b": [2]})
    with pytest.raises(RuntimeError, match="perdeu features"):
        _validate_features(df, ["a", "c", "d"])


def test_validate_features_ok_when_superset():
    df = pd.DataFrame({"a": [1], "b": [2], "extra": [3]})
    # não raises
    _validate_features(df, ["a", "b"])


def test_extract_context_ml_shape(mini_model_and_mart):
    model_path, mart = mini_model_and_mart
    ctx = extract_context_ml(50, mart, model_path=model_path)
    assert ctx["applicant_id"] == 50
    assert 0.0 <= ctx["pred_default_prob"] <= 1.0
    assert ctx["decision"] in {"APROVADO", "APROVADO_COM_LIMITE", "NEGADO"}
    assert len(ctx["key_factors"]) == 3
    for f in ctx["key_factors"]:
        assert {"feature", "value", "shap_value", "direction"}.issubset(f.keys())
        assert f["direction"] in {"aumenta_risco", "reduz_risco"}


def test_extract_context_ml_deterministic(mini_model_and_mart):
    model_path, mart = mini_model_and_mart
    a = extract_context_ml(10, mart, model_path=model_path)
    b = extract_context_ml(10, mart, model_path=model_path)
    assert a == b


def test_extract_context_ml_sorted_by_abs_shap(mini_model_and_mart):
    model_path, mart = mini_model_and_mart
    ctx = extract_context_ml(20, mart, model_path=model_path)
    magnitudes = [abs(f["shap_value"]) for f in ctx["key_factors"]]
    assert magnitudes == sorted(magnitudes, reverse=True)


def test_extract_context_ml_unknown_id_raises(mini_model_and_mart):
    model_path, mart = mini_model_and_mart
    with pytest.raises(ValueError, match="não encontrado"):
        extract_context_ml(99999, mart, model_path=model_path)
