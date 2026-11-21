# PLAN (revised after real data arrived; see CHANGELOG [7])

## Approach
Three tiers. (1) Free rules parser with arithmetic self-checks. (2) Cheap LLM (`mercury-3`) cross-checks documents. (3) Expensive LLM (`gpt-oss-120b`) arbitrates documents the rules cannot verify or where sources disagree. Majority vote per field. Ledger enforces the 2,100-unit budget; failed calls are refunded.

## Alternative considered
Cheap LLM on everything, then escalate by confidence (the original plan). Rejected: LLM confidence is unreliable, and rules give a free independent check.

## Stack
Python 3.12, stdlib only (urllib) plus pytest. Groq and Mercury via OpenAI-compatible HTTP.

## Structure
`src/rules.py` | `src/llm.py` | `src/router.py` | `src/run.py` | `tests/` | `output.jsonl`, `report.json`

## Risks
Groq 8,000 tokens/min limit (handled by limiter); Gemini unusable on free tier; no answer key (accuracy is estimated); spec ambiguity on which date/total.

## Definition of done
output.jsonl for 300 docs, units <= 2,100, time < 10 min, tests pass, README with design note, pushed.
