# Credit Intelligence Pipeline

Pipeline de dados financeiros de ponta a ponta — do dado bruto à decisão de
crédito explicável em produção. Simula o dia a dia de engenharia de
dados + engenharia de IA aplicada a análise de risco de crédito.

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
concreto que funciona antes de aprofundar detalhes. O currículo combina
princípios de ciência cognitiva e referências consolidadas de ensino
técnico moderno:

- **Top-down teaching** ([fast.ai](https://course.fast.ai/)) — cada fase
  começa com o sistema rodando, não com teoria. Matemática e internals
  aparecem **depois** do aluno já ter confiança de que sabe fazer. Inverte
  o currículo tradicional ("teoria primeiro, prática depois") porque
  adultos aprendem melhor quando o contexto de aplicação precede a
  abstração.
- **Learn-by-doing sobre dataset real** ([Kaggle GiveMeSomeCredit](https://www.kaggle.com/competitions/GiveMeSomeCredit))
  — cada desafio parte de problema concreto com dado real e métrica
  objetiva. O aluno **mede** o que fez (AUC, precision@k, pass rate), não
  apenas sente. Métricas viram feedback, não ornamento.
- **Projeto em duas fases** — **Fase 1 (Construção)**: código de referência
  pronto neste repo, com tudo rodando em produção. **Fase 2
  (Redesenvolvimento)**: o aluno reimplementa tudo manualmente **em um repo
  separado** dele, consultando este como gabarito só quando travar. A teoria
  vem do **tropeço**, não antes dele. O gabarito existe pra consultar,
  não pra ler como livro.
- **Worked examples com progressive fading** — para novatos num domínio,
  problemas abertos sem scaffold geram sobrecarga cognitiva ([efeito
  documentado](https://en.wikipedia.org/wiki/Worked-example_effect) em
  educação técnica). Desafios iniciais trazem hints + esqueleto de solução
  na seção "Referência"; os últimos são problemas puros. A ajuda **decresce
  conforme a expertise cresce**.
- **Active recall + blank-page test** — blocos de fill-in-blank ao fim de
  cada desafio forçam reconstrução da memória (recall), não reconhecimento
  passivo. No fim de cada fase, um "teste da página em branco": explicar em
  voz alta sem consultar. Onde travar é onde vale estudar mais.
- **Progressive disclosure** — dicas, guia passo-a-passo e referência
  completa vivem em blocos `<details>` colapsados. O aluno abre só quando
  travar, não antes. Evita spoiler da solução antes da tentativa honesta.
- **Meta-review honesto** — cada fase tem **o que ensina** e **o que NÃO
  ensina** explicitado (ver `melhorias-estruturais.md` no material
  privado). Aparentar completude prejudica mais que admitir gap — e os gaps
  viram trilhas opcionais de aprofundamento.

Reflexões pós-implementação, trade-offs de plataforma e material privado
ficam em [`decisions.md`](decisions.md) e em
`context/projeto-pedagogico/` (não versionado).

---

## Domínio simulado

Sistema de análise de crédito operando no Brasil: recebe solicitações via
API, aplica um pipeline de risco, e retorna:

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

### Perfil 1 — Eu mesmo (fase de Redesenvolvimento)

Objetivo: reimplementar tudo do zero sem olhar no gabarito. A fase de
**Redesenvolvimento** acontece em um **repositório separado**, não
neste — este aqui é apenas a referência que você consulta quando
travar.

**Setup sugerido:**

```bash
# 1. Crie um novo repo fora deste projeto (pasta vazia + git init)
cd ~/programming
mkdir credit-lab-redev && cd credit-lab-redev
git init && git branch -M main

# 2. Estrutura mínima
mkdir -p src tests data/raw
touch src/__init__.py tests/__init__.py
echo "# Credit Lab — Redesenvolvimento" > README.md

# 3. Baixe o dataset Kaggle em data/raw/ (veja instruções em
#    ../credit-intelligence-pipeline-lab/data/README.md)
```

**Fluxo por desafio:**

1. Abra o guia em `context/projeto-pedagogico/fase-N.html` deste repo
   (arquivo estático — basta abrir no navegador, não precisa servidor).
2. Leia o desafio (**o que construir**, IO badges, critério de teste).
3. No seu repo de Redesenvolvimento, tente implementar por **20-30 min
   sem consultar o gabarito**.
4. Se travar por mais que isso, abra o arquivo correspondente em `src/`
   deste repo. Leia, feche, e **reimplemente sem copiar**.
5. Anote onde travou em um `notes.md` do seu repo — esses travamentos
   orgânicos vão virar material de estudo futuro (o `exercicios.md` que
   cresce conforme você faz).

**O que NÃO fazer:**

- Clonar este repo, apagar código, e preencher de novo — o `git` do
  gabarito contaminaria suas tentativas e você perderia o hábito de
  scaffolding do zero.
- Copiar-colar do gabarito direto pro seu repo — derrota o propósito.
- Abrir o gabarito antes de tentar o desafio — leia o guia primeiro,
  depois tente sozinho, só então consulte.

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
ficam em [`context/projeto-pedagogico/`](context/projeto-pedagogico/) —
**guia HTML + meta-revisões públicas**. Destaques:

- **`fase-1.html` até `fase-5.html`**: desafios passo a passo de cada fase
- **`bonus-fase4.html` e `bonus-fase5.html`**: endpoints de explicabilidade
- **`melhorias-estruturais.md`**: T.1-T.10 — o que o currículo NÃO ensina e por quê
- **`pedagogical-inventory.md`**: catálogo de 15 dimensões de conceitos exercitados
- **`platform-review.md`**: comparação da plataforma atual (HTML) vs fast.ai/MkDocs

---

## Status

- Fases 1–5 + Bônus Fase 4 + Bônus Fase 5: **implementados e em produção**
- CI/CD: **verde** (test + deploy via pull request aprovado em `main`)
- Modelo ML: AUC 0.857 (XGBoost calibrado) vs 0.764 (baseline rule-based)
- Custo operacional: <R$1/mês em uso pessoal (Cloud Run scale-to-zero,
  GCS Standard com ~5 MB, Anthropic Haiku em tier free + créditos)

Dívidas conhecidas registradas em [`context/projeto-pedagogico/melhorias-estruturais.md`](context/projeto-pedagogico/melhorias-estruturais.md).
Entre os principais itens abertos: fairness audit, feature engineering
manual, custo assimétrico FN vs FP, Dockerfile de training.

---

## Contribuindo — fluxo de desenvolvimento

Este repositório usa **branch protection** em `main` + **PR workflow
obrigatório**. Push direto em `main` está bloqueado (admin pode bypassar
em emergência, mas o aviso fica registrado).

Esse setup é uma tradução prática do **nível 2 de maturidade de CI/CD**
descrito em [`context/projeto-pedagogico/melhorias-estruturais.md::T.10`](context/projeto-pedagogico/melhorias-estruturais.md).
Treina o hábito de PR review que qualquer time de fintech real exige.

### Fluxo para qualquer mudança

```bash
# 1. Criar branch descritiva (ver convenção abaixo)
git checkout -b feat/nome-curto

# 2. Trabalhar normalmente
# ...editar, testar localmente com `pytest`, commitar...

# 3. Push do branch
git push -u origin feat/nome-curto

# 4. Abrir PR
gh pr create --title "feat: descrição" --body "contexto em 1-2 frases"

# 5. Esperar CI verde (job `test` é status check obrigatório)
gh pr checks

# 6. Merge (squash ou merge commit — projeto não tem preferência)
gh pr merge --squash --delete-branch
```

### Convenção de branches

Prefixo por tipo (consistente com mensagens de commit):

- `feat/` — nova funcionalidade
- `fix/` — correção de bug
- `docs/` — documentação (normalmente pula CI via `paths-ignore`)
- `refactor/` — mudança interna sem alterar comportamento
- `chore/` — manutenção, deps, CI config
- `test/` — adição ou ajuste de testes

### O que dispara CI

O workflow em `.github/workflows/pipeline.yml` usa `paths-ignore` para
**não disparar deploy** quando a mudança é só em docs/material pedagógico:

- `**/*.md` e `*.md`
- `context/**` (todo o guia pedagógico)
- `reports/**`, `models/**`
- `.gitignore`, `LICENSE`

PRs tocando só esses paths fazem merge sem rodar CI — mais rápido,
barato, e evita redeploys desnecessários.

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
