# Decision log

## Something I deliberately did not build

**A full SDR platform, and an AI that writes the outreach emails.** The case asks for one meaningful
end-to-end flow. Personalized email generation looks impressive, but it adds risk (invented facts sent
to a real prospect) and it is a commodity that outreach tools already offer. I focused on the decision
layer: what to do with each account and whether it is safe to automate.

Also not built: multiple contacts per account in the demo flow (the schema supports it), a scheduler
for follow-ups (the date is stored, not executed) and a real CRM sync.

## Somewhere I deliberately did not use AI

**Everything with legal or business risk is decided by rules:** existing customers, accounts owned by an
AE, opt-outs, unsubscribe requests, prompt injection attempts, missing data and the ICP. These must be
exact and explainable. A model that is right 98% of the time would still email a customer who asked to
stop. The unsubscribe and injection checks run before the model ever sees the reply.

## The most important tradeoff

**Safety over automation rate.** Every doubtful case goes to human review: low confidence, an evidence
quote that does not appear in the reply, a contradictory output, an email domain that does not match the
company, a tax ID shared by two records. This means more manual work at the start. I chose it because the
cost of a wrong action (emailing a customer, handing a non-interested lead to an AE) is much higher than
the cost of a person looking at it. The thresholds are in `config/icp.json`, so the automation rate can
grow as the evaluation set grows.

## The biggest production risk I would address next

**Privacy and data handling.** The system sends prospects' replies to an external model and stores them in
the audit log. Before production: a data processing agreement with the model provider, masking of personal
data (phone numbers, signatures) before the model call, a retention policy for the audit log, and
compliance review for LGPD (Brazil), LFPDPPP (Mexico) and Law 1581 (Colombia).

## Other decisions

| Decision | Why |
|---|---|
| Python + SQLite instead of n8n | Testable business logic and a reproducible demo. n8n would fit as the integration layer in front of it. |
| Gemini free tier, `flash-lite` | Zero cost, structured output, large context. The `flash` model returned 503 under load in earlier projects. |
| Personal emails accepted | Many Latin American companies use Gmail or Hotmail. Blocking them would drop real prospects. |
| Size and industry never block | They come from enrichment and are often missing. They help prioritize, not exclude. |
| Duplicate company only within the same country | The same number can exist in two countries' tax systems and mean two different companies. |
| Companies outside Clara's markets are kept | They become a ready list if Clara expands (for example to Argentina). |
| Timestamps with time zone | Events from Mexico, Colombia and Brazil compare correctly. |
