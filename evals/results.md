# AI evaluation results

Model: `gemini-flash-lite-latest`. Run: 2026-10-06 16:17. Cases: 8.

- Intent accuracy: **8/8**
- Decision accuracy: **8/8** (what matters: the action the system takes)

| Case | Expected intent | Got | Expected decision | Got | OK | Detail |
|---|---|---|---|---|---|---|
| es_interested_meeting | interested | interested | HANDOFF | HANDOFF | yes | conf=1.0 lang=es evidence="nos interesa" |
| pt_interested_meeting | interested | interested | HANDOFF | HANDOFF | yes | conf=1.0 lang=pt evidence="Faz sentido para nós sim" |
| es_not_now | not_now | not_now | WAIT | WAIT | yes | conf=0.95 lang=es evidence="retomemos en febrero" |
| pt_referral | referral | referral | ENRICH | ENRICH | yes | conf=1.0 lang=pt evidence="Fala com a Fernanda Lopes, nossa controller: fernanda.lopes@grupoalfa.com.br" |
| es_question | question | question | HUMAN_REVIEW | HUMAN_REVIEW | yes | conf=1.0 lang=es evidence="¿La tarjeta funciona para pagar proveedores en dólares? ¿Y cuánto cuesta?" |
| pt_not_interested | not_interested | not_interested | SUPPRESS | SUPPRESS | yes | conf=0.95 lang=pt evidence="já usamos outra solução de cartão corporativo e estamos satisfeitos" |
| es_ambiguous | unclear | unclear | HUMAN_REVIEW | HUMAN_REVIEW | yes | conf=0.8 lang=es evidence="jaja puede ser, depende" |
| pt_declines_with_meeting_words | not_interested | not_interested | SUPPRESS | SUPPRESS | yes | conf=0.99 lang=pt evidence="não temos interesse no momento" |
