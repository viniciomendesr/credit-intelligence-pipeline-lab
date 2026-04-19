#!/usr/bin/env bash
# Aquece o endpoint /explain-decision 60s antes da entrevista.
# Dispara os 3 applicant_ids pré-validados pra popular o cache por chave.
set -euo pipefail

URL="${1:-https://credit-api-wdrbcpzvha-uc.a.run.app}"

# Ids pré-validados: um por tier. Validar manualmente após rodar o eval
# (scripts/eval_explainer.py) e escolher ids cuja narrativa você já revisou.
ID_APROVADO="${ID_APROVADO:-1}"      # LOW  tier
ID_LIMITE="${ID_LIMITE:-23}"         # MEDIUM tier
ID_NEGADO="${ID_NEGADO:-171}"        # HIGH  tier

echo "▶ Warm-up do endpoint explicável: $URL"
echo ""

echo "1/4 · GET /health"
curl -s "$URL/health" | jq .
echo ""

for pair in "APROVADO:$ID_APROVADO" "LIMITE:$ID_LIMITE" "NEGADO:$ID_NEGADO"; do
  label="${pair%%:*}"
  id="${pair##*:}"
  echo "▶ Pré-aquecendo /explain-decision/$id ($label)"
  curl -s "$URL/explain-decision/$id" \
    | jq '{applicant_id, decision, risk_tier, narrative, cached}'
  echo ""
done

LATEST_EVAL=$(ls -t reports/eval_explainer_*.json 2>/dev/null | head -1 || true)
if command -v open >/dev/null 2>&1; then
  open "$URL/docs"
  open "https://github.com/viniciomendesr/credit-intelligence-pipeline/actions" || true
  if [ -n "${LATEST_EVAL:-}" ] && command -v code >/dev/null 2>&1; then
    code "$LATEST_EVAL"
  fi
fi

echo "✅ Cache por chave populado. Chamadas repetidas voltarão com cached:true em <100ms."
echo "   Siga o DEMO_BONUS.md."
