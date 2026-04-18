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

**Melhoria:** o scaffold do item 1.2 já cria o `__init__.py`. Alternativamente, mudar o import no flow para usar `importlib` ou instalar o projeto com `pip install -e .` — mas isso aumenta a complexidade sem benefício claro para o nível do hackathon.

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

O guia assume que o aluno já sabe instalar e configurar cada ferramenta antes de usá-la. Na prática, esse pressuposto quebra em pelo menos quatro momentos ao longo do hackathon:

- **DuckDB:** a maioria conhece SQLite, mas não sabe que DuckDB lê Parquet diretamente nem que colunas com hífens exigem aspas duplas no SQL — dois comportamentos que não estão em nenhum tutorial genérico
- **FastAPI:** alunos vindos de Flask tentam `return jsonify(...)` e ficam confusos com o modelo de respostas automáticas; a documentação interativa em `/docs` (Swagger UI) não é mencionada em nenhum lugar do guia, mas é o jeito mais rápido de testar os endpoints sem `curl`
- **Prefect:** o servidor temporário que sobe a cada `python pipeline/flow.py` gera logs de `http://127.0.0.1:850x` sem explicação — parece um erro, não é
- **GCP:** é a mais crítica. O aluno precisa criar projeto, instalar `gcloud`, habilitar APIs, criar Service Account com permissões mínimas, gerar JSON de credenciais, e configurar GitHub Secrets — são 9 passos antes de rodar o primeiro `gcloud` do Desafio 4.3. Sem um tutorial dedicado, o aluno gasta mais tempo configurando infraestrutura do que aprendendo o conceito de deploy

**Melhoria:** adicionar ao guia HTML um bloco colapsável "⚙️ Setup da ferramenta" no início de cada desafio que introduz uma nova ferramenta. O bloco deve cobrir:

1. **Instalação** — comando exato para o ambiente do hackathon (não link para a docs oficial)
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
