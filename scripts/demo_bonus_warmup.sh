#!/usr/bin/env bash
# Aquece o endpoint /explain-decision 60s antes da entrevista.
# Dispara os 3 applicant_ids pré-validados pra popular o cache por chave.
set -euo pipefail

URL="${1:-https://credit-api-wdrbcpzvha-uc.a.run.app}"

# Ids pré-validados (narrativa revisada após pass_rate_grounded=1.0 no eval).
# Escolha: 1 de cada tier com perfil claro e dados não-outlier.
ID_APROVADO="${ID_APROVADO:-37167}"  # LOW    — renda R$ 10.750, uso 10%
ID_LIMITE="${ID_LIMITE:-50821}"      # MEDIUM — renda R$ 7.195, uso 63%, debt 0.82
ID_NEGADO="${ID_NEGADO:-23380}"      # HIGH   — renda R$ 4.000, uso 100%

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
echo "   Siga o demo-bonus.md."
