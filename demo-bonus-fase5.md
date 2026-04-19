# demo-bonus-fase5 — runbook do explicável v2 (modelo ML + SHAP)

Roteiro para demonstrar a **comparação side-by-side v1 (rule) vs v2 (ml)**
do endpoint de explicabilidade. O ponto alto é mostrar que o mesmo
tomador recebe narrativas diferentes (e mais principiadas) quando o LLM
narra SHAP em vez de desvio-vs-mediana.

Cenários de uso — iguais ao v1:

- Validação pessoal: o modelo foi retreinado? As narrativas ainda fazem
  sentido?
- Mostrar a alguém interessado em IA aplicada a domínios regulados.
- Portfólio como "case de LLM narrando modelo ML com guardrails".
- Entrevista técnica que puxar para ML + explicabilidade.

> Pré-requisito: `demo-bonus-fase4.md` já ensaiado. O impacto deste
> roteiro depende do contraste — se a audiência nunca viu o v1, algumas
> frases perdem o peso ("reparem como a narrativa mudou").

---

## Setup (60s antes de apresentar)

```bash
./scripts/demo_bonus5_warmup.sh
# Ou com ids específicos:
#   ID_APROVADO=1 ID_LIMITE=23 ID_NEGADO=171 ./scripts/demo_bonus5_warmup.sh
```

Pré-aquece 6 combinações (3 ids × 2 endpoints) + abre no editor:
`reports/eval_explainer_rule_*.json`, `reports/eval_explainer_ml_*.json`,
`reports/model_metrics.json`. 3 artefatos, 3 janelas = 3 momentos da demo.

---

## Roteiro (5 min, 3 beats)

### Beat 1 — Mesmo tomador, duas narrativas (90s)

- Tab ativa: **Swagger**. Expanda ambos `/explain-decision/rule/{id}` e
  `/explain-decision/ml/{id}`.
- Chame `/rule/23380` → Execute. Aponta `decision: "NEGADO"`, 3 fatores
  com "desvio vs mediana", narrativa diz "foi negado porque utilização
  100%, renda R$ 4.000".
- Logo abaixo, chame `/ml/23380` → Execute. Aponta `decision:
  "APROVADO_COM_LIMITE"`, `pred_default_prob: 0.36`, 3 fatores com SHAP,
  narrativa diz "o modelo estima 36% de probabilidade de inadimplência"
  com linguagem diferente.
- Fala: "Mesmo tomador, dois sistemas, duas decisões diferentes. A
  regra SQL negou porque viu `util == 1.0`; o modelo treinado em 144k
  casos históricos disse 'é risco médio, aprova com limite'. **Esse é
  o valor de substituir regra por ML**: a regra é conservadora demais
  nesse caso."

### Beat 2 — A mecânica que faz a v2 confiável (90s)

- Tab ativa: **VS Code com `src/decision_explainer_ml.py` aberto**.
- Aponta `_shap_values_for_row` e `extract_context_ml`.
- Fala: "O LLM não vê o mart inteiro e não vê o modelo — vê 3 tuplas
  `(feature, value, shap_value)` extraídas deterministicamente. A função
  que escolhe quais 3 mostrar NÃO é heurística: é ordenação por
  magnitude absoluta de SHAP values — a contribuição real daquela
  feature pra probabilidade desse tomador específico. É esse o ganho
  da v2 sobre a v1."
- Aponta a lista `DECISION_BY_PROB` no topo. "Decisão vem de
  threshold na probabilidade calibrada — não de regra SQL. Com
  calibração isotonic (Fase 5), a prob significa frequência real."

### Beat 3 — Ponto alto: três JSONs abertos simultaneamente (2 min)

- Alterna pra **VS Code com 3 JSONs**:
  - `reports/model_metrics.json` — AUC XGB 0.857 vs baseline 0.764
    (+0.094). Fala: "O modelo ganhou 9.4 pontos de AUC sobre a regra
    SQL no test set. Isso justifica o esforço de treinar."
  - `reports/eval_explainer_rule_*.json` — `pass_rate_overall: 1.0`.
    Fala: "v1 com guardrails: zero alucinação numérica em 21 amostras."
  - `reports/eval_explainer_ml_*.json` — `pass_rate_overall: 1.0`,
    `cost_usd_total: ~0.004`. Fala: "v2 com os mesmos 3 checks —
    grounded, aligned, forbidden — passa em 100%. Custo 0.004 USD por
    eval de 21 amostras. **Gate de CI em ambos os endpoints**: se a
    taxa cair de 95%, o PR não passa."
- Linha de fechamento: "O arco completo é: Fase 5 treina, Bônus F5
  explica com SHAP, eval espelhado valida. Nenhuma parte confia em
  boa fé — tudo é número."

---

## Perguntas frequentes (específicas da v2)

**"Por que SHAP e não feature importance global?"**
Feature importance global do XGBoost diz "essas são as features mais
importantes no modelo em média". SHAP diz "essa feature, com esse
valor, empurrou a probabilidade desse tomador em +0.12". Para explicar
"por que **você** foi aprovado/negado", o global é inútil. É local ou
nada.

**"Por que a decisão muda de v1 pra v2 no mesmo tomador?"**
v1 usa `risk_tier` que vem de uma regra univariada (`util > 0.9 →
HIGH`). v2 usa a probabilidade calibrada de um modelo que aprendeu
interações entre todas as 11 features. São motores de decisão
diferentes — a divergência é esperada e pedagogicamente rica.

**"Como você sabe que o modelo tá correto, não só o rule?"**
Treino em 115k linhas do Kaggle GiveMeSomeCredit (label `defaulted`
real), test em 29k linhas estratificadas. AUC 0.857 no test é
reprodutível — `reports/model_metrics.json` tem o número e o git SHA
do commit que treinou.

**"Como o Bônus F5 garantiria consistência em retreino?"**
Feature validation em `extract_context_ml::_validate_features`: se o
mart perdeu uma feature que o modelo espera, o endpoint retorna 500 em
vez de usar reordenação aleatória. Retreino é explícito — versão no
GCS é `model-<git-sha>.pkl` + alias `latest`.
