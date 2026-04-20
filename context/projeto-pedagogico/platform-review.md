# Revisão de plataforma — HTML artesanal vs. alternativas

Análise da estrutura atual do guia pedagógico contra alternativas
consolidadas (fast.ai / Jupyter, MkDocs Material, Quarto, etc). O
objetivo duplo é: **ensinar melhor** (top-down, aprender fazendo) e
**reduzir atrito de manutenção com LLM** (menos HTML, mais markdown).

---

## 1. Estado atual — o que a gente tem

9 arquivos totalizando ~7.500 linhas em `context/projeto-pedagogico/`:

| Arquivo | Linhas | Papel |
|---|---:|---|
| `index.html` | 352 | Hub com cards, estatísticas, pitch |
| `fase-1.html` | 594 | Ingestão + validação |
| `fase-2.html` | 616 | SQL + DuckDB |
| `fase-3.html` | 531 | Prefect + FastAPI + Docker |
| `fase-4.html` | 805 | Observabilidade + GCP + CI/CD |
| `fase-5.html` | 311 | Modelagem ML + benchmark |
| `bonus-fase4.html` | 561 | LLM narra regra SQL (v1) |
| `bonus-fase5.html` | 410 | LLM narra modelo ML (v2) |
| `docs.html` | 1930 | Cheat sheet técnica |
| `style.css` | 464 | Tema shared |
| `shared.js` | 292 | Progress tracker + toggles |

**Padrões recorrentes em cada fase:**
- Topbar de navegação (replicada 7x literalmente)
- `phase-header` com pergunta-guia
- Cards de desafio com IO badges, tags (`tag-build`, `tag-criteria`, `tag-expected`), `<details>` com referência
- Blocos de Active Recall (fill-in-blank com JS valida localStorage)
- `variations` + `blank-test`
- `page-nav` no rodapé

### Pontos fortes da estrutura atual
- **Zero build step** — abre direto no navegador
- **Zero dependência de framework** — só HTML + CSS + JS vanilla
- **Funciona offline** após primeira carga (exceto Prism.js via CDN)
- **Progress tracker via localStorage** — persistência trivial
- **Progressive disclosure via `<details>`** — nativo do browser
- **Active recall embarcado** — fill-in-blanks com feedback JS
- **Alta customização visual** — estilo próprio, não de template
- **Copy-paste amigável** — o aluno copia código do HTML direto

### Pontos frágeis (especialmente pra manutenção com LLM)
- **Arquivos grandes** — `fase-4.html` com 805 linhas. Edits cirúrgicos via LLM têm alta chance de quebrar algo distante.
- **Duplicação massiva de nav** — mudança na ordem/renome de fase = 7 arquivos editados (vimos isso acontecer várias vezes nesta sessão).
- **Mistura HTML + strings em PT-BR + snippets Python** — grep/edit fica barulhento. LLM Edit com `old_string` em português longo é propenso a erro.
- **CSS global crescendo** — classes específicas por uso (ex: `.bonus-banner`, `.why-matters`, `.phase-flow`) acumulam sem organização clara.
- **Prism.js via CDN sem pin** — versão pode mudar sem aviso, tema pode desalinhar.
- **Code snippets são strings HTML-escaped** — colar um bloco Python no HTML exige escapar `<`, `>`, aspas. Hostil pra edição rápida.
- **Sem fonte única da verdade** — o mesmo código aparece em `fase-4.html` + no repo real (`src/logger.py`). Se um muda, o outro não acompanha automaticamente.
- **Active recall fill-in-blank vira ossuário** — HTML com `<input data-answer="...">` dentro de `<pre>` é frágil: qualquer re-ordenação de linhas quebra.

---

## 2. fast.ai — o benchmark pedagógico

fast.ai (Jeremy Howard + Sylvain Gugger) é a referência mais citada em
ensino técnico moderno que prioriza "aprender fazendo". A metodologia
tem 3 pilares:

### Pilar 1: Top-down teaching

> "Start by showing how to use a complete, working, state-of-the-art deep
> learning network to solve real-world problems using simple, expressive
> tools, and then gradually dig deeper into understanding how those
> tools are made." — [course.fast.ai](https://course.fast.ai/)

Traduzido para nosso contexto: na lição 1, você **já treina um modelo
que funciona**. Só na lição 5 você abre o que é `nn.Linear`, e na 10
deriva backprop. O oposto do currículo tradicional (teoria → prática).

### Pilar 2: Jupyter Notebook como formato primário

- Cada capítulo = 1 notebook = código executável intercalado com texto
- Todos os notebooks disponíveis gratuitamente no Kaggle e Colab
- "You can also execute all the code in the book yourself"
- Livro impresso é **renderização** dos mesmos notebooks — não há divergência

### Pilar 3: "You can always go deeper later"

Filosofia: é OK não entender tudo na primeira passada. Matemática e
internals aparecem **depois** do aluno já ter confiança de que sabe
fazer. Contrasta com currículos que exigem pré-requisitos absolutos
antes de começar.

**Por que isso funciona** (evidência citada por eles): estudos em
educação mostram que adultos aprendem melhor quando o **contexto de
aplicação** precede a teoria. "Eu preciso disso pra resolver X" é mais
motivador que "estude isso agora, vai ser útil depois".

---

## 3. Comparação direta — atual vs. fast.ai

| Dimensão | Guia atual (HTML) | fast.ai (Jupyter + book) |
|---|---|---|
| Direção pedagógica | **Top-down-ish** — cada fase entrega algo funcional, variações aprofundam | Top-down explícito como filosofia |
| Formato | HTML estático + JS vanilla | Jupyter notebook executável |
| Interatividade | Fill-in-blank via input, progress tracker localStorage | Código rodável + output inline + exercises |
| Ensina fazendo? | Sim — cada desafio constrói código real | Sim — cada notebook roda modelo real |
| "Vai mais fundo depois" | Parcial — via `variations` + `melhorias-estruturais.md` | Central — capítulos posteriores aprofundam |
| Fonte única de verdade | Não — código no HTML e no repo divergem possível | Sim — mesmo código no notebook/livro/produção |
| LLM-friendly pra editar | Frágil — HTML grande, estrutura implícita | Médio — notebook JSON é editável mas verboso |
| Copy-paste pro aluno | Bom — `<pre><code>` direto | Excelente — célula inteira copiável |
| Hospedagem | Qualquer servidor estático | GitHub Pages / Colab / Kaggle |

**Conclusão do direto**: o guia atual **acerta** na filosofia top-down e
no "ensinar fazendo", mas **perde** em dois eixos: (a) o código não é
executável dentro do guia, (b) fonte da verdade é dupla (HTML + repo).

---

## 4. Alternativas de plataforma

### (A) Jupyter Notebooks puros (fast.ai-style)

Cada fase vira 1 notebook. Exemplo: `notebooks/fase-1-ingestao.ipynb`
com markdown explicativo + células de código que o aluno roda no Colab
ou localmente.

**Prós:**
- **Código executável dentro do conteúdo** — ganho pedagógico enorme
- Padrão universal em ML/Data — qualquer aluno de ciência de dados sabe abrir
- Fonte única — o notebook É o código de referência
- Renderiza bem em GitHub (github.com mostra .ipynb)
- Exportável pra HTML/PDF via `nbconvert` se quiser publicar estático depois

**Contras:**
- **Notebooks não combinam com arquitetura deste projeto.** Fase 3+ é
  sobre FastAPI + Docker + Cloud Run — não se roda app web em notebook.
  Forçar vira gambiarra.
- **Active recall / fill-in-blank não é ergonômico** em notebook.
- JSON verboso pra LLM editar — `%% notebook_metadata` atrapalha diff.
- Progress tracking em notebook é manual (não há localStorage).

**Verdict:** excelente pra Fases 1-2 e Fase 5 (puro Python/ML). Péssimo
pra Fases 3-4 + Bônus F4/F5 (serving + infra).

### (B) MkDocs Material

Static site generator: N arquivos markdown + 1 tema. Build gera HTML.

**Prós:**
- **LLM-friendly**: edita markdown puro, sem HTML tags
- **Topbar / nav gerado do filesystem** — renomear fase é 1 linha em `mkdocs.yml`
- Tema Material é polido, responsivo, dark mode built-in
- Plugins: quiz, mermaid, tabs, callouts, mathjax, search
- **Deploy gratuito no GitHub Pages** com 1 action
- Markdown renderiza em qualquer editor (VSCode preview, GitHub web)
- Code snippets via triplo-backtick — zero escapar

**Contras:**
- Build step (`mkdocs build`) — diferente de "abre HTML no browser"
- Active recall precisa plugin (`mkdocs-exercise-plugin` existe mas limitado)
- Customização visual pesada exige override de tema

**Verdict:** **ótima escolha pra manutenção com LLM e pedagogia geral**.
Perde em interatividade e em "código rodável na hora".

### (C) Quarto

Moderno, combina markdown + notebook, suporta "Thebe" pra rodar código
remotamente sem Jupyter local.

**Prós:**
- Aceita **tanto `.qmd` (markdown tipo Pandoc)** **quanto `.ipynb`** como source
- Gera livro-estilo com navegação, search, dark mode
- Integra código executável via Thebe/Binder
- LaTeX / matemática nativo

**Contras:**
- Stack Python + R (overhead de instalação)
- Menos popular = comunidade LLM-assist menor que MkDocs
- Thebe precisa de kernel remoto (Binder) que pode estar lento

**Verdict:** poderoso mas overhead pra projeto pedagógico pessoal.

### (D) Docusaurus / Nextra / Starlight

React/Vue-based static sites com MDX (markdown + JSX). Permite
componentes React embutidos no markdown.

**Prós:**
- Componentes custom (fill-in-blank, cards, carousels) sem CSS hackeado
- Search + versionamento de docs built-in
- Temas fortes

**Contras:**
- Stack React = maior surface pra LLM confundir-se com
- Overkill pra projeto pessoal

**Verdict:** poder alto, custo alto. Só faz sentido se virar projeto
aberto com múltiplos autores.

### (E) Obsidian / Logseq / Notion exportado

Markdown + graph + bi-directional linking. Ótimo pra **revisão** da
Redesenvolvimento.

**Prós:**
- Personal knowledge management — rede de conceitos
- Perfeito pra "após o Redesenvolvimento, anote onde travou"

**Contras:**
- Não é plataforma de **entrega**. É ferramenta de **estudo pessoal**.
- Exportação limitada — não substitui guia público

**Verdict:** **complementar**, não substituto. Pode coexistir: MkDocs
pra entrega, Obsidian pra anotações do aluno.

---

## 5. Recomendação concreta

### O diagnóstico

O guia atual foi **feito à mão sem framework** e isso entrega valor
hoje (estilo único, zero build step, funciona offline), mas gera **dois
problemas estruturais** que vão piorar com tempo:

1. **Divergência HTML ↔ repo** — o código em `fase-5.html:280` tem que
   ser mantido manualmente sincronizado com `src/train.py:55`. É uma
   dívida silenciosa que cresce a cada refactor.
2. **Atrito de edição com LLM** — arquivos de 600+ linhas misturando
   HTML/CSS/JS/Python-em-string forçam Edit cirúrgico com `old_string`
   longo em português. Vimos isso falhar nesta sessão (sed com
   `\*\.` não matching por incompatibilidade BRE).

### A proposta mínima

**Migrar pra MkDocs Material em uma Pass 3** (não agora). Conversão
consegue ser largamente automatizada:

- Cada fase vira `docs/fases/fase-N.md`
- Topbar vira `nav:` em `mkdocs.yml`
- Challenges viram seções markdown com admonitions (`!!! tip`, `!!! info`)
- `<details>` markdown nativo via `???`
- Code snippets com syntax highlighting automático via triplo-backtick
- `docs.html` vira `docs/cheatsheet.md`
- Progress tracker — **remove ou migra pra plugin**; não é essencial

**O que o Redesenvolvimento manual ganha com isso:** quando o aluno (você mesmo)
estiver reimplementando, editar notas num markdown é trivial. Editar
HTML grande é fricção.

### A proposta híbrida (se quiser o melhor dos mundos)

- **MkDocs Material** como plataforma do **guia** (fases, desafios, docs)
- **Jupyter Notebooks opcionais** pra Fases 1-2 e Fase 5 (pure Python/ML)
  — um `notebooks/fase-1-exploratoria.ipynb` pro aluno rodar no Colab
  antes de entrar na implementação modular
- **Código em `src/` continua fonte da verdade** — markdown do guia usa
  `{{ include "src/train.py:40-60" }}` (plugin `mkdocs-include-plugin`)
  pra puxar snippets do próprio código. Divergência deixa de existir.

### O que NÃO recomendo

- **Reescrever o HTML atual** seguindo "padrão melhor" — o estilo custa
  mais que migrar pra framework.
- **Adotar Docusaurus/Nextra** — stack JS é overhead pra projeto pessoal.
- **Obsidian como plataforma pública** — não foi feito pra isso.

### Quando fazer isso

- **Não agora** — o projeto tem 2 entregas abertas (T.7, T.8 itens
  médios, T.9 itens médios). Terminar essas primeiro.
- **Durante ou após o Redesenvolvimento** — quando você estiver reimplementando,
  você já vai estar editando o guia pra corrigir onde o currículo foi
  confuso. Nesse momento, migrar o formato vale mais.

---

## 6. Para o "aprender fazendo primeiro" estilo fast.ai

Independente de plataforma, 3 ajustes pedagógicos que o guia atual pode
receber **sem trocar tech**:

### (a) Cada fase começa com um "Resultado em 10 minutos"

Antes dos desafios detalhados, a fase mostra o **output completo**
— a API rodando, o modelo treinado, o endpoint respondendo — com código
mínimo e "não entende isso ainda? ok, nas próximas 2h você vai
entender". Isso é a cara do fast.ai.

Exemplo pra Fase 5:

> ## O que você vai ter em 10 minutos
> ```bash
> pip install xgboost scikit-learn
> python -c "
> import pandas as pd; from xgboost import XGBClassifier
> df = pd.read_parquet('data/marts/mart_credit_features.parquet')
> X = df.drop(columns=['applicant_id','defaulted','risk_tier'])
> m = XGBClassifier(n_estimators=50); m.fit(X, df['defaulted'])
> print('AUC 0.82+ — detalhes na sessão de treino')
> "
> ```
>
> Este snippet treina um modelo básico que supera a regra SQL da Fase
> 2. Os próximos 4 desafios vão desdobrar cada decisão (calibração,
> scale_pos_weight, feature engineering, versionamento).

### (b) Seção "O que cada desafio NÃO cobre" no final

Explicitar o gap, como o `melhorias-estruturais.md` já faz. Dá
honestidade + ganchos pro Redesenvolvimento aprofundado.

### (c) "Por que isso existe" antes do "Como construir"

Cada desafio hoje começa com 🎯 **O que construir**. Mover a justificativa
(o `connect-note`) pra antes disso. O aluno entende **por quê** antes de
digitar código.

---

## 7. Resumo executivo

| Pergunta | Resposta |
|---|---|
| A estrutura atual é boa pedagogicamente? | Sim nas intenções, parcial na execução. Top-down e active recall estão lá; "código executável inline" e "fonte única de verdade" faltam. |
| É boa pra manutenção com LLM? | **Não** — arquivos grandes, duplicação de nav, HTML+JS+PT-BR misturados. Frágil. |
| fast.ai faz melhor? | Em interatividade e "fonte única": sim. No estilo visual custom: não. |
| Migrar tudo agora? | **Não**. Terminar as dívidas abertas (T.7-T.9) primeiro. |
| Quando migrar? | Durante ou após o Redesenvolvimento, quando for natural re-trabalhar o guia. |
| Pra que formato? | **MkDocs Material** como guia principal + Jupyter Notebooks opcionais pra Fases 1-2/5. Código em `src/` continua fonte da verdade via plugin de include. |
| Ajustes pedagógicos sem trocar tech? | 3 quick wins: "resultado em 10 min" no topo de cada fase, "o que esta fase NÃO cobre" no fim, "por que existe" antes de "o que construir". |

### Fontes

- [Practical Deep Learning - fast.ai course](https://course.fast.ai/)
- [George Zhang: How to make the most of top-down fast.ai](https://medium.com/@georgezhang_33009/how-to-make-the-most-of-the-top-down-fast-ai-courses-ae70814c736f)
- [Rohit Bhattacharya: Why I Advocate fast.ai's Top-Down Approach](https://bhatta.io/2018/10/20/why-i-advocate-fast-ai-top-down-approach/)
- [fastai/fastbook on GitHub (todos os capítulos como Jupyter notebooks)](https://github.com/fastai/fastbook)
- [MkDocs Material](https://squidfunk.github.io/mkdocs-material/)
- [Quarto](https://quarto.org/)
