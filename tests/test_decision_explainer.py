"""Testes da lógica determinística do decision_explainer.

Não chama LLM — testa só ``extract_context``, que é puro e deve ter
saída reprodutível. A validação do comportamento do LLM vive em
``scripts/eval_explainer.py`` (B.3), que roda separadamente com custo.
"""

import pandas as pd
import pytest

from src.decision_explainer import DECISION_BY_TIER, extract_context


@pytest.fixture
def synthetic_mart():
    """Mart sintético com schema completo do mart_credit_features."""
    return pd.DataFrame({
        "applicant_id":          [1,     2,     3,     4,     5],
        "defaulted":             [0,     1,     0,     1,     0],
        "age":                   [35,    52,    28,    41,    60],
        "monthly_income":        [5000,  3000,  4500,  2000,  8000],
        "revolving_utilization": [0.2,   0.95,  0.5,   0.92,  0.1],
        "debt_ratio":            [0.3,   1.8,   0.5,   2.1,   0.2],
        "late_30_59_days":       [0,     3,     1,     5,     0],
        "late_60_89_days":       [0,     2,     0,     3,     0],
        "late_90_days":          [0,     1,     0,     4,     0],
        "income_missing":        [0,     0,     0,     1,     0],
        "risk_tier":             ["LOW", "HIGH", "MEDIUM", "HIGH", "LOW"],
    })


def test_decision_map_complete():
    assert set(DECISION_BY_TIER.keys()) == {"LOW", "MEDIUM", "HIGH"}
    assert DECISION_BY_TIER["HIGH"] == "NEGADO"


def test_extract_context_low_tier(synthetic_mart):
    ctx = extract_context(1, mart=synthetic_mart)
    assert ctx["applicant_id"] == 1
    assert ctx["risk_tier"] == "LOW"
    assert ctx["decision"] == "APROVADO"
    assert len(ctx["key_factors"]) == 3


def test_extract_context_high_tier_surfaces_risk_driver(synthetic_mart):
    """NEGADO deve ter ao menos um fator de risco no top-3.

    Esse invariante é o que o check ``aligned`` do eval (B.3) valida
    em lote — aqui garantimos a nível unitário.
    """
    ctx = extract_context(4, mart=synthetic_mart)
    assert ctx["decision"] == "NEGADO"
    has_risk_driver = any(
        f["direction"] == "alto_aumenta_risco" for f in ctx["key_factors"]
    )
    assert has_risk_driver


def test_extract_context_deterministic(synthetic_mart):
    """Mesma entrada → mesma saída. Sem aleatoriedade, sem timestamp."""
    a = extract_context(2, mart=synthetic_mart)
    b = extract_context(2, mart=synthetic_mart)
    assert a == b


def test_extract_context_unknown_id_raises(synthetic_mart):
    with pytest.raises(ValueError, match="não encontrado"):
        extract_context(9999, mart=synthetic_mart)


def test_key_factors_shape(synthetic_mart):
    """Cada fator tem os campos que o prompt e o eval dependem."""
    ctx = extract_context(4, mart=synthetic_mart)
    required = {"feature", "label", "value", "median", "deviation_ratio", "direction"}
    for f in ctx["key_factors"]:
        assert required.issubset(f.keys()), f"faltam campos em {f}"
        assert f["direction"] in {"alto_aumenta_risco", "alto_reduz_risco", "neutro"}


def test_key_factors_sorted_by_deviation(synthetic_mart):
    """Top-3 fatores devem vir ordenados por |deviation_ratio| descendente."""
    ctx = extract_context(4, mart=synthetic_mart)
    ratios = [abs(f["deviation_ratio"]) for f in ctx["key_factors"]]
    assert ratios == sorted(ratios, reverse=True)
