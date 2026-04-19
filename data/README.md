# data/

Estrutura de dados em camadas inspirada no padrão **medallion** (raw →
staging → mart → monitoring). Todas as subpastas com dados derivados
estão no `.gitignore` — devem ser reproduzíveis rodando o pipeline.

## Layout

```
data/
├── raw/                     # fonte da verdade (Kaggle CSV + API mock)
│   ├── cs-training.csv      ← baixar manualmente (ver abaixo)
│   ├── cs-test.csv          ← baixar manualmente
│   └── bureau_api.json      ← gerado pelo pipeline (Faker)
├── staging/                 # limpo, fiel à fonte, um arquivo Parquet por tabela
│   └── credit_applications.parquet
├── marts/                   # feature tables para ML e analytics
│   └── mart_credit_features.parquet
├── monitoring/              # observabilidade do pipeline
│   └── metrics_history.jsonl    (append-only, uma linha por execução)
├── Data Dictionary.xls      ← dicionário de dados (do próprio Kaggle)
└── sampleEntry.csv          ← template de submissão Kaggle (não usado em produção)
```

**Nenhum arquivo de dados (.csv, .parquet, .json) fora deste README vai
pro git** — ver [`.gitignore`](../.gitignore) do repo.

## Dataset fonte: Give Me Some Credit (Kaggle 2011)

- **Competition**: https://www.kaggle.com/competitions/GiveMeSomeCredit
- **Publicador**: Kaggle, em parceria com uma instituição de crédito
  anônima (dataset corporativo real, ~150k tomadores, anonimizado)
- **Task**: prever `SeriousDlqin2yrs` (inadimplência 90+ dias em 2 anos)
- **Features**: 11 colunas (renda, uso de crédito rotativo, razão
  dívida/renda, número de linhas abertas, atrasos em 3 buckets,
  dependentes, idade, flag de renda ausente)
- **Label**: binário, ~6.8% de positivos (desbalanceado, típico de
  crédito)

### Como baixar

1. Crie uma conta gratuita em [kaggle.com](https://www.kaggle.com/)
2. Aceite os [termos da competition](https://www.kaggle.com/competitions/GiveMeSomeCredit/rules)
   (clique "Late Submission" se já estiver encerrada — o dataset continua
   acessível)
3. Baixe manualmente:
   - `cs-training.csv` → salve em `data/raw/`
   - `cs-test.csv` → salve em `data/raw/`
   - (opcional) `Data Dictionary.xls` → salve em `data/`
4. Alternativa via CLI se você configurou [Kaggle API](https://github.com/Kaggle/kaggle-api):
   ```bash
   kaggle competitions download -c GiveMeSomeCredit -p data/raw/
   cd data/raw && unzip GiveMeSomeCredit.zip && rm GiveMeSomeCredit.zip
   ```

### Por que os arquivos não estão aqui

Os termos da competition são restritivos sobre **redistribuição**. Este
repo é público; commitar os CSVs cria zona cinzenta legal
(ver [OpenML entry](https://www.openml.org/d/45577) classificando como
"Public" mas a ToS oficial do Kaggle manda cada um baixar pela sua conta).

Escolha conservadora: você baixa na sua conta, aceita os termos na sua
conta, e o pipeline opera em cima do seu download. Zero ambiguidade.

## Como regenerar os arquivos derivados

Depois de ter `cs-training.csv` e `cs-test.csv` em `data/raw/`:

```bash
source .venv/bin/activate
python pipeline/flow.py
```

Isso gera:
- `data/raw/bureau_api.json` (~730 KB) — dados fake de bureau via Faker
- `data/staging/credit_applications.parquet` (~3 MB) — staging limpo
- `data/marts/mart_credit_features.parquet` (~4 MB) — mart com features
- `data/monitoring/metrics_history.jsonl` — uma linha nova por execução

Idempotente: rodar N vezes produz N linhas no JSONL de monitoring, mas
os Parquets são sobrescritos com o mesmo conteúdo (determinístico com o
mesmo input).

## Sobre PII e ética de dados

O dataset Kaggle é **anonimizado** — features são agregadas numéricas,
não há nome, CPF, endereço, CEP ou qualquer identificador pessoal. A
coluna índice é um número sequencial, não um ID real de tomador.

Para o objetivo pedagógico, isso é suficiente. Num projeto real com dado
pessoal (PF ou PJ), seriam necessárias camadas extras: tokenização,
políticas LGPD, auditoria de acesso, acordos de compartilhamento.
