# DEMO — Runbook de demonstração do pipeline (5 min)

Roteiro para demonstrar o sistema em produção sem o endpoint LLM. Use
para qualquer cenário em que você precisa provar em 5 minutos que o
sistema está vivo, auditável e reproduzível:

- Validação pessoal depois de um deploy — tudo ainda responde?
- Mostrar para um mentor, colaborador ou colega curioso.
- Revisão de portfólio quando for anexar o projeto em um perfil público.
- Entrevista técnica (um caso particular deste roteiro).

Se a demo evoluir para "como você usa LLM?", complementar com
`DEMO_BONUS.md`.

---

## Setup (60s antes de apresentar)

```bash
./scripts/demo_warmup.sh
# Opcionalmente: ./scripts/demo_warmup.sh https://outra-url.run.app
```

Abre 3 tabs: Swagger `/docs`, GitHub Actions, Cloud Run console.
Aguarde ~30s — a instância precisa estacionar pra evitar cold start na
primeira request do roteiro.

---

## Roteiro (5 min, 3 beats)

### Beat 1 — Está no ar (60s)

- Tab ativa: **Swagger**.
- Fala: "A API expõe dois endpoints públicos, deploy em Cloud Run. URL
  estável, sem autenticação pra facilitar a exibição."
- Clica `/risk-summary` → Try it out → Execute. Resposta aparece.
- Aponta no JSON:
  - `total_records: 144401` — dado real, não mock.
  - `default_rate_pct: 6.76` — bate com o benchmark do DuckDB da Fase 2.
  - `risk_tier_distribution_pct` — LOW/MEDIUM/HIGH.

### Beat 2 — Como o dado chegou aqui (2 min)

- Fala: "O mart é gerado por um pipeline Prefect: ingestão de CSV e API
  simulada de bureau, validação com regras de negócio, transformação em
  staging e mart com DuckDB e SQL, persistência em Parquet."
- Se perguntarem sobre arquitetura: "A API não gera o dado. O mart é
  materializado no pipeline, salvo em Parquet, subido num bucket GCS na
  mesma região do Cloud Run (egress same-region é grátis), e baixado no
  startup do container via ADC — imagem imutável, dado externo."
- Se perguntarem sobre schema: "`models/mart_credit_features.sql` —
  16 colunas incluindo `risk_tier` (derivado de `revolving_utilization`
  + atrasos) e `defaulted` (label original do dataset Kaggle)."

### Beat 3 — Como sei que não quebrou (2 min)

- Tab ativa: **GitHub Actions**.
- Aponta: último run verde, job `test` ~35s, job `deploy` ~2min.
- Fala: "Cada push pra `main` roda testes e faz deploy. Se teste falha,
  job de deploy é skipped — gate automático, nunca manual."
- Tab ativa: **Cloud Run → credit-api → Logs**.
- Aponta: log JSON estruturado com `timestamp`, `level`, `event`,
  `run_id`.
- Fala: "Logging é JSON nativo. Cada execução do pipeline tem um
  `run_id` uuid e todos os logs daquela run carregam essa tag — filtro
  simples no Cloud Logging pra trace de uma execução específica. Drift
  entre execuções é persistido em `metrics_history.jsonl`."

---

## Perguntas frequentes

**"Como escala?"**
Cloud Run autoscale, `min-instances=0`, `max-instances` configurável.
Escala a zero quando sem tráfego — custo idle é zero. Cold start é de
~2-3s na primeira request após inatividade; por isso o warm-up no
início do roteiro.

**"Como sabe que não quebrou em produção?"**
Três camadas. (1) CI: pytest no job `test` bloqueia deploy se falhar.
(2) Cloud Run Logs captura todo log JSON estruturado do container.
(3) `src/monitor.py` compara métricas entre execuções do pipeline e
grava em `metrics_history.jsonl` — detecta drift acima de 10 pontos
percentuais em `default_rate_pct`.

**"Como faz rollback?"**
Cada deploy é uma Revisão no Cloud Run, taggeada com o SHA do commit.
`gcloud run services update-traffic credit-api --to-revisions REV=100`
redireciona 100% do tráfego pra qualquer revisão anterior em segundos,
sem rebuild. Recuperabilidade é baked-in no CI — o workflow usa
`$GITHUB_SHA` como tag da imagem.
