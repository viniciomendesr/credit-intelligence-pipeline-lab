#!/usr/bin/env bash
# Aquece endpoints v1 (rule) + v2 (ml) pros mesmos 3 applicant_ids
# pré-validados, populando caches por chave. O ponto alto da demo
# Bônus F5 é comparar as duas narrativas lado a lado.
set -euo pipefail

URL="${1:-https://credit-api-10681834413.us-central1.run.app}"

ID_APROVADO="${ID_APROVADO:-37167}"  # LOW / low-prob
ID_LIMITE="${ID_LIMITE:-50821}"      # MEDIUM / mid-prob
ID_NEGADO="${ID_NEGADO:-23380}"      # HIGH (rule) / mid-prob (ml)

echo "▶ Warm-up v1 (rule) + v2 (ml): $URL"
echo ""
echo "0/7 · GET /health"
curl -s "$URL/health" | jq .
echo ""

i=1
for pair in "APROVADO:$ID_APROVADO" "LIMITE:$ID_LIMITE" "NEGADO:$ID_NEGADO"; do
  label="${pair%%:*}"
  id="${pair##*:}"
  echo "$i/7 · v1 rule  ($label, id=$id)"
  curl -s "$URL/explain-decision/rule/$id" \
    | jq '{decision, risk_tier, narrative: (.narrative | .[0:100] + "…")}'
  echo ""
  i=$((i+1))
  echo "$i/7 · v2 ml    ($label, id=$id)"
  curl -s "$URL/explain-decision/ml/$id" \
    | jq '{decision, pred_default_prob, narrative: (.narrative | .[0:100] + "…")}'
  echo ""
  i=$((i+1))
done

LATEST_RULE=$(ls -t reports/eval_explainer_rule_*.json 2>/dev/null | head -1 || true)
LATEST_ML=$(ls -t reports/eval_explainer_ml_*.json 2>/dev/null | head -1 || true)
METRICS=reports/model_metrics.json

if command -v open >/dev/null 2>&1; then
  open "$URL/docs"
  open "https://github.com/viniciomendesr/credit-intelligence-pipeline/actions" || true
  if command -v code >/dev/null 2>&1; then
    [ -n "${LATEST_RULE:-}" ] && code "$LATEST_RULE"
    [ -n "${LATEST_ML:-}" ]   && code "$LATEST_ML"
    [ -f "$METRICS" ]         && code "$METRICS"
  fi
fi

echo "✅ Cache v1 + v2 populado. Siga o demo-bonus-fase5.md."
