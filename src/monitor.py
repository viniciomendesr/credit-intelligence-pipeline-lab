import json
from datetime import datetime
from pathlib import Path

import pandas as pd


def collect_metrics(df: pd.DataFrame, run_id: str) -> dict:
    """Snapshot key quality metrics from the mart for one pipeline run."""
    return {
        "run_id": run_id,
        "timestamp": datetime.now().isoformat(),
        "total_records": len(df),
        "default_rate_pct": round(df['defaulted'].mean() * 100, 4),
        "risk_tier_dist": (
            df['risk_tier']
            .value_counts(normalize=True)
            .mul(100).round(2)
            .to_dict()
        ),
        "median_income": round(df['monthly_income'].median(), 2),
    }


def save_metrics(metrics: dict, path: str = 'data/monitoring/metrics_history.jsonl') -> None:
    """Append one metrics snapshot as a JSON line — never overwrites history."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'a') as f:
        f.write(json.dumps(metrics) + '\n')


def detect_drift(
    path: str = 'data/monitoring/metrics_history.jsonl',
    threshold: float = 10.0,
) -> dict:
    """Compare the two most recent runs and flag if default_rate_pct shifted.

    Returns drift_detected=False with a message when history has fewer than
    two entries — avoids crashing on the first run.
    """
    text = Path(path).read_text().strip()
    lines = [l for l in text.split('\n') if l]

    if len(lines) < 2:
        return {"drift_detected": False, "note": "histórico insuficiente"}

    prev = json.loads(lines[-2])
    curr = json.loads(lines[-1])
    delta = abs(curr['default_rate_pct'] - prev['default_rate_pct'])

    return {
        "drift_detected": delta > threshold,
        "delta_pct": round(delta, 4),
        "prev_run": prev['run_id'],
        "curr_run": curr['run_id'],
        "alert": f"Default rate mudou {delta:.4f}pp" if delta > threshold else None,
    }
