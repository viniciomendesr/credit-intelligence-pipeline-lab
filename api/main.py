import os
from datetime import datetime

import pandas as pd
from fastapi import FastAPI, HTTPException


def _load_mart() -> pd.DataFrame:
    bucket = os.getenv("MART_BUCKET")
    obj = os.getenv("MART_OBJECT")
    if bucket and obj:
        from google.cloud import storage
        local = "/tmp/mart_credit_features.parquet"
        storage.Client().bucket(bucket).blob(obj).download_to_filename(local)
        return pd.read_parquet(local)
    return pd.read_parquet("data/marts/mart_credit_features.parquet")


app = FastAPI(title="Credit Intelligence API")

df = _load_mart()


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
