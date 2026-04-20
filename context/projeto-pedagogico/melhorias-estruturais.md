# Melhorias Estruturais — Fases 1, 2, 3 e 4

Reflexão feita após implementar as quatro fases do zero. Cada item aqui foi encontrado na prática, não antecipado no planejamento.

---

## Fase 1 — Ingestão e Validação

### 1.1 `requirements.txt` deveria ser o Desafio 1.0

O arquivo só foi criado na Fase 3, quando o Dockerfile o exigiu. Mas as dependências (`pandas`, `pyarrow`, `faker`) já existiam na Fase 1. Resultado: a Fase 3 introduz um conceito retroativo — o aluno cria o `requirements.txt` depois de ter instalado tudo "no olho".

**Melhoria:** transformar a criação do `requirements.txt` no primeiro ato da Fase 1. Isso ensina o hábito certo (`pip install` → registra imediatamente) e depois o Dockerfile da Fase 3 simplesmente referencia o arquivo já existente, fechando o ciclo de forma natural.

---

### 1.2 Estrutura de diretórios não declarada explicitamente

O guia menciona `data/raw/`, `data/staging/`, `data/marts/` nas descrições, mas não há um passo explícito de criação. Na prática, o CSV estava solto em `data/` e foi necessário mover manualmente. Para quem implementa pela primeira vez, isso gera erros confusos de "file not found" antes de chegar na parte que importa.

**Melhoria:** adicionar um pré-requisito do Desafio 1.1 com o scaffold de diretórios:

```bash
mkdir -p data/{raw,staging,marts,monitoring}
mkdir -p src pipeline api models tests .github/workflows
touch src/__init__.py pipeline/__init__.py api/__init__.py
```

Isso também resolve o problema dos `__init__.py` (ver item abaixo).

---

### 1.3 `src/` sem `__init__.py` — imports quebram na Fase 3

`src/ingestion.py` e `src/transform.py` são importados no `pipeline/flow.py` com `from src.ingestion import ...`. Mas `src/` não tem `__init__.py`, então o import só funciona com o hack `sys.path.insert(0, '.')` na frente. Não é errado, mas não é o padrão Python para packages.

**Melhoria:** o scaffold do item 1.2 já cria o `__init__.py`. Alternativamente, mudar o import no flow para usar `importlib` ou instalar o projeto com `pip install -e .` — mas isso aumenta a complexidade sem benefício claro para o nível do projeto pedagógico.

---

### 1.4 `validate_dataframe` sempre retorna `is_valid: False` para este dataset

A regra `DebtRatio > 100` dispara em 24.380 linhas (16% do dataset). O guia descreve `is_valid` como flag que indica se o dado está pronto para processamento, mas um `is_valid: False` permanente faz o campo perder utilidade prática — o flow da Fase 3 não age sobre ele.

**Melhoria:** ou ajustar o threshold (`DebtRatio > 500` seria mais razoável para este dataset específico), ou transformar `is_valid` em `warnings` e `blockers` — `blockers` são os que realmente impedem o processamento (nulls acima de 30%), `warnings` são anomalias que valem logar mas não bloquear. Isso está mais próximo do que sistemas de qualidade de dados fazem na prática.

---

### 1.5 A lógica de "flag antes de fillna" não tem um teste que a protege

O comentário no código explica o risco, mas não há nenhum teste em `tests/` que verifique se `income_missing` tem valores 1 onde `MonthlyIncome` era nulo. É exatamente o tipo de bug que aparece silenciosamente numa refatoração futura.

**Melhoria:** adicionar ao `test_pipeline.py`:

```python
def test_absence_flag_coverage(mart):
    # income_missing deve ter ao menos alguns 1s — se todos forem 0,
    # o flag foi criado depois do fillna e o sinal foi perdido
    assert mart['income_missing'].sum() > 0, \
        "income_missing está todo zero — flag criado após fillna"
```

---

## Fase 2 — SQL e Modelagem

### 2.1 Caminhos de arquivo hardcoded dentro dos `.sql`

`stg_credit_applications.sql` tem `FROM 'data/staging/credit_applications.parquet'` com caminho relativo hardcoded. Funciona quando rodado da raiz do projeto, mas quebra silenciosamente se chamado de outro diretório — e o erro é um `IOException` do DuckDB que não é óbvio.

**Melhoria:** receber o caminho como parâmetro no `run_model()` e fazer interpolação:

```python
sql = sql.replace('{{staging_path}}', str(ROOT / 'data' / 'staging'))
```

Isso também torna os modelos testáveis com fixtures apontando para paths de teste, sem tocar nos dados reais.

---

### 2.2 Deduplicação com `QUALIFY ROW_NUMBER()` é a parte mais difícil e menos explicada

O `QUALIFY` é SQL avançado — não é ensinado em cursos introdutórios. O guia menciona que é necessário deduplicar, mas não explica por que a chave `(age, monthly_income, debt_ratio)` foi escolhida, nem quantas linhas são removidas (5.599 de 150.000 — cerca de 3.7%).

**Melhoria:** adicionar uma query de diagnóstico antes do desafio que mostra o problema concreto:

```sql
SELECT age, monthly_income, debt_ratio, COUNT(*) AS n
FROM 'data/staging/credit_applications.parquet'
GROUP BY 1, 2, 3
HAVING n > 1
ORDER BY n DESC
LIMIT 5;
```

Ver os duplicatas reais antes de remover torna a solução muito mais intuitiva do que apresentar `QUALIFY` no vácuo.

---

### 2.3 `run_model` sempre carrega o staging como view — coupling implícito

`transform.py` sempre registra `stg_credit_applications` antes de executar qualquer modelo. Isso funciona, mas cria um coupling implícito: qualquer novo modelo que não dependa de staging vai carregar o staging de qualquer jeito. Em um projeto real com dezenas de modelos, isso seria um problema de performance.

**Melhoria estrutural:** detectar as dependências automaticamente via comentário no SQL:

```sql
-- depends_on: stg_credit_applications
```

E no `run_model`, parsear esse comentário para registrar só as views necessárias. Isso é exatamente como o dbt resolve dependências — e introduz o conceito de forma concreta.

---

### 2.4 Não há `.gitignore` — o `data/` inteiro seria commitado

O Parquet de staging tem 150k linhas e o de mart também. Sem `.gitignore`, um `git add .` commita arquivos binários grandes que não deveriam entrar no repositório.

**Melhoria:** criar `.gitignore` como parte do scaffold inicial:

```
.venv/
__pycache__/
data/raw/
data/staging/
data/marts/
data/monitoring/
*.parquet
*.json
!requirements.txt
.DS_Store
```

---

## Fase 3 — Orquestração e API

### 3.1 `subprocess.run(['pytest', ...])` quebra em virtualenvs

O flow chama `pytest` pelo nome, mas o pytest está instalado no `.venv`, não no PATH do sistema. O erro (`FileNotFoundError: 'pytest'`) aparece na última task depois de tudo ter funcionado — frustrante porque todas as tasks anteriores passaram.

**Melhoria:** o guia deveria mostrar `sys.executable -m pytest` como o padrão correto, explicando que `sys.executable` é sempre o Python que está rodando o script atual — e portanto inclui o venv correto. Isso é um gotcha que afeta qualquer subprocess Python-dentro-de-Python.

---

### 3.2 A API não tem `__init__.py` no pacote `api/`

`uvicorn api.main:app` funciona porque o uvicorn resolve o módulo pelo path. Mas `from api.main import app` em testes falharia sem `api/__init__.py`. O guia manda criar `api/main.py` sem mencionar o `__init__.py`.

**Melhoria:** coberto pelo scaffold do item 1.2 — criar todos os `__init__.py` de uma vez no início.

---

### 3.3 O Prefect sobe um servidor temporário a cada execução local

Ao rodar `python pipeline/flow.py` sem um servidor Prefect dedicado, o Prefect 3.x sobe e derruba um servidor temporário a cada execução (porta aleatória). Isso adiciona ~8 segundos de overhead e gera logs confusos sobre `http://127.0.0.1:850x` que desorientam quem não conhece o Prefect.

**Melhoria:** adicionar no guia a opção `serve()` para desenvolvimento local:

```python
if __name__ == "__main__":
    credit_pipeline.serve(name="dev-run")
```

Ou explicar que o servidor temporário é normal e esperado no modo local — atualmente o log aparece sem contexto.

---

### 3.4 `/risk-summary` não tem validação cruzada automatizada com os benchmarks do DuckDB

O guia menciona que `default_rate_pct` deve bater com o benchmark do Desafio 2.1 (margem de ±0.1%), mas essa verificação é manual. Não há nenhum teste que execute isso automaticamente.

**Melhoria:** adicionar um teste de integração que sobe a API, chama `/risk-summary`, e verifica os valores contra os benchmarks conhecidos:

```python
# tests/test_api.py
from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)

def test_risk_summary_default_rate():
    r = client.get("/risk-summary")
    assert r.status_code == 200
    rate = r.json()["default_rate_pct"]
    # Benchmark do DuckDB Fase 2: ~6.7% para o mart limpo
    assert 6.0 < rate < 7.5, f"default_rate_pct fora do esperado: {rate}"
```

---

## Transversal — o que vale adicionar às três fases

### T.1 Sem nenhum arquivo de configuração central

Paths como `data/raw/cs-training.csv`, `data/marts/mart_credit_features.parquet` aparecem em pelo menos 4 arquivos diferentes (`ingestion.py`, `transform.py`, `flow.py`, `main.py`). Mudar a estrutura de pastas exige busca e substituição manual.

**Melhoria:** um `config.py` simples na raiz de `src/`:

```python
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA_RAW     = ROOT / "data" / "raw"
DATA_STAGING = ROOT / "data" / "staging"
DATA_MARTS   = ROOT / "data" / "marts"
CSV_PATH     = DATA_RAW / "cs-training.csv"
API_JSON     = DATA_RAW / "bureau_api.json"
STAGING_PARQUET = DATA_STAGING / "credit_applications.parquet"
MART_PARQUET    = DATA_MARTS / "mart_credit_features.parquet"
```

Todos os módulos importam de `src.config` — mudar uma pasta é uma linha.

---

### T.2 Nenhuma fase tem um "smoke test" de início rápido

Para verificar se o ambiente está correto antes de começar cada fase, não há um comando único. O aluno descobre que algo está quebrado só quando roda o código de verdade.

**Melhoria:** adicionar ao guia HTML um bloco de verificação no início de cada fase:

```bash
# Fase 1
python -c "import pandas, pyarrow, faker; print('ok')"

# Fase 2  
python -c "import duckdb; print('DuckDB', duckdb.__version__)"

# Fase 3
python -c "import prefect, fastapi, uvicorn; print('ok')"
```

Simples, mas economiza 20 minutos de debugging de ambiente.

---

### T.3 O `.venv` está dentro do projeto sem `.gitignore`

A pasta `.venv/` tem ~288 arquivos Python e bibliotecas. Sem `.gitignore`, um `git init && git add .` commita tudo isso. Coberto pelo item 2.4, mas vale reforçar como problema transversal.

---

### T.4 Nenhuma fase tem tutorial de configuração das ferramentas principais

O guia assume que o aluno já sabe instalar e configurar cada ferramenta antes de usá-la. Na prática, esse pressuposto quebra em pelo menos quatro momentos ao longo do projeto:

- **DuckDB:** a maioria conhece SQLite, mas não sabe que DuckDB lê Parquet diretamente nem que colunas com hífens exigem aspas duplas no SQL — dois comportamentos que não estão em nenhum tutorial genérico
- **FastAPI:** alunos vindos de Flask tentam `return jsonify(...)` e ficam confusos com o modelo de respostas automáticas; a documentação interativa em `/docs` (Swagger UI) não é mencionada em nenhum lugar do guia, mas é o jeito mais rápido de testar os endpoints sem `curl`
- **Prefect:** o servidor temporário que sobe a cada `python pipeline/flow.py` gera logs de `http://127.0.0.1:850x` sem explicação — parece um erro, não é
- **GCP:** é a mais crítica. O aluno precisa criar projeto, instalar `gcloud`, habilitar APIs, criar Service Account com permissões mínimas, gerar JSON de credenciais, e configurar GitHub Secrets — são 9 passos antes de rodar o primeiro `gcloud` do Desafio 4.3. Sem um tutorial dedicado, o aluno gasta mais tempo configurando infraestrutura do que aprendendo o conceito de deploy

**Melhoria:** adicionar ao guia HTML um bloco colapsável "⚙️ Setup da ferramenta" no início de cada desafio que introduz uma nova ferramenta. O bloco deve cobrir:

1. **Instalação** — comando exato para o ambiente do projeto (não link para a docs oficial)
2. **Verificação** — um comando de smoke test que confirma que a instalação funcionou
3. **Gotcha principal** — o comportamento contraintuitivo mais comum para quem vem de outra ferramenta

Exemplo para o Desafio 4.3 (GCP):

```
⚙️ Setup do GCP — expanda antes de começar

1. Criar projeto no console.cloud.google.com e anotar o PROJECT_ID
2. Instalar gcloud CLI: brew install --cask google-cloud-sdk
3. Autenticar: gcloud auth login && gcloud config set project SEU_PROJECT_ID
4. Criar Service Account com roles/run.admin + roles/artifactregistry.writer
5. Gerar credenciais: gcloud iam service-accounts keys create credentials.json ...
6. Adicionar GCP_SA_KEY e GCP_PROJECT_ID em Settings → Secrets → Actions no GitHub
```

O formato colapsável mantém a página limpa para quem já conhece a ferramenta, mas remove o bloqueio completo para quem nunca usou. A ausência desse tutorial no Desafio 4.3 é o principal motivo pelo qual o aluno pode passar mais tempo em setup de infraestrutura do que no aprendizado de CI/CD em si.

---

### T.5 Arquitetura da imagem Docker não é mencionada — quebra silenciosamente no Cloud Run

Quem desenvolve em Mac com Apple Silicon (M1/M2) builda imagens Docker em `arm64` por padrão. O Cloud Run roda em `linux/amd64`. O resultado: o container sobe perfeitamente local mas falha no Cloud Run sem nenhuma mensagem de erro útil — o processo crasha antes de iniciar qualquer log, e o Cloud Run retorna apenas "failed to start and listen on the port within the allocated timeout".

O diagnóstico não é óbvio porque o erro aponta para porta, não para arquitetura. A investigação natural (verificar porta, aumentar memória, checar timeout) não resolve nada.

**Melhoria:** o Desafio 4.3 deve mencionar explicitamente a flag `--platform` no comando de build:

```bash
# Sem isso, Mac M1/M2 gera imagem arm64 que o Cloud Run não consegue executar
docker buildx build --platform linux/amd64 -t $IMAGE . --load
docker push $IMAGE
```

E adicionar um passo de verificação antes do deploy:

```bash
# Confirma que a imagem é amd64 antes de fazer push
docker inspect $IMAGE --format '{{.Architecture}}'
# deve retornar: amd64
```

Esse é um gotcha que afeta qualquer serviço de cloud (Cloud Run, ECS, Kubernetes) quando o desenvolvimento é feito em Apple Silicon. Vale mencionar uma vez no início da Fase 4 e não apenas no passo de build.

---

### T.6 API acoplada a dado de build — o anti-pattern que só aparece no CI

O `Dockerfile` da Fase 4 contém `COPY data/marts/ ./data/marts/` e a `api/main.py` lê o parquet no import (`pd.read_parquet('data/marts/...')`). No deploy manual da máquina local funciona — o parquet está lá porque o aluno rodou o pipeline antes. Mas o CI não tem esses dados: o dataset Kaggle (`data/raw/cs-training.csv`) está no `.gitignore` por termos de uso, então o pipeline não roda no runner, e o mart derivado também não existe. O `docker build` quebra com `COPY failed: "/data/marts": not found` e o diagnóstico é confuso porque "funciona localmente".

O problema de fundo é conceitual: **dado não é código**. Empacotar o parquet no container mistura duas coisas que têm ciclos de vida diferentes — código muda a cada commit, dado muda a cada execução do pipeline, e amarrá-los obriga a refazer o build toda vez que o dado regenera. Além disso, a imagem Docker carrega o peso do dado de treino pra cada cold start de serving, que é o oposto do que containers foram feitos pra fazer.

**Melhoria:** a Fase 4 deveria introduzir o padrão "imagem imutável, dado externo" como parte do currículo, não como dívida que o aluno tropeça depois:

1. **Subir o artefato pra um bucket GCS na mesma região do Cloud Run.** Egress `GCS → Cloud Run same-region` é gratuito, então a escolha é barata e ensina o padrão canônico de ML serving em GCP.

2. **Fazer a API baixar do bucket no startup usando Application Default Credentials (ADC).** Sem chaves JSON no container:

   ```python
   def _load_mart() -> pd.DataFrame:
       bucket = os.getenv("MART_BUCKET")
       obj = os.getenv("MART_OBJECT")
       if bucket and obj:
           from google.cloud import storage
           local = "/tmp/mart_credit_features.parquet"
           storage.Client().bucket(bucket).blob(obj).download_to_filename(local)
           return pd.read_parquet(local)
       return pd.read_parquet("data/marts/mart_credit_features.parquet")  # dev local
   ```

   O fallback pro disco local preserva a DX de desenvolvimento — o aluno roda `uvicorn api.main:app` da máquina dele sem precisar configurar ADC.

3. **Deploy no Cloud Run com `--service-account` e `--set-env-vars`:**

   ```bash
   gcloud run deploy credit-api \
     --service-account credit-pipeline-sa@$PROJECT_ID.iam.gserviceaccount.com \
     --set-env-vars MART_BUCKET=...,MART_OBJECT=mart_credit_features.parquet \
     ...
   ```

   Com `roles/storage.objectViewer` no bucket específico (nunca no projeto inteiro), princípio do menor privilégio na prática.

Esse arranjo ensina três conceitos valiosos de uma vez — IAM fino, ADC, e separação imagem/dado — e tem custo essencialmente nulo (4 MB em GCS Standard = ~R$0,001/mês). É o tipo de desbloqueio que só aparece quando o CI tenta rodar o que funcionava localmente, e é por isso que a Fase 4 é o momento certo de apresentar o conceito.

---

### T.7 Outlier de renda + regra de tier univariada — o que o eval do Bônus expôs

Ao rodar `scripts/eval_explainer.py --n 21` pela primeira vez, o eval do Bônus B.3 sinalizou 16 violações de grounded-ness. A maior parte era falso-positivo de formatação (o LLM escreve `R$ 5.400,00` em padrão BR e o regex do check interpretava mal). Mas inspecionar as violações revelou um caso embaraçoso:

```
applicant_id 93515
  debt_ratio:            1161.0     (mediana da carteira: 0.36)
  monthly_income:        1.0        (mediana: 5400.0)
  revolving_utilization: 0.0
  risk_tier:  LOW
  decision:   APROVADO
```

**O pipeline aprovou um tomador com renda declarada de R$ 1 e dívida 1161 vezes a renda.** A narrativa do LLM foi factualmente correta (citou os valores recebidos) — o problema estava duas camadas acima, no motor de risco.

**Duas causas compostas:**

1. **Validação da Fase 1 não filtra outliers extremos.** O `validate_dataframe` (item 1.4) já sinalizava `DebtRatio > 100` em 16% das linhas, mas só como `is_valid: False` informativo — o flow não age sobre o flag e o mart absorve os outliers. Renda de R$ 1 provavelmente veio de erro de entrada no CSV original do Kaggle, e passou ilesa.

2. **Regra de tier em `models/mart_credit_features.sql` é univariada.** A classificação só olha `revolving_utilization` e atrasos:

   ```sql
   CASE
       WHEN revolving_utilization > 0.9 OR late_90_days > 2 THEN 'HIGH'
       WHEN revolving_utilization > 0.5 OR late_30_59_days > 1 THEN 'MEDIUM'
       ELSE 'LOW'
   END
   ```

   Tomador sem cartão rotativo e sem atrasos → LOW, mesmo com renda R$ 1 e debt_ratio 1161. É uma regra de uma variável disfarçada de três — na verdade só olha comportamento de crédito, ignora capacidade de pagamento.

**Melhoria dupla:**

- **Fase 1** — transformar `validate_dataframe` em função que realmente filtra em vez de só logar. Uma regra mínima: `monthly_income >= 100` + `debt_ratio <= 50` como blockers; valores fora desse range são outliers estatísticos que não representam tomador viável e contaminam a carteira.

- **Fase 2** — regra de tier multivariada que incorpora renda e debt_ratio:

  ```sql
  CASE
      WHEN revolving_utilization > 0.9 OR late_90_days > 2
           OR debt_ratio > 5 OR monthly_income < 500           THEN 'HIGH'
      WHEN revolving_utilization > 0.5 OR late_30_59_days > 1
           OR debt_ratio > 1.5                                  THEN 'MEDIUM'
      ELSE 'LOW'
  END
  ```

  Thresholds são exemplo — num sistema real viriam do time de risco calibrando safras. O ponto é que capacidade (renda, debt_ratio) e comportamento (rotativo, atrasos) são eixos independentes e a regra precisa respeitar isso.

**Meta-lição pedagógica:** o eval do Bônus foi construído pra pegar alucinação do LLM. Na primeira execução ele expôs um bug de **dado/regra de negócio** das Fases 1 e 2 que estava ali o tempo todo e nunca foi visto — porque os testes existentes (`test_pipeline.py`) validam invariantes de schema, não de sensibilidade das decisões. Eval de qualidade de output encontra regressões **upstream** do sistema, não só do modelo. Esse tipo de achado é o valor real de ter um eval em lote no final do pipeline, mesmo num projeto de aprendizagem.

---

### T.8 GitHub Actions — boas práticas silenciosamente ausentes

O workflow `.github/workflows/pipeline.yml` funciona (test + deploy verdes), mas tem várias lacunas que num time real custariam minutos do runner, segurança ou dinheiro. A Fase 4 (desafio 4.4) ensina "push main → CI roda testes e deploya" como se isso bastasse — mas CI/CD bem feito tem camadas que o guia atual ignora.

**Exemplo concreto do desperdício atual.** Nos últimos pushes desta sessão, os seguintes commits dispararam 3 minutos completos de CI **sem necessidade**:

- `ab9fd1c` — só adicionou `.claude/` ao `.gitignore`
- `aa53fca` — só renames de arquivos `.md`
- `108b7c0` — só criou `decisions.md`
- `4ecc7c7` — só `reports/` no `.gitignore`
- `c3d94ea` — só atualização de `decisions.md`

Nenhum desses toca código Python, nenhum muda o Dockerfile, nenhum muda o workflow em si — ainda assim rebuildaram imagem, fizeram push e redeployaram. O free tier do GitHub Actions dá 2000 minutos/mês, então pra projeto pedagógico pessoal não estoura; num time com 50 devs, isso vira conta real.

**Melhoria em 3 prioridades:**

**🔴 Alta — implementar na próxima iteração do workflow:**

1. **Filtros `paths-ignore`**: bloquear execução em commits docs-only.

   ```yaml
   on:
     push:
       branches: [main]
       paths-ignore:
         - '**.md'
         - 'context/**'
         - 'reports/**'
         - 'models/**'
         - '.gitignore'
         - 'LICENSE'
     pull_request:
       branches: [main]
       paths-ignore: [mesmo]
   ```

2. **`concurrency` com `cancel-in-progress`**: quando se pusha 3 commits em rajada, só o último importa. Sem isso, os 3 rodam em paralelo.

   ```yaml
   concurrency:
     group: ${{ github.workflow }}-${{ github.ref }}
     cancel-in-progress: true
   ```

3. **pip cache via `setup-python`**: cada run reinstala ~60 pacotes (~30-60s). O action já suporta, só não estava habilitado.

   ```yaml
   - uses: actions/setup-python@v5
     with:
       python-version: '3.11'
       cache: 'pip'
       cache-dependency-path: 'requirements.txt'
   ```

**🟡 Média — higiene de segurança e operação:**

4. **`permissions` mínimas**: default `GITHUB_TOKEN` tem write em issues/PRs/actions. Job de test só precisa `contents: read`. Reduz vetor de ataque se um step malicioso vazar numa dependência comprometida.

   ```yaml
   jobs:
     test:
       permissions:
         contents: read
   ```

5. **`timeout-minutes`**: sem limite, job travado roda até o max do runner (6h) queimando minutos. `timeout-minutes: 10` no test, `20` no deploy.

6. **Migração Node.js 24**: todos os runs têm warning — `actions/checkout@v4`, `actions/setup-python@v5`, `google-github-actions/auth@v2` rodam em Node 20, deprecated em **2026-06-02** pela GitHub. Dois caminhos: aguardar versões novas dos actions com suporte Node 24, ou setar `env: FORCE_JAVASCRIPT_ACTIONS_TO_NODE24=true` no workflow pra forçar agora e validar compatibilidade.

**🟢 Baixa — conceitualmente importantes, pragmaticamente baixo ROI pra lab solo:**

7. **SHA pinning de actions**: `actions/checkout@a1b2c3d...` em vez de `@v4`. Protege contra supply chain attacks (tag `@v4` pode ser re-apontada). GitHub Security Lab recomenda. Trade-off: atualização manual de cada SHA quando sair nova versão.

8. **Docker BuildKit cache**: `docker build` atualmente reconstrói tudo desde `apt install`. Com cache no Artifact Registry ou `type=gha`, economia de 1-2min/deploy. Setup não trivial.

9. **OIDC Workload Identity Federation**: substituir `GCP_SA_KEY` (chave JSON em secret) por federação de identidade curta via `google-github-actions/auth@v2`. Remove secret de longa duração. Grande refactor — vale pra produção real, overkill pra lab.

10. **Environment approval gates**: `environment: production` com required reviewer. Impede deploy até alguém aprovar manualmente. Irrelevante pra solo; canônico em time.

**Fix mínimo sugerido (itens 1-5 combinados):**

```yaml
name: Credit Pipeline CI/CD

on:
  push:
    branches: [main]
    paths-ignore: ['**.md', 'context/**', 'reports/**', 'models/**', '.gitignore', 'LICENSE']
  pull_request:
    branches: [main]
    paths-ignore: ['**.md', 'context/**', 'reports/**', 'models/**', '.gitignore', 'LICENSE']

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

env:
  PROJECT_ID: ${{ secrets.GCP_PROJECT_ID }}
  REGION: us-central1
  SERVICE: credit-api
  REPO: credit-api

jobs:
  test:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'
          cache-dependency-path: 'requirements.txt'
      - run: pip install -r requirements.txt
      - run: pytest tests/ -v

  deploy:
    needs: test
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    timeout-minutes: 20
    permissions:
      contents: read
      id-token: write    # preparação pra OIDC futuramente
    steps:
      # ... (resto inalterado por enquanto)
```

**Meta-lição pedagógica:** a Fase 4 ensina "CI/CD é push pra main → deploy automatizado" como se o objetivo fosse passar o job. Na prática, CI/CD bem feito tem três responsabilidades simultâneas: **rodar só quando precisa** (path filters + concurrency), **rodar com privilégio mínimo** (permissions + OIDC), e **rodar rápido** (cache). Um workflow que acerta só a primeira parece funcionar em lab, mas não escala. Vale incorporar esses 3 eixos como conceito na próxima iteração do guia do Desafio 4.4 — não como "boas práticas extras" num apêndice, mas como **parte da definição de feito**.

---

### T.9 Fase 5 — backlog de ML engineering (onde foi tomado atalho)

A Fase 5 entregou um XGBoost calibrado com AUC 0.857 vs baseline 0.764 (+0.094), modelo versionado no GCS, 6 testes unitários de `prepare_dataset`, CI verde. Funciona — mas o objetivo pedagógico é expor **onde o atalho foi tomado**, porque a maior parte do trabalho de ML em produção mora nesses atalhos.

**🔴 Alta prioridade — fazer antes de declarar Fase 5 "pronta":**

1. **`src/train.py` usa `print()` em vez de logging estruturado.** Inconsistente com a Fase 4 (`src/logger.py` emite JSON pra Cloud Logging). Se algum dia o training rodar em cloud (Cloud Run Job, Vertex AI), os logs ficam perdidos. Fix: trocar os 5 `print()` por `log.info(..., extra={"stage": "...", "metric": ...})`. 10 linhas.

2. **Validação de feature list em inferência.** O bundle salva `features: list[str]`, mas nem `src/train.py::evaluate_and_benchmark` nem o futuro `decision_explainer_ml.py` checam se o mart ainda tem essas colunas. Se alguém adicionar uma coluna nova ao mart sem retreinar, a reordenação de colunas pelo pandas pode produzir predições erradas silenciosamente. Fix (vai direto pro `decision_explainer_ml.py`):

   ```python
   missing = set(bundle["features"]) - set(mart.columns)
   if missing:
       raise RuntimeError(f"Mart perdeu features do modelo: {missing}")
   X = mart[bundle["features"]]  # ordem determinística
   ```

3. **Outlier T.7 ainda no treino.** O modelo foi treinado no mart contendo `applicant_id 93515` (renda R$ 1, debt_ratio 1161). É ruído numérico — XGBoost é robusto, mas treinar sobre dado sabidamente sujo é má higiene. Resolver T.7 antes de declarar o modelo definitivo, retreinar, comparar AUC (esperado: mudança desprezível, mas honesto).

**🟡 Média — anotar como dívida, atacar conforme tempo:**

4. **Feature engineering manual.** Modelo usou 11 features cruas. Features derivadas podem somar 0.01-0.03 AUC e são ~10 linhas:

   ```python
   X["income_per_dependent"]  = X["monthly_income"] / (X["dependents"] + 1)
   X["delinquency_score"]     = 5*X["late_90_days"] + 3*X["late_60_89_days"] + X["late_30_59_days"]
   X["has_any_late"]          = (X["total_late_payments"] > 0).astype(int)
   X["utilization_x_debt"]    = X["revolving_utilization"] * X["debt_ratio"]
   ```

5. **Custo assimétrico ignorado.** `scale_pos_weight=13.78` assume que errar um FP (negar quem pagaria) e um FN (aprovar quem dá default) custa igual. Em crédito, FN custa **muito mais** — perda principal não recuperável vs receita perdida na aprovação. Fix: tuning de threshold de decisão por custo esperado em vez de 0.5 fixo. Conceitualmente grande, implementação em ~15 linhas.

6. **Zero fairness audit.** Modelo usa `age`, `dependents`, `income_missing` — features potencialmente sensíveis. Num projeto real de crédito regulado no Brasil, é requisito verificar TPR/FPR split por faixa etária pra detectar disparate impact. Fix: script `scripts/fairness_audit.py` que calcula TPR/FPR por bucket de idade e flaga diferenças maiores que threshold.

7. **Sem early stopping nem learning curves.** Treino fixo em `n_estimators=200`. Não sabemos se converge em 50, 200, 500. Fix: `XGBClassifier(early_stopping_rounds=20, eval_set=[(X_val, y_val)])` — ensina underfitting/overfitting na prática e expõe learning curves pra diagnóstico.

8. **Sem calibration validation.** Assumimos que `CalibratedClassifierCV` melhora Brier score — não medimos. Fix: `brier_score_loss` antes e depois da calibração no `evaluate_and_benchmark`, + reliability diagram no notebook de EDA.

9. **CI não retreina o modelo.** Gap arquitetural: `model-latest.pkl` pode divergir do código em `main`. Quatro caminhos possíveis, do mais simples ao mais sofisticado:
   - Doc-only: `decisions.md` explica que upload é manual (status quo, transparente)
   - Script: `scripts/train_and_upload.sh` que roda local e sobe com versão
   - CI job opcional: workflow com `workflow_dispatch` pra trigger manual
   - CI auto: job que roda `train.py` + upload + bump de tag em PRs que mexem em `src/train.py` ou features do mart

**🟢 Baixa — conceitualmente valiosas, pragmaticamente baixa prioridade pra lab solo:**

10. **Hyperparameter tuning via Optuna ou GridSearchCV.** Ganho esperado: 0.005-0.02 AUC. Custo: ~30min de compute local.
11. **Cross-validation 5-fold pra confidence interval do AUC.** Único split atual não dá sigma. Fix: `cross_val_score(calibrated, X, y, scoring="roc_auc", cv=5)` + CI reporting (mean ± std).
12. **Dockerfile de training.** Hoje depende de `libomp` no macOS. Um Dockerfile de treino cozinha o ambiente e torna o build reprodutível em qualquer máquina.
13. **Notebook `notebooks/fase5_eda.ipynb`.** ROC curve, calibration plot, feature importance, SHAP summary plot. Números frios viram insights visuais.
14. **Benchmark com LightGBM + LogReg + RF.** Variação deliberada: LogReg simples interpretável vs boosting caixa-preta — entendimento do trade-off com números.
15. **Endpoint `GET /predict/{id}` na API.** A Fase 5 cria modelo mas não serve — só o Bônus F5 consome. Um endpoint `predict` simples completaria o loop Fase 5 antes do Bônus F5 e separaria "scoring" de "explainability".
16. **Model drift detection no `src/monitor.py`.** Hoje monitora só o mart. Em produção, performance do modelo cai com o tempo (concept drift). Fix: log de `actual_vs_predicted` quando houver ground truth ou de `prediction_distribution` quando não houver (stability index).

**Fix sugerido em camadas:**

- **Antes do Bônus F5**: itens 1, 2, 3 da alta (logging + feature validation + resolver T.7).
- **Durante ou logo após Bônus F5**: itens 4-6 (feature eng, custo assimétrico, fairness).
- **Durante o Redesenvolvimento**: restante, na ordem em que você naturalmente tropeçar.

**Meta-lição pedagógica:** AUC 0.857 é um número. O **trabalho real** de ML engineering é saber onde esse número foi obtido com atalho — hyperparams default, custo simétrico, sem fairness, sem drift monitoring, sem validação de calibração — e qual a ordem de atacar isso. Projeto tradicional termina quando o modelo funciona; projeto honesto termina quando a lista de atalhos está explícita e priorizada. Essa seção é a versão explícita dessa lista — vale incorporar no guia da Fase 5 como **"O que este desafio NÃO ensina e por quê"** no final, com link pros itens de 🔴/🟡 como próximos passos para quem quer aprofundar.

---

### T.10 CI/CD nível 1 — `push → deploy prod` funciona, mas não é padrão de time

A Fase 4 ensina o fluxo `commit → CI → build → deploy → prod` como se fosse a definição de "feito". Funcionalmente correto para um lab solo, mas **muito abaixo do que qualquer time de fintech real faz**. O aluno conclui o projeto achando que CI/CD é isso — e, numa entrevista de senior, não vai saber responder "como vocês separam staging de prod?".

**Níveis de maturidade de CI/CD no mercado** (útil como mapa mental pro aluno entender onde ele está e pra onde pode ir):

| Nível | Fluxo | Usado por |
|---|---|---|
| **1 — push = deploy prod** (atual do projeto) | `commit → main → deploy prod` | Projetos solo, POCs, labs pessoais |
| **2 — feature branches + PR** | `feat/* → PR → merge main → deploy prod` | Maioria das startups pequenas/médias |
| **3 — staging + manual promotion** | `main → staging auto`; `tag v* → prod com approval` | Startups médias, fintechs começam aqui |
| **4 — trunk-based + feature flags** | Deploy contínuo em `main`, release controlada por flag (LaunchDarkly, Unleash) | Google, Meta, Netflix, Shopify |
| **5 — progressive delivery + auto-rollback** | Canary 5% → 25% → 100% com rollback automático em regressão de métrica | Bancos, telco, SaaS com SLA 99.99% |

**O que falta no currículo atual pra subir pelo menos até nível 3:**

1. **Branch protection + PR workflow** — `main` não deve aceitar push direto. Mesmo solo, abrir PR pra revisar o próprio diff treina um hábito obrigatório em qualquer time. Zero custo, alto valor pedagógico.

2. **Ambiente de staging separado** — deploy em push pra `main` vai pro staging; prod só sai por tag git ou aprovação manual. Exercita conceito de environment promotion e testes fora de produção.

3. **GitHub Environments com required reviewer** — deploy pra prod pede clique humano antes de executar. Ensina gate de aprovação, que em fintech regulada é requisito, não capricho.

4. **Versionamento semântico via tags** — `v0.1.0` como fonte da verdade de uma release, não SHA do último commit. Ensina release engineering e facilita rollback deliberado.

5. **Canary deploy via `--no-traffic` + `update-traffic`** — Cloud Run suporta nativamente. Deploy nova versão sem tráfego, depois migra 5% → 25% → 100%. Introduz conceito de progressive delivery sem depender de Argo/Flagger.

**Melhoria pedagógica proposta:**

- **Fase 4 adiciona item 4.6** — "Evoluindo o CI/CD": transforma o fluxo atual em PR-based + documenta o upgrade pra staging/tags.
- **Documento novo `ci-cd-maturity.md`** (em `docs/` ou `context/projeto-pedagogico/`) — os 5 níveis, o que cada um ensina, quando vale evoluir. Serve como bússola pro aluno.
- **Na Fase 4 e na seção "O que esta fase NÃO cobre"**: registrar explicitamente "staging environment, PR workflow, feature flags, canary deploys — próximos passos depois da fase de Redesenvolvimento".

**O que este projeto JÁ tem de bom** (vale reconhecer antes de criticar):

- CI passa **antes** do deploy (gate automático — nível 2 de maturidade de testes)
- Versionamento implícito por SHA do commit
- `paths-ignore` + `concurrency cancel-in-progress` (otimização de custo de runner)
- `permissions: contents: read` (least privilege no workflow)
- Secrets gerenciados via Secret Manager, não env plana
- Rollback documentado em `decisions.md` via `gcloud run services update-traffic`

**Meta-lição pedagógica:** a Fase 4 passa "CI/CD funcionando" como se fosse meta final. Em time real, **CI/CD funcionando sem buffer de segurança é artefato de projeto pessoal, não de produção**. Há um espectro de sofisticação que vai do "commit = deploy" (este projeto) até "5% de tráfego com rollback automático em métrica" (Netflix), e entender esse espectro é o que distingue alguém que **usa** CI/CD de alguém que **projeta** CI/CD. Currículo honesto explicita onde está nesse espectro e por quê.
