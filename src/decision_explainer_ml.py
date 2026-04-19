"""Reason-code extractor via SHAP + LLM narrator — Bônus Fase 5 (v2).

Refinement of ``decision_explainer_rule.py``:

- **v1 (rule)**: decisão vem de ``risk_tier`` (regra SQL), top-3 fatores
  escolhidos por desvio-vs-mediana (heurística).
- **v2 (ml)**: decisão vem de ``pred_default_prob`` (modelo treinado na
  Fase 5), top-3 fatores escolhidos por ``|SHAP value|`` (principiado).

Separação extrator/narrador, guardrails contra alucinação, ``_usage``
pra observabilidade de custo — tudo idêntico ao v1. A única mudança
semântica é *o que o extrator escolhe mostrar*.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

DECISION_BY_PROB = [
    (0.30, "APROVADO"),
    (0.60, "APROVADO_COM_LIMITE"),
    (1.01, "NEGADO"),
]

_CLIENT = None
_BUNDLE: dict[str, Any] | None = None
_BOOSTER = None  # xgboost.Booster do estimator base (pra SHAP nativo)


def _get_bundle(model_path: str = "models/model.pkl") -> dict[str, Any]:
    """Carrega o bundle e extrai o Booster XGBoost para SHAP nativo.

    Cache em módulo — roda uma vez por processo. Usa ``Booster.predict(
    DMatrix, pred_contribs=True)`` em vez da lib ``shap`` pra evitar
    incompatibilidade SHAP 0.48 ↔ XGBoost 3.x no parser de base_score.
    """
    global _BUNDLE, _BOOSTER
    if _BUNDLE is None:
        _BUNDLE = joblib.load(model_path)
        # CalibratedClassifierCV wrappa XGB. predict_proba vem dele (calibrado),
        # mas SHAP values vêm do booster base (nativo, sem lib shap).
        base = _BUNDLE["model"].calibrated_classifiers_[0].estimator
        _BOOSTER = base.get_booster()
    return _BUNDLE


def _shap_values_for_row(X_row: pd.DataFrame) -> list[float]:
    """Retorna SHAP values da linha via Booster nativo (sem lib shap).

    ``pred_contribs=True`` retorna (n_samples, n_features + 1) onde a
    última coluna é o bias (valor esperado). Descartamos essa coluna.
    """
    from xgboost import DMatrix
    assert _BOOSTER is not None
    contribs = _BOOSTER.predict(DMatrix(X_row), pred_contribs=True)
    return contribs[0, :-1].tolist()


def _get_client():
    global _CLIENT
    if _CLIENT is None:
        from anthropic import Anthropic
        _CLIENT = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _CLIENT


def _validate_features(mart: pd.DataFrame, required: list[str]) -> None:
    """T.9#2 — feature validation em inferência.

    Se o mart perdeu alguma coluna que o modelo espera, falha alto e
    barulhento em vez de silenciosamente usar reordenação do pandas.
    """
    missing = set(required) - set(mart.columns)
    if missing:
        raise RuntimeError(
            f"Mart perdeu features que o modelo espera: {sorted(missing)}. "
            "Modelo precisa ser retreinado ou mart precisa ser regenerado."
        )


def _decision_from_prob(prob: float) -> str:
    for threshold, label in DECISION_BY_PROB:
        if prob < threshold:
            return label
    return "NEGADO"


def extract_context_ml(
    applicant_id: int,
    mart: pd.DataFrame,
    model_path: str = "models/model.pkl",
) -> dict[str, Any]:
    """Determinístico: carrega modelo, calcula prob + top-3 SHAP values."""
    bundle = _get_bundle(model_path)
    features = bundle["features"]

    _validate_features(mart, features)

    match = mart[mart["applicant_id"] == applicant_id]
    if match.empty:
        raise ValueError(f"applicant_id {applicant_id} não encontrado no mart")

    X = match[features]
    prob = float(bundle["model"].predict_proba(X)[0, 1])
    shap_row = _shap_values_for_row(X)

    factors = []
    for i, feat in enumerate(features):
        sv = float(shap_row[i])
        val = float(X.iloc[0][feat])
        factors.append({
            "feature": feat,
            "value": round(val, 4),
            "shap_value": round(sv, 4),
            "direction": "aumenta_risco" if sv > 0 else "reduz_risco",
        })
    factors.sort(key=lambda d: abs(d["shap_value"]), reverse=True)

    return {
        "applicant_id": int(applicant_id),
        "pred_default_prob": round(prob, 4),
        "decision": _decision_from_prob(prob),
        "key_factors": factors[:3],
    }


def _build_prompt(ctx: dict[str, Any]) -> str:
    factors_text = "\n".join(
        f"- {f['feature']} = {f['value']}  "
        f"(SHAP = {f['shap_value']:+.3f}, {f['direction']})"
        for f in ctx["key_factors"]
    )
    pct = ctx["pred_default_prob"] * 100
    return f"""Você é um analista de crédito de um motor de crédito B2B. O modelo estimou probabilidade de inadimplência de {pct:.1f}%. Decisão: {ctx['decision']}.

Top-3 fatores que mais contribuíram para essa probabilidade (SHAP values — maior magnitude absoluta):
{factors_text}

Escreva uma explicação em português, máximo 3 frases, dirigida ao próprio tomador.

RESTRIÇÕES OBRIGATÓRIAS:
- Cite APENAS os valores/percentuais listados acima (o valor da feature, a probabilidade {pct:.1f}%, e opcionalmente o sinal do SHAP). Não invente números.
- Não mencione raça, gênero, endereço, CEP ou qualquer atributo sensível.
- Não prometa reversão da decisão. Seja factual, não motivacional.
- Não mencione "SHAP" nem termos técnicos — fale com o tomador."""


def explain_decision_ml(
    applicant_id: int,
    mart: pd.DataFrame,
    model_path: str = "models/model.pkl",
    llm_model: str = "claude-haiku-4-5-20251001",
) -> dict[str, Any]:
    """Context determinístico + narrativa via LLM com guardrails."""
    ctx = extract_context_ml(applicant_id, mart, model_path)
    prompt = _build_prompt(ctx)

    client = _get_client()
    response = client.messages.create(
        model=llm_model,
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    return {
        **ctx,
        "narrative": response.content[0].text,
        "generated_at": datetime.now().isoformat(),
        "_usage": {
            "model": response.model,
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        },
    }
