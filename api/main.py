from datetime import datetime

import pandas as pd
from fastapi import FastAPI, HTTPException

app = FastAPI(title="Credit Intelligence API")

# Lido uma vez no startup — não a cada request
df = pd.read_parquet('data/marts/mart_credit_features.parquet')


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
