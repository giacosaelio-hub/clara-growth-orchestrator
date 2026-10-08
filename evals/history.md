# Evaluation history

| Run | Model | Decision accuracy | What happened |
|---|---|---|---|
| 1 | gemini-flash-lite-latest | 7/8 | The model returned `meeting_requested: "martes a las 11"` (text instead of true/false). Schema validation rejected it and the reply went to human review: the system stayed safe. Fix: explicit field types in the prompt, a separate `meeting_time` field, and the schema passed to Gemini as `response_schema`. |
| 2 | gemini-flash-lite-latest | 8/8 | All cases correct. Evidence quotes became short and precise. |
