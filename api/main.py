import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException

sys.path.insert(0, ".")
from src.decision_explainer_rule import explain_decision
from src.decision_explainer_ml import explain_decision_ml


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
    """Baixa model.pkl do GCS (se MODEL_BUCKET setado) ou usa local.

    Retorna o path pro bundle, ou None se o modelo não está disponível
    (dev local sem pkl treinado + sem MODEL_BUCKET). Nesse caso, o
    endpoint /ml retorna 503.
    """
    bucket = os.getenv("MODEL_BUCKET")
    obj = os.getenv("MODEL_OBJECT", "model-latest.pkl")
    if bucket:
        from google.cloud import storage
        local = "/tmp/model.pkl"
        storage.Client().bucket(bucket).blob(obj).download_to_filename(local)
        return local
    local = "models/model.pkl"
    return local if Path(local).exists() else None


app = FastAPI(title="Credit Intelligence API")

df = _load_mart()
MODEL_PATH = _ensure_model_local()


@app.get("/health")
def health():
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "records": len(df),
    }


@app.get("/risk-summary")
def risk_summary():
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


@app.get("/explain-decision/rule/{applicant_id}")
def explain_rule(applicant_id: int):
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


@app.get("/explain-decision/ml/{applicant_id}")
def explain_ml(applicant_id: int):
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
