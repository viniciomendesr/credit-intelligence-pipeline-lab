import os
import sys
from datetime import datetime, timedelta
from pathlib import Path as FilePath

import pandas as pd
from fastapi import FastAPI, HTTPException, Path

sys.path.insert(0, ".")
from src.decision_explainer_rule import explain_decision
from src.decision_explainer_ml import explain_decision_ml


# ──────────────────────────────────────────────────────────────────────────
# Loading — mart + model vêm do GCS em produção, disco em dev
# ──────────────────────────────────────────────────────────────────────────

def _load_mart() -> pd.DataFrame:
    bucket = os.getenv("MART_BUCKET")
    obj = os.getenv("MART_OBJECT")
    if bucket and obj:
        from google.cloud import storage
        local = "/tmp/mart_credit_features.parquet"
        storage.Client().bucket(bucket).blob(obj).download_to_filename(local)
        return pd.read_parquet(local)
    return pd.read_parquet("data/marts/mart_credit_features.parquet")


def _ensure_model_local() -> str | None:
    """Baixa model.pkl do GCS (se MODEL_BUCKET setado) ou usa local."""
    bucket = os.getenv("MODEL_BUCKET")
    obj = os.getenv("MODEL_OBJECT", "model-latest.pkl")
    if bucket:
        from google.cloud import storage
        local = "/tmp/model.pkl"
        storage.Client().bucket(bucket).blob(obj).download_to_filename(local)
        return local
    local = "models/model.pkl"
    return local if FilePath(local).exists() else None


# ──────────────────────────────────────────────────────────────────────────
# Swagger UI — descrição rica + tags + exemplos de IDs
# ──────────────────────────────────────────────────────────────────────────

API_DESCRIPTION = """
API pública de análise de crédito com decisão explicável via LLM.
Parte do [Credit Intelligence Pipeline Lab](https://github.com/viniciomendesr/credit-intelligence-pipeline-lab)
— projeto pedagógico pessoal de engenharia de dados/IA aplicada a crédito.

## 🚀 Quickstart em 30 segundos

1. **Expanda** `GET /risk-summary` → **Try it out** → **Execute**.
   Você verá a distribuição da carteira (~144k registros).
2. **Expanda** `GET /explain-decision/rule/{applicant_id}` → **Try it out** →
   digite `37167` → **Execute**. LLM narra uma decisão APROVADO via regra SQL.
3. **Expanda** `GET /explain-decision/ml/{applicant_id}` → **Try it out** →
   digite `37167` → **Execute**. Agora a narrativa vem do modelo XGBoost + SHAP.

## 🎯 IDs sugeridos — compare v1 (rule) vs v2 (ml) no mesmo tomador

| ID | Tier (rule) | Prob (ml) | Por que testar |
|---:|---|---|---|
| **37167** | LOW | ~1% | APROVADO em ambos — caso fácil |
| **50821** | MEDIUM | ~7% | LIMITE em ambos — caso intermediário |
| **23380** | HIGH | ~36% | **divergência:** rule NEGA, ML dá LIMITE — regra univariada vs. modelo multivariado |

O ID **23380** é o caso mais didático: o modelo treinado em 144k
históricos é **menos conservador** que a regra SQL baseada apenas em
`revolving_utilization > 0.9`.

## 🧠 O que cada endpoint retorna

- **v1 (rule)**: decisão vem da regra SQL da Fase 2 (categórica: LOW/MEDIUM/HIGH).
  Extrator escolhe top-3 fatores por **desvio vs. mediana** da carteira.
- **v2 (ml)**: decisão vem de probabilidade calibrada do XGBoost
  (AUC 0.857 vs 0.764 do baseline rule-based). Extrator escolhe top-3
  fatores por **SHAP values nativos** do XGBoost. Threshold: `<0.30 → APROVADO`,
  `0.30-0.60 → LIMITE`, `≥0.60 → NEGADO`.

Ambos têm **guardrails contra alucinação** no prompt (LLM só pode citar valores
passados pelo extrator determinístico) e **eval programático** validado com
pass rate ≥ 95% em 21 amostras estratificadas.

## 📊 Dataset

[Kaggle Give Me Some Credit](https://www.kaggle.com/competitions/GiveMeSomeCredit)
(2011) — ~150k tomadores anônimos, 11 features, label `defaulted`
(inadimplência 90+ dias em 2 anos). IDs válidos variam de ~1 a ~150000
(alguns excluídos por outliers).

## 💰 Custo por chamada (Anthropic Claude Haiku 4.5)

Cada chamada aos endpoints de explicação custa ~US$ 0,001 (≈ R$ 0,005).
Cache por chave com TTL de 30 minutos economiza repetições.

## 📁 Código-fonte

Ver [github.com/viniciomendesr/credit-intelligence-pipeline-lab](https://github.com/viniciomendesr/credit-intelligence-pipeline-lab).
"""

TAGS_METADATA = [
    {
        "name": "Status",
        "description": (
            "Saúde da API e estatísticas agregadas da carteira. "
            "Use estes endpoints primeiro para ver o contexto antes de "
            "pedir explicações individuais."
        ),
    },
    {
        "name": "Explicabilidade v1 (rule-based)",
        "description": (
            "LLM narra a decisão gerada pela **regra SQL** da Fase 2. "
            "Top-3 fatores escolhidos por desvio-vs-mediana da carteira. "
            "Decisão categórica (LOW/MEDIUM/HIGH)."
        ),
    },
    {
        "name": "Explicabilidade v2 (modelo ML)",
        "description": (
            "LLM narra a decisão do **XGBoost calibrado** da Fase 5. "
            "Top-3 fatores escolhidos por SHAP values nativos. Decisão "
            "derivada de probabilidade calibrada (`pred_default_prob`)."
        ),
    },
]


app = FastAPI(
    title="Credit Intelligence API",
    description=API_DESCRIPTION,
    version="0.1.0",
    openapi_tags=TAGS_METADATA,
    contact={
        "name": "credit-intelligence-pipeline-lab",
        "url": "https://github.com/viniciomendesr/credit-intelligence-pipeline-lab",
    },
)

df = _load_mart()
MODEL_PATH = _ensure_model_local()

# ──────────────────────────────────────────────────────────────────────────
# Exemplos reutilizados nos dois endpoints /explain-decision/*
# ──────────────────────────────────────────────────────────────────────────

APPLICANT_ID_EXAMPLES = {
    "Caso fácil — APROVADO": {
        "summary": "ID 37167 (perfil limpo)",
        "description": (
            "Renda R$ 10.750, uso de crédito rotativo 10%, sem atrasos. "
            "**Rule e ML concordam: APROVADO.**"
        ),
        "value": 37167,
    },
    "Caso intermediário — LIMITE": {
        "summary": "ID 50821 (perfil médio)",
        "description": (
            "Renda R$ 7.195, uso 63% do limite rotativo, razão dívida/renda "
            "0.82. **Rule e ML concordam: APROVADO_COM_LIMITE.**"
        ),
        "value": 50821,
    },
    "Caso divergente — NEGADO vs LIMITE": {
        "summary": "ID 23380 (v1 e v2 divergem)",
        "description": (
            "Renda R$ 4.000, uso **100%** do limite rotativo. "
            "**Rule: NEGADO** (tier HIGH por regra univariada). "
            "**ML: APROVADO_COM_LIMITE** (prob ~36%, modelo considera o "
            "quadro completo). Caso mais pedagógico pra comparar v1 vs v2."
        ),
        "value": 23380,
    },
}


# ──────────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["Status"], summary="Healthcheck da API")
def health():
    """Checa se a API está no ar.

    Retorna status + timestamp + número de registros carregados em memória.
    Use como primeiro teste — se responder `status: ok` com `records > 0`,
    o mart carregou do GCS e os outros endpoints estão prontos.
    """
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "records": len(df),
    }


@app.get(
    "/risk-summary",
    tags=["Status"],
    summary="Estatísticas agregadas da carteira",
)
def risk_summary():
    """Agregados da carteira de crédito completa.

    Retorna:
    - **`total_records`**: número de tomadores no mart
    - **`default_rate_pct`**: taxa de inadimplência histórica (label real do Kaggle)
    - **`risk_tier_distribution_pct`**: distribuição LOW/MEDIUM/HIGH via regra SQL
    - **`median_income_by_tier`**: renda mediana por tier

    **Insight pedagógico:** reparem que LOW e MEDIUM têm mediana de renda
    igual — sinal de que a regra SQL é univariada (só olha `revolving_utilization`
    + atrasos, ignora renda). A Fase 5 corrige isso treinando um modelo
    multivariado.
    """
    return {
        "total_records": len(df),
        "default_rate_pct": round(df['defaulted'].mean() * 100, 2),
        "risk_tier_distribution_pct": (
            df['risk_tier']
            .value_counts(normalize=True)
            .mul(100).round(2)
            .to_dict()
        ),
        "median_income_by_tier": (
            df.groupby('risk_tier')['monthly_income']
            .median().round(2)
            .to_dict()
        ),
    }


_explanation_cache: dict[int, dict] = {}
EXPLANATION_TTL = timedelta(minutes=30)


@app.get(
    "/explain-decision/rule/{applicant_id}",
    tags=["Explicabilidade v1 (rule-based)"],
    summary="Explica decisão gerada pela regra SQL, narrada por LLM",
)
def explain_rule(
    applicant_id: int = Path(
        ...,
        title="ID do tomador",
        description=(
            "ID inteiro do tomador no mart. Valores aproximadamente entre "
            "1 e 150.000. Selecione um exemplo no menu abaixo ou digite "
            "qualquer ID válido."
        ),
        openapi_examples=APPLICANT_ID_EXAMPLES,
    ),
):
    """Narra a decisão de crédito gerada pela **regra SQL da Fase 2**.

    **Fluxo interno**:
    1. Busca o tomador no mart
    2. Mapeia `risk_tier` → decisão categórica (LOW=APROVADO,
       MEDIUM=APROVADO_COM_LIMITE, HIGH=NEGADO)
    3. Extrator determinístico escolhe 3 fatores com maior desvio vs.
       mediana da carteira
    4. LLM (Claude Haiku 4.5) narra em PT-BR com guardrails contra alucinação
       (só pode citar os valores do extrator — não inventa número)

    **Campos da resposta**:
    - `decision`: APROVADO / APROVADO_COM_LIMITE / NEGADO
    - `risk_tier`: LOW / MEDIUM / HIGH
    - `key_factors[]`: top-3 fatores com `value`, `median`, `deviation_ratio`, `direction`
    - `narrative`: texto PT-BR gerado pelo LLM
    - `_usage`: tokens + modelo (observabilidade de custo)
    - `cached`: `true` se resposta veio do cache em memória

    **Cache**: TTL 30min por `applicant_id`. Segunda chamada no mesmo ID
    volta em ~30ms com `cached: true`.

    **Errors**:
    - `404` — ID não existe no mart
    - `503` — `ANTHROPIC_API_KEY` não configurada no runtime
    """
    now = datetime.now()
    cached = _explanation_cache.get(applicant_id)
    if cached and (now - cached["_cached_at"]) < EXPLANATION_TTL:
        return {**{k: v for k, v in cached.items() if k != "_cached_at"}, "cached": True}

    try:
        result = explain_decision(applicant_id, mart=df)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except KeyError:
        raise HTTPException(
            status_code=503,
            detail="ANTHROPIC_API_KEY ausente no runtime",
        )

    _explanation_cache[applicant_id] = {**result, "_cached_at": now}
    return {**result, "cached": False}


# Cache separado pra v2 — mesma chave (applicant_id), respostas diferentes.
_explanation_cache_ml: dict[int, dict] = {}


@app.get(
    "/explain-decision/ml/{applicant_id}",
    tags=["Explicabilidade v2 (modelo ML)"],
    summary="Explica decisão do modelo XGBoost via SHAP, narrada por LLM",
)
def explain_ml(
    applicant_id: int = Path(
        ...,
        title="ID do tomador",
        description=(
            "ID inteiro do tomador no mart. **Tente o mesmo ID que você "
            "usou no endpoint `/rule/` acima para comparar as narrativas.**"
        ),
        openapi_examples=APPLICANT_ID_EXAMPLES,
    ),
):
    """Narra a decisão do **modelo XGBoost calibrado da Fase 5**, via SHAP.

    **Diferenças vs v1 (rule)**:
    - Decisão vem de **probabilidade calibrada** (`pred_default_prob`), não
      de regra fixa. Threshold: `<0.30 → APROVADO`, `0.30-0.60 → LIMITE`,
      `≥0.60 → NEGADO`.
    - Top-3 fatores vêm de **SHAP values nativos** do XGBoost (contribuição
      real daquela feature pra probabilidade daquele tomador específico),
      não de heurística de desvio-vs-mediana.
    - O modelo tem AUC 0.857 vs 0.764 do baseline rule-based (+0.094).

    **Experimente**: chame `/rule/23380` e depois `/ml/23380`. A regra SQL
    diz NEGADO (tier HIGH por uso 100% do limite rotativo), mas o modelo
    treinado diz APROVADO_COM_LIMITE (prob ~36%) — porque considera todas
    as features juntas, não só uma.

    **Campos da resposta**:
    - `decision`: APROVADO / APROVADO_COM_LIMITE / NEGADO
    - `pred_default_prob`: probabilidade de inadimplência (0-1), calibrada via isotonic
    - `key_factors[]`: top-3 fatores com `value`, `shap_value`, `direction`
    - `narrative`: texto PT-BR
    - `_usage`: tokens + modelo
    - `cached`: `true` se veio do cache

    **Errors**:
    - `404` — ID não existe no mart
    - `503` — modelo não disponível OU `ANTHROPIC_API_KEY` ausente
    """
    if MODEL_PATH is None:
        raise HTTPException(
            status_code=503,
            detail="Modelo não disponível. Treine com `python -m src.train` "
            "ou configure MODEL_BUCKET/MODEL_OBJECT.",
        )

    now = datetime.now()
    cached = _explanation_cache_ml.get(applicant_id)
    if cached and (now - cached["_cached_at"]) < EXPLANATION_TTL:
        return {**{k: v for k, v in cached.items() if k != "_cached_at"}, "cached": True}

    try:
        result = explain_decision_ml(applicant_id, mart=df, model_path=MODEL_PATH)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except KeyError:
        raise HTTPException(
            status_code=503,
            detail="ANTHROPIC_API_KEY ausente no runtime",
        )

    _explanation_cache_ml[applicant_id] = {**result, "_cached_at": now}
    return {**result, "cached": False}
