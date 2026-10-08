"""AI evaluation suite: runs the reply cases against the real model and writes evals/results.md.

    py evals/run_evals.py
"""
import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from app.ai import GeminiLLM, interpret  # noqa: E402
from app.rules import decide_from_ai, decide_reply_pre_ai  # noqa: E402

ACCOUNT = {"is_customer": 0, "has_open_opportunity": 0, "assigned_ae": None, "do_not_contact": 0}


def main():
    cases = json.loads((ROOT / "evals" / "cases.json").read_text(encoding="utf-8"))
    llm = GeminiLLM()
    rows, ok_intent, ok_decision = [], 0, 0
    for c in cases:
        pre = decide_reply_pre_ai(ACCOUNT, None, c["text"])
        if pre:
            intent, decision, note = "(rule)", pre.kind, pre.rule
        else:
            ai, failure, raw = interpret(llm, c["text"])
            d = decide_from_ai(ai, failure)
            intent = ai.intent if ai else "(rejected)"
            decision = d.kind
            note = failure or f"conf={ai.confidence} lang={ai.language} evidence=\"{ai.evidence}\""
        hit_i, hit_d = intent == c["expected_intent"], decision == c["expected_decision"]
        ok_intent += hit_i
        ok_decision += hit_d
        rows.append((c["id"], c["expected_intent"], intent, c["expected_decision"], decision, hit_d, note))
        print(f"{'OK ' if hit_d else 'XX '} {c['id']:<32} intent {intent:<15} decision {decision:<13} {note[:70]}")
        time.sleep(4)  # stay under the free tier rate limit

    n = len(cases)
    md = [f"# AI evaluation results", "",
          f"Model: `{llm.model}`. Run: {datetime.now():%Y-%m-%d %H:%M}. Cases: {n}.", "",
          f"- Intent accuracy: **{ok_intent}/{n}**",
          f"- Decision accuracy: **{ok_decision}/{n}** (what matters: the action the system takes)", "",
          "| Case | Expected intent | Got | Expected decision | Got | OK | Detail |",
          "|---|---|---|---|---|---|---|"]
    for r in rows:
        md.append(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} | {'yes' if r[5] else 'NO'} | {r[6]} |")
    (ROOT / "evals" / "results.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"\nintent {ok_intent}/{n}  decision {ok_decision}/{n}  -> evals/results.md")


if __name__ == "__main__":
    main()
