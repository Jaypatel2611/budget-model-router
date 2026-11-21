# PLAN

## Approach
Two-pass cascade with a risk-ranked, budget-capped escalation.
1. Cheap model on every doc (cost 1 each).
2. Verifier (text only, no gold): per field -> grounded in text? valid format? plus model self-confidence -> doc risk score.
3. Sort docs by risk desc; escalate to expensive model while remaining budget >= 20 and risk > 0; replace cheap answer.
4. Expected accuracy: per-field priors measured on a separate dev set (cheap acc when grounded / ungrounded, expensive acc). Measured accuracy vs gold reported alongside.
Why: exact budget control (we know spend before pass 2), escalation goes where the cheap model is likeliest wrong, simple to explain and tune.

## Alternative considered
Per-doc streaming threshold (escalate if risk > t). Simpler for 5M docs/month but cannot guarantee a fixed budget on a batch; kept as the production design (see README design note).

## Stack
Python 3.12, stdlib + pytest. Optional `anthropic` SDK for the real backend. No pandas/sklearn: nothing needs them.

## Structure
`src/docs.py` generator | `src/models.py` Sim + Anthropic backends | `src/router.py` verifier, router, calibration, scheduler | `src/run.py` CLI + report | `tests/` | `out/` (ignored)

## Tasks
1 docs generator -> 2 sim backend -> 3 verifier+router -> 4 run/report -> 5 tests -> 6 security pass -> 7 README -> 8 push.

## Risks
Sim is optimistic/rigged-looking (mitigate: separate dev set, report gap, label as simulation); real backend untested; budget assumption arbitrary (configurable).

## Definition of done
`python -m src.run` prints accuracy >= 92%, cost <= budget, time < 10 min; tests pass; README + CHANGELOG complete; pushed to GitHub.
DESIGN.md skipped: no UI or API.
