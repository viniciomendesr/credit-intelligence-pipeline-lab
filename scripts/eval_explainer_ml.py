#!/usr/bin/env python
"""Eval programático do decision_explainer_ml (Bônus Fase 5) em lote.

Espelha ``eval_explainer_rule.py`` com 3 adaptações:

1. **Amostragem estratificada por faixa de `pred_default_prob`** (baixo
   <0.3 / médio 0.3-0.6 / alto >=0.6) em vez de ``risk_tier``.
2. **Check ``aligned``**: se ``decision == NEGADO``, pelo menos um fator
   no top-3 deve ter ``shap_value > 0`` (empurrou prob pra cima).
3. **Pool de grounded values**: inclui ``pred_default_prob`` (e ×100),
   ``value`` e ``shap_value`` de cada feature, e números em labels.

Gera ``reports/eval_explainer_ml_<ts>.json``. Exit 1 se pass rate < 0.95.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.decision_explainer_ml import (  # noqa: E402
    _decision_from_prob,
    _get_bundle,
    _shap_values_for_row,
    explain_decision_ml,
)

# Preço Haiku 4.5 — atualizar se mudar
PRICE_IN_PER_MTOK = 1.00
PRICE_OUT_PER_MTOK = 5.00

FORBIDDEN = [
    "cep", "endereço", "endereco", "raça", "raca", "gênero", "genero",
    "estado civil", "religião", "religiao",
]
NUM_RE = re.compile(r"\d+[.,]?\d*")
_BR_THOUSANDS_RE = re.compile(r"(\d)\.(\d{3})(?!\d)")
_BR_DECIMAL_RE = re.compile(r"(\d),(\d)")


def _normalize_pt_br_numbers(text: str) -> str:
    prev = None
    while prev != text:
        prev = text
        text = _BR_THOUSANDS_RE.sub(r"\1\2", text)
    text = _BR_DECIMAL_RE.sub(r"\1.\2", text)
    return text


def _expand_valid_values(ctx: dict) -> list[float]:
    out: list[float] = []
    prob = float(ctx["pred_default_prob"])
    out.append(prob)
    out.append(prob * 100)
    for f in ctx["key_factors"]:
        v = float(f["value"])
        out.append(v)
        if 0 < abs(v) <= 1:
            out.append(v * 100)
        s = float(f["shap_value"])
        out.append(s)
        out.append(s * 100)
    return out


def check_grounded(narrative: str, ctx: dict) -> tuple[bool, str]:
    valid = _expand_valid_values(ctx)
    normalized = _normalize_pt_br_numbers(narrative)
    for token in NUM_RE.findall(normalized):
        try:
            num = float(token)
        except ValueError:
            continue
        if not any(
            abs(num - v) < 0.05 or abs(num - v) / (abs(v) + 1e-9) < 0.02
            for v in valid
        ):
            return False, f"número '{token}' não vem de key_factors/prob"
    return True, ""


def check_aligned(result: dict) -> tuple[bool, str]:
    if result["decision"] != "NEGADO":
        return True, ""
    has_risk_driver = any(
        f["shap_value"] > 0 for f in result["key_factors"]
    )
    return (True, "") if has_risk_driver else (False, "NEGADO sem SHAP positivo top-3")


def check_forbidden(narrative: str) -> tuple[bool, str]:
    low = narrative.lower()
    hit = next((w for w in FORBIDDEN if w in low), None)
    return (False, f"menciona '{hit}'") if hit else (True, "")


def stratified_by_pred(mart_path: str, model_path: str, n: int, seed: int) -> list[int]:
    """Amostra n ids estratificados por faixa de pred_default_prob.

    Calcula prob pra todos via bulk predict (muito mais rápido que 1 a 1).
    """
    mart = pd.read_parquet(mart_path)
    bundle = _get_bundle(model_path)
    X = mart[bundle["features"]]
    probs = bundle["model"].predict_proba(X)[:, 1]
    mart = mart.assign(_prob=probs)

    def bucket(p: float) -> str:
        if p < 0.30:
            return "low"
        if p < 0.60:
            return "mid"
        return "high"

    mart["_bucket"] = mart["_prob"].apply(bucket)
    proportions = {"low": 0.60, "mid": 0.25, "high": 0.15}
    ids: list[int] = []
    for b, pct in proportions.items():
        k = max(1, round(n * pct))
        pool = mart[mart["_bucket"] == b]
        if pool.empty:
            continue
        sample = pool.sample(n=min(k, len(pool)), random_state=seed)
        ids.extend(sample["applicant_id"].tolist())
    return ids[:n]


def run_eval(mart_path: str, model_path: str, n: int, seed: int) -> dict:
    ids = stratified_by_pred(mart_path, model_path, n, seed)
    mart = pd.read_parquet(mart_path)

    latencies: list[float] = []
    violations: list[dict] = []
    cost_in = cost_out = 0
    pass_grounded = pass_aligned = pass_forbidden = pass_all = 0

    for applicant_id in ids:
        t0 = time.perf_counter()
        result = explain_decision_ml(applicant_id, mart, model_path)
        latencies.append((time.perf_counter() - t0) * 1000)

        usage = result.get("_usage", {})
        cost_in += usage.get("input_tokens", 0)
        cost_out += usage.get("output_tokens", 0)

        ok_g, msg_g = check_grounded(result["narrative"], result)
        ok_a, msg_a = check_aligned(result)
        ok_f, msg_f = check_forbidden(result["narrative"])

        pass_grounded += ok_g
        pass_aligned += ok_a
        pass_forbidden += ok_f
        pass_all += (ok_g and ok_a and ok_f)

        for ok, check, msg in [
            (ok_g, "grounded", msg_g),
            (ok_a, "aligned", msg_a),
            (ok_f, "forbidden", msg_f),
        ]:
            if not ok:
                violations.append({
                    "applicant_id": int(applicant_id),
                    "check": check,
                    "detail": msg,
                    "narrative": result["narrative"],
                    "pred_default_prob": result["pred_default_prob"],
                    "key_factors": result["key_factors"],
                })

    total = max(len(ids), 1)
    return {
        "n_samples": len(ids),
        "seed": seed,
        "pass_rate_grounded": round(pass_grounded / total, 4),
        "pass_rate_aligned": round(pass_aligned / total, 4),
        "pass_rate_forbidden": round(pass_forbidden / total, 4),
        "pass_rate_overall": round(pass_all / total, 4),
        "latency_p95_ms": round(float(np.percentile(latencies, 95)), 2),
        "latency_mean_ms": round(float(np.mean(latencies)), 2),
        "cost_usd_total": round(
            cost_in * PRICE_IN_PER_MTOK / 1e6 + cost_out * PRICE_OUT_PER_MTOK / 1e6,
            6,
        ),
        "tokens_input_total": int(cost_in),
        "tokens_output_total": int(cost_out),
        "violations": violations,
        "generated_at": datetime.now().isoformat(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mart", default="data/marts/mart_credit_features.parquet")
    parser.add_argument("--model", default="models/model.pkl")
    parser.add_argument("--n", type=int, default=21)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--threshold", type=float, default=0.95)
    args = parser.parse_args()

    report = run_eval(args.mart, args.model, args.n, args.seed)
    out_dir = Path("reports")
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f"eval_explainer_ml_{datetime.now():%Y%m%d_%H%M%S}.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    summary = {k: v for k, v in report.items() if k != "violations"}
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"\nRelatório completo: {out_path}")
    if report["violations"]:
        print(f"Violações: {len(report['violations'])} (ver arquivo)")

    if report["pass_rate_overall"] < args.threshold:
        print(f"\n❌ FAIL: pass_rate_overall {report['pass_rate_overall']} < {args.threshold}")
        return 1
    print(f"\n✅ PASS (threshold {args.threshold})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
