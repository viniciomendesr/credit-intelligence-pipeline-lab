#!/usr/bin/env bash
# Aquece o Cloud Run 60s antes da entrevista.
# Endpoints sem LLM — demo da Fase 4 (sistema sem bônus).
set -euo pipefail

URL="${1:-https://credit-api-wdrbcpzvha-uc.a.run.app}"

echo "▶ Warm-up do Cloud Run: $URL"
echo ""

echo "1/2 · GET /health"
curl -s "$URL/health" | jq .
echo ""

echo "2/2 · GET /risk-summary (carrega o parquet na memória)"
curl -s "$URL/risk-summary" \
  | jq '{total_records, default_rate_pct, risk_tier_distribution_pct}'
echo ""

if command -v open >/dev/null 2>&1; then
  open "$URL/docs"
  open "https://github.com/viniciomendesr/credit-intelligence-pipeline/actions" || true
  open "https://console.cloud.google.com/run?project=credit-pipeline-demo" || true
elif command -v xdg-open >/dev/null 2>&1; then
  xdg-open "$URL/docs" || true
fi

echo "✅ Sistema aquecido. Aguarde 30s e inicie a demo (demo.md)."
