# DEMO_BONUS — Runbook do endpoint explicável (5 min)

Roteiro para demonstrar o endpoint `/explain-decision/{applicant_id}` —
o diferencial de LLM com guardrails em cima do pipeline. Use para:

- Validar que o explicador ainda está consistente depois de mexer no
  prompt, trocar de modelo ou regenerar o mart.
- Mostrar a alguém interessado em IA aplicada a domínios regulados
  (mentor, colaborador, amigo da área).
- Anexar em portfólio como "case de LLM em produção com eval".
- Entrevista técnica que puxar para IA/LLM/explicabilidade.

> Pré-requisito: `DEMO.md` da Fase 4 já ensaiado. Este runbook assume
> que o sistema base já foi demonstrado — aqui entra só o diferencial.

---

## Setup (60s antes de apresentar)

```bash
./scripts/demo_bonus_warmup.sh
# Ou com ids específicos:
#   ID_APROVADO=1 ID_LIMITE=23 ID_NEGADO=171 ./scripts/demo_bonus_warmup.sh
```

Pré-aquece o endpoint com 3 `applicant_id`s (um por tier) pra popular o
cache por chave. Abre Swagger, Actions e o último
`reports/eval_explainer_*.json` no VS Code (se `code` estiver no PATH).

**Antes da primeira demo pública:** rode `python scripts/eval_explainer.py
--n 30` uma vez, revise manualmente as narrativas do JSON de saída, e
escolha 3 ids cujas respostas você já aprovou. Use-os como
`ID_APROVADO` / `ID_LIMITE` / `ID_NEGADO`. Nunca digite um id "qualquer"
ao vivo — tier HIGH com dado estranho pode gerar narrativa que soa mal
na hora da demonstração.

---

## Roteiro (5 min, 3 beats)

### Beat 1 — Decisão APROVADA (60s)

- Tab ativa: **Swagger**.
- Clica `/explain-decision/{applicant_id}` → `1` (ou o `ID_APROVADO`) →
  Execute.
- Aponta no JSON:
  - `decision: "APROVADO"`, `risk_tier: "LOW"`.
  - `key_factors` com 3 entradas — cada uma traz `value`, `median`,
    `direction`.
  - `narrative` em PT-BR citando esses valores.
- Fala: "Decisão em segundos. Se um SaaS parceiro (imobiliária, edtech)
  vai montar a tela de aprovação ou negativa, essa `narrative` cumpre
  a Resolução 4.935/Bacen — o tomador tem direito de saber por quê."

### Beat 2 — Decisão NEGADA (90s)

- Swagger → `/explain-decision/171` (ou `$ID_NEGADO`) → Execute.
- Aponta:
  - `decision: "NEGADO"`, `risk_tier: "HIGH"`.
  - `key_factors`: ao menos 1 com `direction: alto_aumenta_risco`.
  - `narrative` cita os mesmos números da seção `key_factors` (aponta
    com o cursor: "`revolving_utilization: 0.95` aqui, `0,95` na
    narrativa — mesmo valor").
- Fala: "O LLM não escolhe quais features mencionar — o extrator
  determinístico em `src/decision_explainer.py` pega os 3 de maior
  desvio vs mediana da carteira, e passa pro prompt. O LLM só narra.
  Essa separação é o que faz o compliance aprovar."

### Beat 3 — Ponto alto: eval como gate de CI (2 min)

- Tab ativa: **VS Code com `reports/eval_explainer_*.json` aberto**.
- Aponta os campos na ordem:
  1. `pass_rate_grounded: 1.0` — "nenhuma alucinação numérica em 21
     amostras. O check é regex: todo número na `narrative` precisa
     existir nos `key_factors`, com tolerância de arredondamento."
  2. `pass_rate_aligned: 1.0` — "decisão bate com fatores. Se é NEGADO,
     pelo menos um fator de risco está no top-3."
  3. `pass_rate_forbidden: 1.0` — "nenhuma menção a CEP, raça, gênero,
     estado civil, religião."
  4. `cost_usd_total: ~0.004` — "0.2 centavos por decisão, Haiku 4.5."
  5. `latency_p95_ms: ~1800` — "sub 2 segundos p95, chamadas cacheadas
     voltam em <100ms."
- Fala: "Confiança em LLM em produção não vem de boa fé. Vem desse
  relatório. Ele roda como gate de CI — se `pass_rate_overall < 0.95`,
  o PR não passa. Essa é a diferença entre 'plugar um LLM' e 'colocar
  um LLM em produção regulada'."

---

## Perguntas frequentes

**"Como você sabe que o LLM não está inventando número?"**
Abre o eval report, aponta `pass_rate_grounded`. Check é programático:
regex acha todo número na narrativa, cada um precisa bater com algum
`value` ou `median` dos `key_factors` (tolerância de 0.05 absoluto ou
2% relativo pra arredondamento). 21 amostras, threshold 95%, gate de CI.

**"Quanto isso custa?"**
`cost_usd_total: ~0.004` para 21 decisões — **0.2 centavos por chamada**.
Haiku 4.5 em todos os tiers hoje; variação razoável seria Haiku para
LOW/MEDIUM e Sonnet só para HIGH (decisão de negativa é a mais
sensível legalmente). O campo `_usage` no response carrega
`input_tokens` e `output_tokens` — permite dashboard de custo por SaaS
parceiro se cobrar por chamada.

**"E se a Anthropic cair?"**
Hoje o endpoint retorna 503. Próximo passo é fallback: retornar
`decision` + `key_factors` sem `narrative` — o extrator determinístico
já é uma explicação estruturada, só perde o wrapping em PT-BR. SLA de
scoring não depende do LLM; só o texto depende.
