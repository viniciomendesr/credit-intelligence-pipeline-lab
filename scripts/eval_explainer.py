#!/usr/bin/env python
"""Eval programático do decision_explainer em lote.

Amostra ``applicant_id``s estratificados por ``risk_tier`` (proporção real
da carteira) e aplica três checks binários à saída de
``explain_decision``:

  - grounded : todo número citado na ``narrative`` existe entre os
               ``value``/``median`` dos ``key_factors``
  - aligned  : se ``decision == NEGADO``, pelo menos um fator de risco
               está no top-3
  - forbidden: narrativa não cita CEP, raça, gênero, estado civil, religião

Gera ``reports/eval_explainer_<timestamp>.json`` com pass rates, latência
p95, custo em USD (Haiku 4.5) e lista completa de violações. Sai com
exit 1 se ``pass_rate_overall < threshold`` — pensado pra rodar como
step de CI.

Uso:
    python scripts/eval_explainer.py --n 21 --seed 42
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
from src.decision_explainer import explain_decision  # noqa: E402

# Haiku 4.5 pricing — atualizar se mudar na tabela
PRICE_IN_PER_MTOK = 1.00   # USD por milhão de tokens de input
PRICE_OUT_PER_MTOK = 5.00  # USD por milhão de tokens de output

FORBIDDEN = ["cep", "endereço", "endereco", "raça", "raca", "gênero", "genero",
             "estado civil", "religião", "religiao"]
NUM_RE = re.compile(r"\d+[.,]?\d*")


def stratified_sample(mart_path: str, n: int, seed: int) -> list[int]:
    df = pd.read_parquet(mart_path)
    proportions = {"LOW": 0.70, "MEDIUM": 0.16, "HIGH": 0.14}
    ids: list[int] = []
    for tier, p in proportions.items():
        k = max(1, round(n * p))
        pool = df[df["risk_tier"] == tier]
        if pool.empty:
            continue
        sample = pool.sample(n=min(k, len(pool)), random_state=seed)
        ids.extend(sample["applicant_id"].tolist())
    return ids[:n]


def _candidate_strings(value: float) -> set[str]:
    """Representações aceitáveis de um número que o LLM pode ter escrito."""
    out: set[str] = set()
    out.add(f"{value:.2f}")
    out.add(f"{value:.1f}")
    if float(value).is_integer():
        out.add(str(int(value)))
    return out


def check_grounded(narrative: str, key_factors: list[dict]) -> tuple[bool, str]:
    valid_values: list[float] = []
    for f in key_factors:
        valid_values.append(float(f["value"]))
        valid_values.append(float(f["median"]))
    for token in NUM_RE.findall(narrative):
        try:
            num = float(token.replace(",", "."))
        except ValueError:
            continue
        if not any(abs(num - v) < 0.05 or abs(num - v) / (abs(v) + 1e-9) < 0.02
                   for v in valid_values):
            return False, f"número '{token}' não aparece nos key_factors"
    return True, ""


def check_aligned(result: dict) -> tuple[bool, str]:
    if result["decision"] != "NEGADO":
        return True, ""
    has_risk_driver = any(
        f["direction"] == "alto_aumenta_risco" for f in result["key_factors"]
    )
    return (True, "") if has_risk_driver else (False, "NEGADO sem fator de risco no top-3")


def check_forbidden(narrative: str) -> tuple[bool, str]:
    low = narrative.lower()
    hit = next((w for w in FORBIDDEN if w in low), None)
    return (False, f"menciona '{hit}'") if hit else (True, "")


def run_eval(mart_path: str, n: int, seed: int) -> dict:
    ids = stratified_sample(mart_path, n, seed)
    latencies: list[float] = []
    violations: list[dict] = []
    cost_in = cost_out = 0
    pass_grounded = pass_aligned = pass_forbidden = pass_all = 0

    for applicant_id in ids:
        t0 = time.perf_counter()
        result = explain_decision(applicant_id, mart_path)
        latencies.append((time.perf_counter() - t0) * 1000)

        usage = result.get("_usage", {})
        cost_in += usage.get("input_tokens", 0)
        cost_out += usage.get("output_tokens", 0)

        ok_g, msg_g = check_grounded(result["narrative"], result["key_factors"])
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
                })

    total = len(ids)
    return {
        "n_samples": total,
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
    parser.add_argument("--n", type=int, default=21)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--threshold", type=float, default=0.95)
    args = parser.parse_args()

    report = run_eval(args.mart, args.n, args.seed)
    out_dir = Path("reports")
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f"eval_explainer_{datetime.now():%Y%m%d_%H%M%S}.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    summary = {k: v for k, v in report.items() if k != "violations"}
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"\nRelatório completo: {out_path}")
    if report["violations"]:
        print(f"Violações: {len(report['violations'])} (ver arquivo)")

    if report["pass_rate_overall"] < args.threshold:
        print(f"\n❌ FAIL: pass_rate_overall {report['pass_rate_overall']} < threshold {args.threshold}")
        return 1
    print(f"\n✅ PASS (threshold {args.threshold})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
