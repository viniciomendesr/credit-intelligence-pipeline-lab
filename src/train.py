"""Training pipeline — Fase 5.

Treina um XGBoost calibrado em cima do mart pra prever ``defaulted``,
compara métricas contra o baseline rule-based da Fase 2 (onde
``risk_tier`` é derivado de uma regra SQL), e persiste artefatos:

- ``models/model.pkl`` — bundle (modelo calibrado + features + sha do commit)
- ``reports/model_metrics.json`` — AUC/precision@k/log-loss pra model e
  baseline, com delta.

Uso:
    python -m src.train                      # treina com defaults
    python -m src.train --mart outro.parquet # mart alternativo
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import log_loss, roc_auc_score
from sklearn.model_selection import train_test_split
from xgboost import XGBClassifier

from src.logger import get_logger

log = get_logger("train")

MART_PATH_DEFAULT = "data/marts/mart_credit_features.parquet"
MODEL_PATH_DEFAULT = "models/model.pkl"
METRICS_PATH_DEFAULT = "reports/model_metrics.json"
SEED = 42

# Colunas excluídas do X:
# - applicant_id: chave natural, não é feature
# - defaulted: label (target)
# - risk_tier: derivado da regra SQL que estamos tentando bater — vazamento
# - loaded_at: metadado de ingestão
# - has_90day_default: derivado direto de late_90_days — vazamento redundante
EXCLUDE_COLS = {
    "applicant_id",
    "defaulted",
    "risk_tier",
    "loaded_at",
    "has_90day_default",
}

TIER_ORDINAL = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}


def prepare_dataset(
    mart_path: str = MART_PATH_DEFAULT,
    test_size: float = 0.2,
    random_state: int = SEED,
):
    """Carrega mart e faz split 80/20 estratificado por ``defaulted``.

    Retorna (X_train, X_test, y_train, y_test, df_test_meta), onde
    ``df_test_meta`` é o subset original do mart alinhado ao test set
    (útil pra baseline rule-based que precisa de ``risk_tier``).
    """
    df = pd.read_parquet(mart_path)
    feature_cols = [c for c in df.columns if c not in EXCLUDE_COLS]
    X = df[feature_cols].copy()
    y = df["defaulted"].astype(int)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, stratify=y, random_state=random_state
    )
    df_test_meta = df.loc[X_test.index]
    return X_train, X_test, y_train, y_test, df_test_meta


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True
        ).strip()
    except Exception:
        return "unknown"


def train_model(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    out_path: str = MODEL_PATH_DEFAULT,
) -> dict:
    """Treina XGBoost com calibração isotonic e persiste o bundle."""
    scale_pos_weight = (len(y_train) - y_train.sum()) / max(y_train.sum(), 1)

    base = XGBClassifier(
        n_estimators=200,
        max_depth=5,
        learning_rate=0.1,
        scale_pos_weight=scale_pos_weight,
        eval_metric="logloss",
        random_state=SEED,
        n_jobs=-1,
    )
    calibrated = CalibratedClassifierCV(base, method="isotonic", cv=3)
    calibrated.fit(X_train, y_train)

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    bundle = {
        "model": calibrated,
        "features": list(X_train.columns),
        "trained_at": datetime.now().isoformat(),
        "git_sha": _git_sha(),
        "n_train": int(len(X_train)),
        "scale_pos_weight": float(scale_pos_weight),
    }
    joblib.dump(bundle, out_path)
    return bundle


def _precision_at_k(y_true: pd.Series, scores: np.ndarray, k_pct: float) -> float:
    n_top = max(int(len(y_true) * k_pct), 1)
    idx = np.argsort(scores)[::-1][:n_top]
    return float(y_true.iloc[idx].mean() if hasattr(y_true, "iloc") else y_true[idx].mean())


def evaluate_and_benchmark(
    bundle: dict,
    X_test: pd.DataFrame,
    y_test: pd.Series,
    df_test_meta: pd.DataFrame,
    out_path: str = METRICS_PATH_DEFAULT,
) -> dict:
    """Calcula métricas do modelo ML e do baseline rule-based, compara."""
    model = bundle["model"]
    y_proba = model.predict_proba(X_test)[:, 1]

    # Baseline rule-based: usa risk_tier como "score" ordinal (LOW < MEDIUM < HIGH)
    tier_score = df_test_meta["risk_tier"].map(TIER_ORDINAL).values
    mask_high = (df_test_meta["risk_tier"] == "HIGH").values
    pos_rate_at_high = float(y_test.values[mask_high].mean()) if mask_high.any() else 0.0

    report = {
        "n_test": int(len(y_test)),
        "pos_rate_test": float(y_test.mean()),
        "trained_at": bundle["trained_at"],
        "git_sha": bundle["git_sha"],
        "features": bundle["features"],
        "model": {
            "auc": float(roc_auc_score(y_test, y_proba)),
            "log_loss": float(log_loss(y_test, y_proba)),
            "precision_at_10": _precision_at_k(y_test, y_proba, 0.10),
            "precision_at_20": _precision_at_k(y_test, y_proba, 0.20),
        },
        "baseline_rule": {
            "auc": float(roc_auc_score(y_test, tier_score)),
            "precision_at_tier_high": pos_rate_at_high,
            "pct_flagged_high": float(mask_high.mean()),
        },
    }
    report["delta"] = {
        "auc": report["model"]["auc"] - report["baseline_rule"]["auc"],
    }

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(json.dumps(report, indent=2, ensure_ascii=False))

    log.info(
        "Modelo avaliado",
        extra={
            "stage": "evaluate",
            "model_auc": round(report["model"]["auc"], 4),
            "baseline_auc": round(report["baseline_rule"]["auc"], 4),
            "delta_auc": round(report["delta"]["auc"], 4),
            "model_precision_at_20": round(report["model"]["precision_at_20"], 4),
            "baseline_precision_at_high": round(report["baseline_rule"]["precision_at_tier_high"], 4),
            "log_loss": round(report["model"]["log_loss"], 4),
            "n_test": report["n_test"],
        },
    )
    log.info("Relatório persistido", extra={"stage": "evaluate", "path": str(out_path)})
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mart", default=MART_PATH_DEFAULT)
    parser.add_argument("--model-out", default=MODEL_PATH_DEFAULT)
    parser.add_argument("--metrics-out", default=METRICS_PATH_DEFAULT)
    args = parser.parse_args()

    log.info("Iniciando training pipeline", extra={"stage": "start", "mart": args.mart})

    X_train, X_test, y_train, y_test, df_test_meta = prepare_dataset(args.mart)
    log.info(
        "Dataset preparado",
        extra={
            "stage": "prepare",
            "n_train": len(X_train),
            "n_test": len(X_test),
            "n_features": len(X_train.columns),
            "y_train_pos_rate": round(float(y_train.mean()), 4),
            "y_test_pos_rate": round(float(y_test.mean()), 4),
        },
    )

    bundle = train_model(X_train, y_train, args.model_out)
    log.info(
        "Modelo treinado e persistido",
        extra={
            "stage": "train",
            "model_path": args.model_out,
            "scale_pos_weight": round(bundle["scale_pos_weight"], 2),
            "git_sha": bundle["git_sha"],
        },
    )

    evaluate_and_benchmark(bundle, X_test, y_test, df_test_meta, args.metrics_out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
