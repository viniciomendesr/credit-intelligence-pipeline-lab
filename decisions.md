# decisões de arquitetura e processo

Registro das decisões técnicas feitas ao longo do projeto. Serve de âncora
pra fase de Redesenvolvimento (implementação manual a partir do zero, em repo separado) e de checkpoint
quando alguma escolha precisa ser reavaliada.

Formato: cada entrada tem data, contexto, decisão, alternativas consideradas,
e — quando aplicável — resultado observado depois. Ordenado por tema, não
cronologicamente — dentro de cada tema, do mais antigo pro mais recente.

---

## arquitetura de serving

### 2026-04-18 — mart baixado do GCS no startup, não copiado na imagem

**Contexto.** O Dockerfile copiava `data/marts/` pra dentro da imagem. Funcionava
local porque o parquet estava gerado no disco, mas o CI quebrava porque
`cs-training.csv` (fonte) é gitignored (termos Kaggle) e o mart derivado
também.

**Decisão.** Remover `COPY data/marts/`. API baixa o parquet de
`gs://credit-pipeline-demo-marts` no startup via ADC, com fallback pro disco
local quando envs `MART_BUCKET`/`MART_OBJECT` não estão setadas (preserva DX
de dev).

**Alternativas consideradas** (em ordem descartada):

- (A) GCS com CSV fonte + CI gera parquet — acopla CI à execução do pipeline.
- (B) Parquet sintético no CI — prod rodando com fake data, anti-pattern.
- (D) Commitar o parquet — zona cinzenta dos termos Kaggle + binary bloat no git.

**Resultado.** CI desbloqueado, imagem ~500KB menor, custo extra GCS
~R$0,001/mês. Egress GCS→Cloud Run same-region é gratuito. Documentado em
`melhorias-estruturais.md::T.6`.

---

### 2026-04-19 — ANTHROPIC_API_KEY via Secret Manager, não env var plana

**Contexto.** Endpoint `/explain-decision` precisa da key da Anthropic no
runtime. Dois caminhos: `--set-env-vars` no `gcloud run deploy` ou Secret
Manager com `--update-secrets`.

**Decisão.** Secret Manager. Key fica em `projects/credit-pipeline-demo/secrets/anthropic-api-key`,
SA `credit-pipeline-sa` tem `roles/secretmanager.secretAccessor` **apenas
nesse recurso** (menor privilégio).

**Por quê.** Env var em texto plano aparece em `gcloud run services describe`
(qualquer um com `roles/run.viewer` lê). Secret Manager força trilha de
auditoria via Cloud Audit Logs e permite rotação sem rebuild (só nova
versão + próximo cold start).

**Custo.** 6 secrets grátis + 10k accesses/mês grátis. Não mexe no budget R$5.

---

## arquitetura do explicador LLM

### 2026-04-18 — separação determinística (extrator) + LLM (narrador)

**Contexto.** Endpoint que explica decisão de crédito em PT-BR. Abordagem
ingênua: jogar o mart inteiro no prompt e pedir "explique". Abordagem
correta: extrair os fatores primeiro, narrar depois.

**Decisão.** Duas funções em `src/decision_explainer_rule.py`:

1. `extract_context()` — determinística, escolhe top-3 fatores com maior
   desvio vs. mediana da carteira. Sem LLM.
2. `explain_decision()` — chama `extract_context`, monta prompt com restrições
   explícitas ("cite apenas os valores acima, não invente número, não mencione
   atributo sensível"), chama Haiku 4.5, retorna dict.

**Por quê.** Se o LLM decide sozinho quais fatores mencionar, ele seleciona
o que parece plausível — pode omitir feature crítica ou inventar uma que não
existe. Com extração determinística antes, o compliance controla **o que**
pode ser dito; o LLM só controla o **tom**. Essa separação é o que faz o
endpoint passar revisão regulatória.

**Resultado.** Primeira chamada em prod narrou APROVADO para tomador com
renda R$ 16.000 citando os 3 valores exatos de `key_factors`. Narrativa
legível pelo tomador, auditável pelo time de risco.

---

### 2026-04-18 — cache por `applicant_id`, não global

**Contexto.** Cada chamada ao LLM custa ~US$0.001 e ~2s de latência. Cache é
necessário. Escolher entre: cache global (primeiro insight) ou por chave.

**Decisão.** Cache por chave. `dict[int, dict]` em escala de módulo, TTL 30min.
Cache global trocaria explicações entre tomadores (tomador 7 recebendo
narrativa do tomador 3) — corretude depende do input.

**Trade-off conhecido.** No Cloud Run com múltiplas réplicas, cada instância
tem seu cache local. Aceitável pra este projeto (explicação é idempotente
pro mesmo mart + modelo + prompt). Em produção de escala, usar Memorystore/
Redis. Registrado como variação em `bonus-fase4.html::B.2`.

---

## observabilidade e eval

### 2026-04-19 — eval programático em lote como gate de CI (B.3)

**Contexto.** LLM em produção falha silenciosamente — mudança de prompt ou
troca de modelo pode introduzir alucinação em 5% dos casos sem ninguém notar.

**Decisão.** `scripts/eval_explainer_rule.py` que amostra 21 `applicant_id`s
estratificados por tier (LOW/MEDIUM/HIGH em proporção da carteira), roda o
explainer em cada, e aplica 3 checks binários:

1. **grounded** — todo número na narrativa existe nos `key_factors`
2. **aligned** — se `decision == NEGADO`, pelo menos um fator de risco está
   no top-3
3. **forbidden** — narrativa não menciona CEP/raça/gênero/religião/estado civil

Gera `reports/eval_explainer_rule_<timestamp>.json` com pass rates, latência p95,
custo USD, tokens consumidos, violações. Exit 1 se `pass_rate_overall < 0.95`
— pensado pra virar step de CI.

**Custo.** ~US$0,02 por execução de 21 amostras (Haiku 4.5). 0,4% do crédito
de US$5 da Anthropic.

---

### 2026-04-19 — iterações no check de `grounded-ness` (4 bugs, 4 fixes)

**Contexto.** Primeira execução do eval devolveu `pass_rate_grounded: 0.24`
— indicando 76% de "alucinação". Investigação ao longo de 5 runs
(~US$0,10 total) revelou que o LLM estava fiel; o check tinha **falsos
positivos em 4 categorias**. Progressão: 0.24 → 0.62 → 0.67 → 0.90 → 1.00.

**Bug 1: formato BR não reconhecido.** LLM escreve `R$ 5.400,00`; regex pegava
`5.400` e convertia pra float `5.4` (formato americano). Fix: normalizar BR
antes do regex — ponto como milhar vira nada, vírgula como decimal vira
ponto. **Resultado:** 0.24 → 0.62.

**Bug 2: números em labels não considerados válidos.** LLM cita "atrasos
médios de 60-89 dias" — `60` e `89` vêm do label da feature, não do
`value`/`median`. Fix: incluir no pool de valid_values os números extraídos
dos labels via regex.

**Bug 3: percentual como representação de decimal < 1.** LLM escreve "utiliza
apenas 2% do limite" quando o value é `0.02`. Transformação matematicamente
correta e user-friendly, mas `2` não aparece literalmente nos key_factors.
Fix: aceitar `value * 100` como representação válida quando `0 < |value| < 1`.
**Resultado:** 0.67 → 0.90.

**Bug 4: off-by-one no bound + `deviation_ratio` ignorado.** Duas falhas
remanescentes num único fix:

- `value = 1.0` (uso total do limite rotativo) caía fora de `0 < |v| < 1` —
  strict less than excluía o próprio 1.0. LLM narrava "100%", check flagueava.
  Fix: mudar pra `<= 1`.
- `deviation_ratio = 0.85` é metadado não passado no prompt, mas o LLM
  computa a mesma coisa (`(10000 - 5400) / 5400 ≈ 85%`) e escreve "85% acima
  da mediana". Fix: incluir `deviation_ratio` e `deviation_ratio * 100` no
  pool — se o LLM fez a mesma conta que o extrator, é grounded.

**Resultado final:** 0.90 → 1.00. Todos os 3 checks em 1.0, exit 0.

**Meta-lição.** Eval de LLM em primeira iteração é tão defeituoso quanto o
LLM. A ordem correta: construir eval → ver falhas → assumir primeiro que é
o eval errado → só depois suspeitar do LLM. Aplicado aqui, todos os 4 bugs
eram do check, nenhum do LLM. Salvou tempo de prompt engineering
desnecessário.

---

### 2026-04-19 — narrativa incluída em cada violação do report

**Contexto.** Primeira versão do eval só logava `{applicant_id, check, detail}`
nas violações. Na hora de diagnosticar, chamar `explain_decision()` de novo
pegava narrativa DIFERENTE (LLM não-determinístico) — impossível debugar o
texto que de fato falhou.

**Decisão.** Incluir `narrative` + `key_factors` dentro de cada objeto de
violação no JSON. Arquivo cresce ~1KB por violação; aceitável.

**Resultado.** Diagnóstico dos 3 bugs acima virou triagem de 5 minutos em
vez de reprodução especulativa.

---

## processo e meta-decisões

### 2026-04-20 — material pedagógico público + CI/CD nível 2 (branch protection + PR workflow)

**Contexto.** Duas decisões entrelaçadas:

1. A pasta `context/projeto-pedagogico/` (guia HTML + `melhorias-estruturais.md` + `pedagogical-inventory.md` + `platform-review.md`) era gitignored sob pretexto de "material de estudo privado". Na prática, o conteúdo **É** o valor pedagógico do projeto — manter privado escondia o que torna o projeto interessante pra quem aprende. Decisão: tornar público.

2. O fluxo de CI/CD estava no **nível 1 de maturidade** (ver `melhorias-estruturais.md::T.10`): `push main → deploy prod`, sem PR, sem approval, sem staging. Funciona pra lab solo, mas não é o que qualquer time de fintech real faz.

**Decisão.** Subir pro **nível 2**: branch protection em `main` + PR workflow obrigatório.

Implementação concreta:

- **`.gitignore`**: remover `context/` da lista de ignorados. Adicionar comentário explicando que o conteúdo é público mas o CI **ignora mudanças ali** via `paths-ignore` no workflow (evita redeploys desnecessários quando editamos docs).
- **Branch protection em `main`** (via `gh api`):
  - `required_pull_request_reviews` ativo (force push e push direto bloqueados)
  - `required_status_checks.contexts = ["test"]` — PR não faz merge sem CI verde no job de test
  - `required_approving_review_count: 0` — solo dev pode merge sozinho, mas tem que passar pelo PR
  - `enforce_admins: false` — admin pode bypassar em emergência; a regra é speed-bump, não bloqueio permanente
- **Fluxo daqui pra frente**: `git checkout -b feat/foo && ... && gh pr create` no lugar de `git push origin main`.

**Alternativas consideradas:**

- *Manter nível 1* — coerente com "projeto solo", mas perde o ensino do fluxo que o aluno vai ver no primeiro emprego em fintech.
- *Pular pra nível 3 (staging + manual promotion)* — saltaria um degrau; PR workflow é pré-requisito.
- *Nível 2 com `enforce_admins: true`* — mais rigoroso, mas trava o admin em emergências. Pra solo sem time, false é pragmático.

**Trade-off aceito.** Fluxo fica mais lento (não dá mais `git push origin main` direto). Em contrapartida: o diff sempre passa por uma tela de PR, onde eu mesmo revejo antes de merge. Simula review sem precisar de segunda pessoa.

**Meta-lição pedagógica.** Esse upgrade é parte do que T.10 (`melhorias-estruturais.md`) documentou como lacuna. Saiu de registro → implementação. Em time real, os próximos níveis seriam staging environment (nível 3), feature flags (nível 4), e canary + auto-rollback (nível 5).

---

### 2026-04-19 — preservar evolução (sem force-push rebase no `main`)

**Contexto.** Texto "entrevista" escrito originalmente nos runbooks de demo
precisou ser genericizado. Tentativa inicial: rebase `--autosquash` pra
absorver o refactor no commit original + `git push --force-with-lease`.

**Decisão.** Desfazer a rebase (`git reset --hard`) e commitar o refactor
como novo commit por cima. Repo é público — force push reescreve história
publicamente visível, afeta forks/clones, e não apaga commits do cache do
GitHub (ficam dangling por ~90 dias).

**Trade-off aceito.** Git log mostra "tinha entrevista, generalizei" em vez
de uma história linear limpa. Pra um lab de aprendizagem, a evolução é
conteúdo pedagógico, não ruído. A própria narrativa do repo documenta o
processo de pensamento.

---

### 2026-04-19 — reports/ gitignored (narrativas derivadas do Kaggle)

**Contexto.** `scripts/eval_explainer_rule.py` gera JSONs em `reports/` contendo
narrativas individuais com features citadas (`value`, `median`, `applicant_id`).

**Decisão.** Adicionar `reports/` ao `.gitignore`. Consistente com a linha
existente sobre o dataset Kaggle original — narrativas derivadas preservam
o 1:1 com linhas do dataset, então a zona cinzenta de redistribuição se
aplica aqui também, mesmo que menos claramente.

**Análise da licença Kaggle.** OpenML classifica o dataset como "Public"
(https://www.openml.org/d/45577). Mas a ToS oficial da competição (2011)
é JS-gated e não foi lida literalmente. Manter gitignored é a escolha
conservadora zero-custo — dá pra relaxar depois se o usuário decidir
publicar com atribuição no README.

---

## reavaliações e pivots

### 2026-04-19 — Bônus F5: SHAP nativo (não via lib `shap`) + thresholds de decisão + feature validation

**Contexto.** Implementação do `src/decision_explainer_ml.py` esbarrou em
incompatibilidade: a lib `shap==0.48.0` falha ao parsear `base_score` do
XGBoost 3.x (recebe como string de lista `'[4.9998403E-1]'`, não consegue
converter pra float).

**Decisão.** Usar **SHAP nativo do XGBoost** via
`Booster.predict(DMatrix(X), pred_contribs=True)` em vez da lib externa.
Contribs retornados têm shape `(n, n_features + 1)` com bias na última
coluna — descartar a coluna final dá os SHAP values da linha. Zero
dependência adicional.

**Decisão 2.** Thresholds de decisão fixos: `prob < 0.30 → APROVADO`,
`0.30-0.60 → APROVADO_COM_LIMITE`, `≥ 0.60 → NEGADO`. Conservador pra
`APROVADO` (só quando modelo tem alta confiança de não-default) e rígido
pra `NEGADO` (precisa de evidência forte). Não é threshold otimizado por
business cost (T.9#5) — é didático.

**Decisão 3.** Cache por chave separado entre v1 e v2 (`_explanation_cache`
vs `_explanation_cache_ml`). Mesmo `applicant_id`, respostas distintas —
compartilhar dict sobrescreveria.

**Decisão 4.** Feature validation em inferência (T.9#2 aplicado):
`_validate_features()` checa que o mart tem todas as colunas que o bundle
do modelo espera. Se faltar, `RuntimeError` barulhento em vez de
reordenação silenciosa do pandas. Direto pro caminho crítico.

**Observação pedagogicamente valiosa.** Applicant 23380 (pre-validado no
`demo_bonus4_warmup.sh` como "NEGADO via tier HIGH") recebe decisão
**diferente** da v2: `pred_default_prob=0.36` → `APROVADO_COM_LIMITE`.
Ou seja, o modelo treinado em 144k históricos é **menos conservador** que
a regra SQL univariada. Demo side-by-side expõe isso — material de
conversa em entrevista.

---

### 2026-04-19 — arquitetura paralela v1/v2: adicionar Fase 5 + promover bônus pra Bônus Fase 4

**Contexto.** Análise de aderência do bônus ao produto real de um sistema de análise de crédito
expôs que o pipeline inteiro até aqui era **100% rule-based** — a
classificação de risco vinha de um `CASE WHEN` de 3 linhas em
`models/mart_credit_features.sql` e o label `defaulted` do Kaggle
jamais foi usado pra treinar nada. O projeto se chama "Credit
Intelligence Pipeline" e não tinha modelo treinado.

**Decisão.** Estrutura paralela v1/v2 em vez de substituição destrutiva:

- **Bônus Fase 4 (v1)** = o bônus atual renomeado, LLM narra a regra SQL
- **Fase 5** (nova) = treinar XGBoost + benchmarking contra baseline rule-based
- **Bônus Fase 5 (v2)** = LLM narra o modelo ML com SHAP values

**Alternativas descartadas:**

- *Substituir bônus por Fase 5* — empacota dois tópicos diferentes
  (engenharia de AI vs. modelagem ML) num só slot. Destrutivo.
- *Refatorar bônus existente pra consumir o modelo* — rewrite de
  `decision_explainer.py`, destrói o v1. Inconsistente com a meta-decisão
  "preservar evolução em repo público".
- *Single endpoint com query param `?source=rule|ml`* — engenharia
  elegante mas esconde a progressão pedagógica.

**Opção A escolhida**: arquivos paralelos. `decision_explainer_rule.py`
+ `decision_explainer_ml.py`, endpoints `/explain-decision/rule/{id}` +
`/explain-decision/ml/{id}`, evals paralelos. Duplicação consciente —
cada fase é demoável isoladamente e a comparação lado a lado vira
conteúdo de entrevista.

**Renames não-destrutivos aplicados:** `decision_explainer.py` →
`_rule.py`, `eval_explainer.py` → `_rule.py`, `demo_bonus_warmup.sh` →
`demo_bonus4_warmup.sh`, `demo-bonus.md` → `demo-bonus-fase4.md`,
`bonus.html` → `bonus-fase4.html`, endpoint `/explain-decision/{id}`
→ `/explain-decision/rule/{id}`.

**Novos guias HTML:** `fase-5.html`, `bonus-fase5.html`. Código a
implementar em sessões subsequentes.

**Hub reestruturado:** 5 cards → **7 cards planos**, stats
atualizadas (5 fases, 28 desafios, 10 ferramentas com XGBoost + SHAP).

**Meta-lição.** O fato de que o projeto rodou 4 fases sem usar o label
real do dataset é sinal de que "intelligence" no nome não basta —
precisa de training loop. A estrutura v1/v2 também ensina um padrão
arquitetural valioso: quando você tem um conceito (explicação de decisão)
que pode ter vários backings (regra, ML, futuro: ensemble), separar o
interface do implementation em arquivos paralelos torna cada backing
testável, substituível e compreensível isoladamente.

---

### 2026-04-18 — pivot do bônus: `/insights` → `/explain-decision`

**Contexto.** Bônus original pedia endpoint `GET /insights` com LLM resumindo
o histórico de métricas do pipeline (`metrics_history.jsonl`) em PT-BR.
Análise crítica da aderência ao dia a dia de um sistema de análise de crédito (domínio de
"last mile do crédito", empresa-alvo do hackathon) mostrou que LLM narrando
métricas é **meta-observabilidade** (dashboard narrado), não o coração do
produto deles.

**Decisão.** Trocar por `GET /explain-decision/{applicant_id}` — explicação
de decisão de crédito em PT-BR com guardrails. Encosta no caminho do dinheiro
do sistema (reason-code regulatório para cumprir Res.
4.935/Bacen), mantém toda a infra do bônus original (FastAPI, cache, LLM em
produção, PT-BR), e ganha a separação extrator/narrador como conteúdo
pedagógico central.

**Outcome.** B.1 + B.2 reescritos. Adicionado B.3 (eval) e B.4 (runbook de
demo) que não existiam antes. Total passou de 2 → 4 desafios no bônus.

---

### 2026-04-19 — demos reframadas: de "entrevista" pra "qualquer demonstração"

**Contexto.** Runbooks `DEMO.md`/`DEMO_BONUS.md` foram escritos com framing
explícito de entrevista técnica ("demonstrar pro entrevistador", "na call",
"killer moment"). Usuário corrigiu: essas demos servem pra vários cenários —
validação pessoal pós-deploy, showcase pra mentor/colaborador, portfólio,
auditoria — e entrevista é só **um caso particular**.

**Decisão.** Reescrever runbooks + challenges 4.5/B.4 nos HTMLs com framing
genérico. Lista de 4 cenários no topo de cada doc. Trocar "killer moment"
por "ponto alto da demo". Manter toda a estrutura de beats e perguntas
frequentes — o conteúdo é útil em qualquer audiência.

**Arquivos renomeados.** `DEMO.md` → `demo.md`; `DEMO_BONUS.md` →
`demo-bonus-fase4.md` (feedback secundário: lowercase kebab-case como padrão).

---

### 2026-04-19 — outlier invisível descoberto pelo eval (Fase 1/2)

**Contexto.** Eval do Bônus B.3 expôs `applicant_id 93515`: `monthly_income:
1.0`, `debt_ratio: 1161.0`, classificado como `LOW → APROVADO`. Pipeline
aprovou alguém com renda de R$ 1 e dívida 1161× a renda.

**Diagnóstico.** Bug composto de duas fases:

- Fase 1: `validate_dataframe` sinaliza `is_valid: False` em outliers mas o
  flow não age sobre o flag — outliers passam pro mart.
- Fase 2: regra de tier em `models/mart_credit_features.sql` só olha
  `revolving_utilization` + atrasos. Ignora renda e `debt_ratio`. Regra
  univariada disfarçada de multivariada.

**Decisão (pendente de implementação).** Documentado em
`melhorias-estruturais.md::T.7` com fixes propostos: (1) converter warnings
de validação em blockers; (2) regra de tier multivariada incorporando
`monthly_income` e `debt_ratio`.

**Meta-lição.** Eval construído pra pegar alucinação de LLM encontrou bug
de **dado/regra de negócio** upstream que os testes de schema existentes
não pegavam. Eval em lote valida o sistema inteiro, não só o modelo.
