# budget-model-router

Route 300 business documents (invoices, contracts, emails) between a **cheap** LLM (1 cost unit) and an **expensive** LLM (20 units) so that 92%+ of extracted fields are correct, inside a cost budget and in under 10 minutes.

> **Read this first: what is real and what is simulated.**
> The 300 documents were not supplied and no LLM API key was available. So (1) the documents are **synthetic** (seeded, with gold labels) and (2) the default models are a **deterministic simulation** of a cheap (~87% field accuracy) and an expensive (~98%) model. The accuracy numbers below measure the *router* against that simulation, **not** real LLM quality. A real Anthropic backend (`--backend anthropic`) is implemented but **untested** (no key). See the assumptions in [PRD.md](PRD.md).

## Approach
1. **Cheap model on every document** (cost 1 each).
2. **Verifier (text only, no gold):** per field, is the value present in the text, is the format valid, and does it sit on the same line as its cue word (`Issue date:`, `Total`, ...). The model's own confidence is added. The result is a risk score per doc.
3. **Budget-capped escalation:** sort docs by risk and send the riskiest to the expensive model while `spent + 20 <= budget`. Docs whose fields all pass are never escalated. An escalated doc costs 1 + 20 (the cheap attempt is paid too). If the expensive call fails, the cheap answer is kept.
4. **Expected accuracy** is computed *before* looking at gold, from priors measured on a separate 100-doc dev set (cheap accuracy on fields that pass or fail the verifier; expensive accuracy). Measured accuracy vs gold is reported next to it.

Why: spend is known exactly before the expensive pass, so the budget is a hard guarantee, and money goes where the cheap model is likeliest wrong.

## Run
```
pip install -r requirements.txt
python -m src.run                      # sim backend, budget 1800 units, seed 42
python -m src.run --budget 1200        # tighter budget
python -m pytest -q                    # 6 tests
# real models (untested): pip install anthropic; set ANTHROPIC_API_KEY; python -m src.run --backend anthropic
```
Outputs: `out/results.jsonl` (per doc: model used, fields, risk) and `out/report.json`.

## Results (real output of `python -m src.run`, seed 42, simulated models)
| | cost (units) | field accuracy | sim time |
|---|---|---|---|
| all cheap | 300 | 87.3% | n/a |
| all expensive | 6,000 (over budget) | not run (sim error rate is ~2%) | n/a |
| **router, budget 1800** | **1,800** | **95.2%** (expected 94.1%) | **60 s** (75 docs escalated) |

Budget sweep (same data): 300 -> 87.3% | 900 -> 91.5% | **1200 -> 92.8%** | 1800 -> 95.2% | 3000 -> 98.4% (spent 2,820). The smallest budget meeting 92% here is about 1,200 units. Expected accuracy tracked measured accuracy within ~1 point (slightly pessimistic).
Time is simulated latency (cheap ~0.6 s, expensive ~8 s per call) on 16 workers. Real wall time of the simulation is ~0.02 s.

## Design note: 5M documents / month, with prices and quality changing
- **Streaming threshold, not batch ranking.** At 5M docs (~2/s) escalate when `risk > t`. A controller adjusts `t` hourly so spend tracks the monthly budget. The batch router here is the same logic with a known queue.
- **Models are config, not code.** Each model is (backend, cost, latency, priors). A price or model change is a config edit; the router only sees `cost` and `extract()`.
- **Continuous calibration.** Send ~0.5-1% of traffic to the expensive model (or humans) as a gold sample. Re-estimate priors and verifier precision per doc type weekly and on every model or price change. Alert if expected-vs-measured drift exceeds ~2 points.
- **Cheap tricks first.** Cache identical and near-duplicate docs, escalate only the failing fields (shorter prompt) instead of the whole doc, and add a mid-tier model so the cascade is cheap -> mid -> expensive.
- **Throughput and reliability.** Queue plus worker pool with rate-limit-aware backoff, idempotent per-doc results, retries then fallback to the cheap answer, per-tenant spend caps, and no doc text in logs.
- **Safety net.** Shadow-test any new model on the dev set before routing traffic, and keep the old one as fallback.

## Assumptions and limitations
- Synthetic, clean, English docs with label-style text. Real scans and PDFs would weaken the verifier (needs OCR and more checks). The verifier had no false positives on dev data, which is optimistic.
- The budget (1,800 units) is my assumption. The simulation error rates are my choice and were fixed before the first run, not tuned to hit the target.
- Dev-set priors are noisy (e.g. "flagged field accuracy" = 0.0 from 100 docs).
- Anthropic backend: untested; model IDs may need updating; one overall confidence per doc.

## Next steps
Run on real documents with a real key; field-level escalation; a mid-tier model; a learned risk model (logistic regression on verifier features); confidence calibration.

Links: [PRD.md](PRD.md) | [PLAN.md](PLAN.md) | [CHANGELOG.md](CHANGELOG.md)
