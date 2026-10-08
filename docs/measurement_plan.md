# Measurement and experiment plan

## Goal

Not more emails or more replies. **Incremental qualified pipeline, without growing the SDR team at the
same pace.**

## Funnel

| Stage | Owner | Event |
|---|---|---|
| Targeted account | CRM | `account_targeted` |
| Contacted | System or SDR | first email sent |
| Replied | Prospect | `reply_received` |
| Qualified (SQL) | SDR | the system hands off, or the SDR qualifies |
| Accepted opportunity (SQO) | AE | the AE accepts the lead and opens an opportunity |
| Closed won | AE | deal won |

## Experiment

- **Design:** randomized holdout by account. Each month's target list is split at random, stratified by country and segment, so both groups look alike.
- **Treatment:** SDRs supported by the system (rules, reply interpretation, automatic handoff).
- **Control:** the current process.
- **Same SDRs, same period, same ICP.** The split is by account, not by SDR, so SDR skill does not bias the result.
- **Duration:** at least one full sales cycle for the SQO metric (around 60 days), with a weekly read of leading indicators.

## Primary metric

**AE-accepted opportunities (SQOs) per SDR per month, treatment minus control.**

It captures both halves of the goal: each SDR produces more, and the AE accepts what they receive.
More SQLs that AEs reject would not count.

## Secondary metrics

- pipeline value per SDR
- SQL to SQO acceptance rate
- accounts worked per SDR
- time from reply to first AE contact
- share of replies handled without human review
- cost per SQO

## Guardrails

If any of these worsens beyond its threshold, the system does not scale.

- AE rejection rate of handoffs
- unsubscribe and spam complaint rate
- email bounce rate
- SQO to closed won rate, checked later, so quantity never replaces quality

## Decision rule

Scale when the primary metric improves with statistical confidence and no guardrail worsens. If the
result is neutral, keep the system for the SDR time it saves and tune the thresholds. If a guardrail
breaks, roll back to human review for every reply (kill switch) and investigate.

## Instrumentation

Every decision is already in the audit log with its rule, the AI output and the model version. Joining
it with CRM opportunity data by `account_id` gives every metric above, per group.
