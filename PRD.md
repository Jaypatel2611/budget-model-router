# PRD - Model Router Under a Budget

## Problem
Extract key fields from 300 business documents (invoices, contracts, emails) using two LLMs: a cheap/fast/error-prone one and an expensive/accurate/slow one. One expensive call costs 20x one cheap call. Expensive-only breaks budget and deadline; cheap-only is too inaccurate. Build a router that picks a model per document and reports expected accuracy, cost and time.

## Goals
- Process all 300 docs; >= 92% of fields correct; cost within budget; < 10 min total.
- Report expected accuracy (estimated without gold), measured accuracy (against gold), cost, time, escalation rate.
- Backend-agnostic: swap models without touching routing logic.

## Non-goals
UI/API, OCR of scans, fine-tuning, human review loop, multilingual docs.

## MVP scope
Cascade router: cheap model on all docs -> text-only verifier scores risk -> riskiest docs escalate to expensive model until budget is spent -> report.

## Inputs / outputs
In: 300 docs (`id`, `kind`, `text`). Out: `out/results.jsonl` (per-doc fields, model used, risk) and `out/report.json` + printed summary.
Fields: invoice (invoice_no, date, vendor, total, currency); contract (party_a, effective_date, term_months, governing_law, value); email (sender, date, subject, deadline, amount).

## Edge cases
Missing/ungrounded values, model returns bad JSON, distractor dates/amounts in text, API errors (retry then fall back to cheap result), zero budget, budget exhausted mid-run.

## Success metrics
Field accuracy >= 92%; cost <= budget; wall time < 10 min; |expected - measured accuracy| small.

## Assumptions (ambiguity flagged, not invented as requirements)
1. **Documents were not supplied** -> 300 seeded synthetic docs with gold labels generated (`src/docs.py`); 40 separate dev docs used only for calibration.
2. **No API key available** -> default backend is a deterministic *simulated* cheap/expensive model with modelled error rates and latency. Accuracy numbers are therefore properties of the simulation, not of real LLMs. A real Anthropic backend exists but is untested here.
3. **Budget not given** -> 1,500 cost units (cheap=1, expensive=20; all-expensive = 6,000; avg 5 units/doc), configurable.
4. "Accuracy" = fraction of individual fields exactly correct after normalisation.
5. Time is simulated latency on a 16-worker pool (cheap 0.6s, expensive 8s per call), plus real wall time.

## Open questions
Real budget figure? Real documents/field schema? Is partial-field escalation allowed (would cut cost further)? Rate limits of the real provider?
