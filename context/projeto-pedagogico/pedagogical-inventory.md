# Inventário pedagógico — Credit Intelligence Pipeline

Catálogo do que o projeto **exercita concretamente** por domínio, pra
suportar futura revisão do currículo. Cada dimensão tem itens marcados
por nível (🔵 fundamental / 🟡 intermediário / 🟢 avançado) e apontadores
pra onde no código o conceito aparece.

Gerado em 2026-04-19 após conclusão de Fases 1-5 + Bônus F4 + Bônus F5.

---

## Dimensões cobertas

### 1. Ferramental / CLI
- 🔵 `pip` + venv, `git` (commit/log/diff/push), `curl + jq`
- 🟡 `gcloud` (run, storage, iam, secrets, artifacts), `docker buildx --platform`, `gh` CLI
- 🟡 `git rebase --autosquash`, `git reflog`, `brew` pra libs de sistema
- 🟢 Shell history hygiene (`HIST_IGNORE_SPACE`), `git push --force-with-lease`

### 2. Python idiomatic
- 🔵 Type hints, `pathlib`, f-strings, context managers, list/dict comprehensions
- 🟡 Decorators (`@app.get`, `@task`, `@flow`), lazy init/singleton com module globals, `__future__` annotations, argparse
- 🟡 `subprocess.run(sys.executable, ...)` venv-safe, `joblib.dump`/`load`
- 🟡 Hierarquia de exceções (`ValueError`/`KeyError` → HTTPException)

### 3. Data engineering
- 🔵 Arquitetura em camadas (raw → staging → mart), schema contract via testes
- 🟡 Columnar (Parquet) vs row (CSV), append-only JSONL, idempotência
- 🟡 Immutable image + external data, versionamento por git SHA, data leakage

### 4. SQL / modelagem
- 🔵 SELECT/WHERE/CASE WHEN em DuckDB
- 🟡 Derivar features em SQL, quoting em DuckDB
- 🟢 Window functions (`QUALIFY ROW_NUMBER() OVER(...)`) pra dedupe

### 5. Machine Learning
- 🔵 Classificação binária supervisionada, train/test split
- 🟡 Estratificação, class imbalance (`scale_pos_weight`), serialização de modelo, baseline comparison
- 🟢 Gradient boosting (XGBoost), calibração isotonic, SHAP local vs feature importance global, data leakage patterns

### 6. Estatística / matemática
- 🔵 Média, mediana, percentil
- 🟡 AUC (ROC), precision@k, desvio relativo vs absoluto
- 🟢 Log-loss (cross-entropy), SHAP values (fundamento matemático), probabilidade calibrada vs raw score

### 7. APIs / backend
- 🔵 REST + HTTP methods + status codes
- 🟡 FastAPI auto-OpenAPI, Swagger UI/ReDoc, startup init, cache por chave com TTL
- 🟡 Fallback gracioso (503) em dependência ausente

### 8. Cloud / infra
- 🟡 Cloud Run serverless, Artifact Registry, GCS (classes, same-region egress), ADC
- 🟢 Secret Manager com versionamento, IAM least privilege (binding por recurso), rollback via update-traffic
- 🟢 Cost-aware architecture (budget R$5 orientando decisões)

### 9. Observabilidade
- 🟡 Structured logging JSON, Cloud Logging nativo, trace correlation via run_id, cache observable
- 🟢 Drift detection entre runs, token accounting + custo USD por chamada

### 10. AI / LLM engineering
- 🟡 Prompt engineering com restrições, model tiers (Haiku vs Sonnet), cache semântico
- 🟢 Separation: grounded context → LLM narrates only (architecture pattern)
- 🟢 Eval programático em lote (3 checks: grounded/aligned/forbidden) como CI gate
- 🟢 Guardrails contra alucinação numérica (iteração de 4 bugs no check)
- 🟢 LLM-como-narrador vs LLM-como-decisor

### 11. Security / compliance
- 🟢 IAM least privilege, secret rotation strategy, API key hygiene
- 🟢 Audit trail via Cloud Audit Logs
- 🟢 Compliance regulatório (Res. 4.935/Bacen, CDC), fairness concerns (anotados como T.9)

### 12. Software engineering
- 🔵 Unit tests (pytest + fixtures), reproducibility via random_state, gitignore strategy
- 🟡 Dependency pinning, configuration via env vars com fallback, separação de módulos
- 🟢 Interface segregation (mesmo shape, backings diferentes — v1/v2), semantic versioning em major bumps

### 13. DevOps / CI/CD
- 🔵 Jobs, steps, secrets, dependency gating (`needs:`)
- 🟡 `paths-ignore`, `concurrency cancel-in-progress`, pip cache, timeout-minutes
- 🟢 `permissions: contents: read` (least privilege), preserve evolution vs rewrite history

### 14. Domain knowledge (crédito regulado BR)
- 🔵 Default 90+ dias, features de crédito (debt_ratio, utilization, delinquency)
- 🟡 Tiers de decisão, imbalance natural de dataset, regulamentação BR
- 🟢 Custo assimétrico FN vs FP (anotado como T.9 backlog), BaaS + SaaS vertical model

### 15. Pedagogy / meta-learning
- 🔵 Active recall (fill-in-blank), progressive disclosure (`<details>`), blank-page test
- 🟡 Reflexão estruturada (ADR-like decisions.md)
- 🟢 Projeto em duas fases (Construção → Redesenvolvimento), meta-review "o que NÃO é ensinado" (melhorias-estruturais.md), progressão v1 → v2 como gradiente explícito

---

## O arco da jornada do aluno

1. **Dados** (Fases 1-2) — ingestão múltipla, limpeza, SQL, Parquet
2. **Orquestração + serving** (Fase 3) — batch Prefect + API síncrona compartilhando dado
3. **Produção** (Fase 4) — cloud, observabilidade, CI/CD, rollback
4. **ML real** (Fase 5) — treinar modelo, comparar com baseline, versionar
5. **AI regulada** (Bônus F4 + F5) — LLM com guardrails, eval programático, reason-codes

---

## O que o projeto ensina bem × onde é superficial × gaps

**🟢 Profundo e bem exercitado:**
- LLM engineering (prompt, grounded, eval, guardrails, iteração empírica)
- CI/CD best practices (paths-ignore, concurrency, cache, permissions)
- IAM + least privilege + secret management em GCP
- Separation of concerns em AI (extrator determinístico vs narrador LLM)
- Observabilidade estruturada (JSON logs + cost tracking)

**🟡 Tocado mas superficial:**
- Estatística avançada (sem CV real, sem CI do AUC, sem hypothesis testing)
- SQL avançado (só QUALIFY — sem CTE recursivo, window funcs amplas)
- Async Python (FastAPI suporta, projeto usa sync)
- Streaming (ausente, só batch)

**🔴 Ausentes ou só como dívida registrada:**
- Hyperparameter tuning (Optuna/GridSearch)
- Cross-validation real pra confidence interval
- Fairness audit (T.9 #6)
- Feature engineering manual (T.9 #4)
- Custo assimétrico em ML (T.9 #5)
- Model drift detection (só data drift existe)
- Dockerfile de training
- OIDC / Workload Identity Federation
- SHA pinning de GitHub Actions

---

## Plays pedagógicos pra implementar depois

1. **Bloco "📚 Conceitos exercitados" no topo de cada fase do HTML** — 4-6 itens por fase apontando pro código onde aparecem. Torna o currículo implícito em explícito.
2. **Seção "O que esta fase NÃO ensina"** no final de cada fase, com link pros itens em `melhorias-estruturais.md`. Honestidade pedagógica > aparente completude.
3. **Trilhas de aprofundamento por dimensão** — pós-Redesenvolvimento, quem quer ir fundo em ML rigor pode rodar `Optuna + CV + fairness` sobre o mesmo projeto-base.
4. **Reorganização top-down tipo fast.ai** — ver `platform-review.md` (análise separada).
