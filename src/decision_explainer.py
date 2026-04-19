"""Reason-code extractor + LLM narrator for credit decisions.

Two responsibilities, intentionally separated:

1. ``extract_context`` — deterministic: given an ``applicant_id``, reads the
   mart, picks the top-3 features whose value deviates the most from the
   portfolio median, and maps ``risk_tier`` to a human decision label.
   No LLM. Same input → same output. Unit-testable.

2. ``explain_decision`` — wraps ``extract_context`` and asks the LLM to
   narrate the result in PT-BR with explicit guardrails in the prompt
   (cite only values from context, no sensitive attributes, ≤3 sentences).

Splitting the two is what makes the endpoint auditable: compliance can
review exactly which features may be surfaced to the borrower and the
LLM only controls tone, not facts.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import pandas as pd

DECISION_BY_TIER = {
    "LOW": "APROVADO",
    "MEDIUM": "APROVADO_COM_LIMITE",
    "HIGH": "NEGADO",
}

# (column_in_mart, human_label, direction_in_risk)
FEATURES: list[tuple[str, str, str]] = [
    ("revolving_utilization", "Uso do limite rotativo (0-1)", "alto_aumenta_risco"),
    ("debt_ratio",            "Razão dívida/renda",            "alto_aumenta_risco"),
    ("monthly_income",        "Renda mensal declarada (R$)",   "alto_reduz_risco"),
    ("late_30_59_days",       "Atrasos recentes (30-59 dias)", "alto_aumenta_risco"),
    ("late_60_89_days",       "Atrasos médios (60-89 dias)",   "alto_aumenta_risco"),
    ("late_90_days",          "Atrasos graves (90+ dias)",     "alto_aumenta_risco"),
    ("income_missing",        "Renda não declarada (flag 0/1)", "alto_aumenta_risco"),
    ("age",                   "Idade",                         "neutro"),
]

_MART_CACHE: dict[str, pd.DataFrame] = {}
_CLIENT = None


def _load_mart(mart_path: str) -> pd.DataFrame:
    if mart_path not in _MART_CACHE:
        _MART_CACHE[mart_path] = pd.read_parquet(mart_path)
    return _MART_CACHE[mart_path]


def _get_client():
    global _CLIENT
    if _CLIENT is None:
        from anthropic import Anthropic
        _CLIENT = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _CLIENT


def extract_context(
    applicant_id: int,
    mart_path: str = "data/marts/mart_credit_features.parquet",
    mart: pd.DataFrame | None = None,
) -> dict[str, Any]:
    df = mart if mart is not None else _load_mart(mart_path)

    match = df[df["applicant_id"] == applicant_id]
    if match.empty:
        raise ValueError(f"applicant_id {applicant_id} não encontrado no mart")
    row = match.iloc[0]

    cols = [f[0] for f in FEATURES if f[0] in df.columns]
    medians = df[cols].median(numeric_only=True)

    factors: list[dict[str, Any]] = []
    for col, label, direction in FEATURES:
        if col not in df.columns:
            continue
        val = float(row[col])
        med = float(medians[col])
        ratio = (val - med) / (abs(med) + 1e-9)
        factors.append({
            "feature": col,
            "label": label,
            "value": round(val, 2),
            "median": round(med, 2),
            "deviation_ratio": round(ratio, 2),
            "direction": direction,
        })
    factors.sort(key=lambda f: abs(f["deviation_ratio"]), reverse=True)

    tier = str(row["risk_tier"])
    return {
        "applicant_id": int(applicant_id),
        "risk_tier": tier,
        "decision": DECISION_BY_TIER[tier],
        "key_factors": factors[:3],
    }


def _build_prompt(ctx: dict[str, Any]) -> str:
    factors_text = "\n".join(
        f"- {f['label']}: {f['value']} (mediana da carteira: {f['median']})"
        for f in ctx["key_factors"]
    )
    return f"""Você é um analista de crédito da Core AI. Um tomador recebeu a decisão {ctx['decision']} (tier de risco {ctx['risk_tier']}).

Fatores extraídos pelo motor de risco:
{factors_text}

Escreva uma explicação em português, máximo 3 frases, dirigida ao próprio tomador.

RESTRIÇÕES OBRIGATÓRIAS:
- Cite APENAS os valores listados acima. Não invente números.
- Não mencione raça, gênero, endereço, CEP ou qualquer atributo sensível.
- Não prometa reversão da decisão. Seja factual, não motivacional."""


def explain_decision(
    applicant_id: int,
    mart_path: str = "data/marts/mart_credit_features.parquet",
    mart: pd.DataFrame | None = None,
    model: str = "claude-haiku-4-5-20251001",
) -> dict[str, Any]:
    ctx = extract_context(applicant_id, mart_path, mart=mart)
    prompt = _build_prompt(ctx)

    client = _get_client()
    response = client.messages.create(
        model=model,
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
