# Credit Intelligence Pipeline

Pipeline de dados financeiros de ponta a ponta — do dado bruto à decisão de
crédito explicável em produção. Simula o dia a dia de engenharia de
dados + engenharia de IA em um **motor de crédito B2B** (empresa genérica
que entrega camada de decisão de crédito para SaaS verticais — imobiliárias,
edtechs, healthtechs — conforme a regulação brasileira).

---

## O que este repositório é

Este repo tem **duas identidades simultâneas**, e ambas são intencionais:

1. **Implementação de referência** (gabarito) — código funcional em produção,
   com CI/CD, observabilidade, testes e custos controlados. Serve como demo
   técnica e base de comparação.

2. **Projeto pedagógico pessoal** — material de estudo para uma pessoa
   aprendendo engenharia de dados + engenharia de IA aplicada a crédito, do
   zero até deploy. O currículo é desenhado para acumular aprendizados
   concretos a cada fase.

Se você caiu aqui buscando **código ML/engineering** → começa em `src/`
e `api/`. Se veio **pra aprender** → siga a seção [Como usar este repo
como material de estudo](#como-usar-este-repo-como-material-de-estudo).

---

## Abordagem pedagógica

O projeto é estruturado em **5 fases + 2 bônus**, cada uma entregando algo
concreto que funciona antes de aprofundar detalhes. A inspiração é direta:

- **[fast.ai](https://course.fast.ai/)** — ensino top-down ("primeiro mostra
  o sistema funcionando, depois desdobra como funciona"). Learn-by-doing
  como filosofia central, não como ornamento.
- **[Kaggle](https://www.kaggle.com/competitions/GiveMeSomeCredit)** — cada
  fase parte de um problema concreto com dado real e métrica objetiva. O
  aluno mede o que fez, não apenas "sente" que fez.
- **Two-pass learning** — primeira passagem com código de referência pronto
  (este repo), segunda passagem reimplementando manualmente a partir dos
  guias. A teoria vem do tropeço, não antes dele.

Detalhes estratégicos da abordagem e reflexões pós-implementação ficam em
[`decisions.md`](decisions.md).

---

## Domínio simulado

Motor de crédito B2B operando no Brasil: recebe solicitações de crédito via
API interna de SaaS parceiros, aplica um pipeline de risco, e retorna:

- **Decisão** (APROVADO / APROVADO_COM_LIMITE / NEGADO)
- **Probabilidade calibrada de inadimplência** (ML)
- **Explicação em PT-BR** do porquê da decisão, com guardrails contra
  alucinação — cumprindo a **Resolução 4.935/Bacen** e o CDC (tomador tem
  direito de saber por que foi negado).

Pra quem está aprendendo, esse contexto força exercitar:

- Dados regulatórios e suas restrições (redistribuição, PII, auditoria)
- Trade-off FN vs FP em crédito (custo assimétrico)
- Explicabilidade como requisito legal, não só ético
- Custo de inferência em produção (latência, tokens, egress)

---

## Arquitetura (alto nível)

```
                    ┌─────────────────────────────────────────┐
                    │  Pipeline (batch / Prefect)             │
                    │                                         │
  CSV (Kaggle)      │  ingestão → validação → SQL (DuckDB) → │
  API bureau mock   │  mart Parquet → monitoring JSONL        │
                    └───────────┬─────────────────────────────┘
                                │
                                ▼
                         ┌──────────────┐
                         │  GCS bucket  │  (mart + modelo versionados)
                         └──────┬───────┘
                                │
                    ┌───────────▼───────────────┐
                    │  API (FastAPI, Cloud Run) │
                    │  ─────────────────────    │
                    │  GET /health              │
                    │  GET /risk-summary        │
                    │  GET /explain-decision/   │
                    │      rule/{applicant_id}  │  ← v1: narra regra SQL
                    │  GET /explain-decision/   │
                    │      ml/{applicant_id}    │  ← v2: narra modelo ML
                    └───────────┬───────────────┘
                                │
                     ┌──────────▼──────────┐
                     │  Anthropic Claude   │  (via Secret Manager)
                     │  Haiku 4.5          │
                     └─────────────────────┘
```

Fluxo completo + reflexões em [`decisions.md`](decisions.md).

---

## Quickstart

Pré-requisitos: Python 3.11+, `gcloud` CLI (apenas para deploy), acesso ao
[dataset Kaggle](#dataset) (download manual).

```bash
# 1. Clone e instale
git clone https://github.com/viniciomendesr/credit-intelligence-pipeline-lab
cd credit-intelligence-pipeline-lab
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Baixe o dataset Kaggle manualmente (ver data/README.md)
#    e coloque cs-training.csv + cs-test.csv em data/raw/

# 3. Rode o pipeline (gera staging + mart)
python pipeline/flow.py

# 4. Treine o modelo
python -m src.train

# 5. Rode a API local
uvicorn api.main:app --reload

# 6. Abra http://localhost:8000/docs
```

Endpoints disponíveis: `/health`, `/risk-summary`,
`/explain-decision/rule/{id}` (v1), `/explain-decision/ml/{id}` (v2).

Para o endpoint LLM (`/explain-decision/*`), defina `ANTHROPIC_API_KEY`:

```bash
 export ANTHROPIC_API_KEY="sk-ant-..."   # prefixo com espaço evita histórico
```

---

## Estrutura das fases

| Fase | O que você constrói | Stack novo |
|---|---|---|
| **1. Python puro** | Ingestão + validação de dados de crédito, scaffolding de projeto | pandas, Faker, Parquet |
| **2. SQL + modelagem** | Staging + mart com DuckDB, dedupe via QUALIFY, feature engineering | DuckDB, SQL, pytest |
| **3. Orquestração + API** | Flow Prefect, API FastAPI local, containerização | Prefect, FastAPI, Docker |
| **4. Observabilidade + Deploy** | Logging estruturado, drift detection, Cloud Run, CI/CD | GCP, GitHub Actions, Secret Manager |
| **Bônus Fase 4 (v1)** | LLM narra a regra SQL com guardrails, eval programático como gate de CI | Anthropic API, prompt engineering, SHAP-free explainer |
| **5. Modelagem ML** | Treinar XGBoost calibrado, benchmarking contra baseline rule-based | scikit-learn, XGBoost, SHAP nativo |
| **Bônus Fase 5 (v2)** | LLM narra o modelo ML via SHAP values, eval comparativo v1/v2 | SHAP (xgboost built-in), threshold calibration |

Cada fase tem runbooks de demonstração em `demo.md`, `demo-bonus-fase4.md`
e `demo-bonus-fase5.md`.

---

## Dataset

Este projeto usa o dataset público **[Give Me Some Credit](https://www.kaggle.com/competitions/GiveMeSomeCredit)**
(Kaggle competition, 2011). É um dataset de risco de crédito com ~150k
linhas, 11 features por tomador, e o label `defaulted` (inadimplência em
90+ dias nos 2 anos seguintes).

**Por que esse dataset?**
- Tamanho amigável (roda local sem cluster)
- Label verdadeiro presente (permite ML supervisionado real)
- Desbalanceamento natural (~6.8% de positivos), força lidar com classe
  rara
- Features interpretáveis (renda, dívida, atrasos) — úteis pra
  explicabilidade
- 15+ anos de análise pública (Kaggle kernels, notebooks) como referência
  externa

**Download e instruções completas em [`data/README.md`](data/README.md).**
Arquivos `cs-training.csv`, `cs-test.csv` e derivados ficam fora do git
por respeito aos termos de uso do Kaggle.

---

## Stack

Python 3.11 · pandas · DuckDB · FastAPI · Prefect · Docker · GCP
(Cloud Run + GCS + Secret Manager + Artifact Registry) · GitHub
Actions · pytest · Anthropic Claude API · scikit-learn · XGBoost.

---

## Como usar este repo como material de estudo

Três perfis de uso. Escolha o que bate com o seu momento.

### 👨‍💻 Perfil 1 — Eu mesmo (refazendo na mão, Pass 2)

Objetivo: reimplementar tudo sem olhar no gabarito.

1. Clone em **outra pasta**, deleta `src/`, `api/`, `pipeline/`, `scripts/`,
   `tests/`.
2. Mantém `data/` (precisa do dataset), `requirements.txt`, e os guias.
3. Abre o guia privado em `context/projeto-pedagogico/fase-1.html` (se existir
   localmente) ou segue pelos desafios descritos em [`decisions.md`](decisions.md).
4. Para cada desafio: tente por 20-30 min, só então abra o gabarito neste
   repo.
5. Anote onde travou em `exercicios.md` pessoal — esses travamentos são
   ouro pra estudos futuros.

### 👀 Perfil 2 — Alguém aprendendo pelo repo

Objetivo: seguir os runbooks + ler o código pra entender padrões.

1. Clone este repo
2. Leia [`decisions.md`](decisions.md) — entende o porquê das escolhas
3. Leia [`demo.md`](demo.md) — vê o sistema funcionando
4. Navega por `src/` pra ver cada módulo
5. Se quiser aprofundar em IA aplicada → [`demo-bonus-fase4.md`](demo-bonus-fase4.md)
   e [`demo-bonus-fase5.md`](demo-bonus-fase5.md)

### 🛠️ Perfil 3 — Engenheiro avaliando o código

Objetivo: julgar se este projeto mostra competência relevante.

- API em produção: https://credit-api-10681834413.us-central1.run.app/docs
- CI/CD verde em `.github/workflows/pipeline.yml`
- Testes unitários em `tests/` (23 passando)
- Eval programático em `scripts/eval_explainer_{rule,ml}.py` (gate de CI)
- Arquitetura em [`decisions.md`](decisions.md)

---

## Referências de metodologia

Projeto foi desenhado consultando:

- **[Practical Deep Learning for Coders (fast.ai)](https://course.fast.ai/)**
  — ensino top-down, "get your hands dirty first", progressive fading.
- **[Kaggle Give Me Some Credit](https://www.kaggle.com/competitions/GiveMeSomeCredit)**
  — estrutura de competition com dataset público + métrica objetiva.
- **Worked example effect** — literatura de ciência cognitiva sobre o
  valor de exemplos resolvidos antes de problemas puros, especialmente
  para novatos num domínio.

Reflexões pós-implementação sobre o que funciona e o que precisa ajustar
ficam em `context/projeto-pedagogico/` (material privado).

---

## Status

- Fases 1–5 + Bônus Fase 4 + Bônus Fase 5: **implementados e em produção**
- CI/CD: **verde** (test + deploy automáticos em push para `main`)
- Modelo ML: AUC 0.857 (XGBoost calibrado) vs 0.764 (baseline rule-based)
- Custo operacional: <R$1/mês em uso pessoal (Cloud Run scale-to-zero,
  GCS Standard com ~5 MB, Anthropic Haiku em tier free + créditos)

Dívidas conhecidas registradas em `context/projeto-pedagogico/melhorias-estruturais.md`
(material privado). Entre os principais itens abertos: fairness audit,
feature engineering manual, custo assimétrico FN vs FP, Dockerfile de
training.

---

## Licença e uso

Código sob **MIT License**. Dataset Kaggle segue os
[termos da competição original](https://www.kaggle.com/competitions/GiveMeSomeCredit/rules)
— arquivos `cs-*.csv` não são redistribuídos neste repo; download manual
obrigatório via conta Kaggle.

Não há PII no dataset. Features são anonimizadas e o label é binário.

---

## Contato

Este é um projeto pessoal de estudo. Sugestões, críticas e pull requests
são bem-vindos — mas a prioridade é o valor didático para quem está
aprendendo, não robustez de produção multi-tenant.
