# CHANGELOG

## [1] - PRD, PLAN, repo init
- What changed: created PRD.md, PLAN.md, .gitignore; `git init` inside D:/Jay/TechAhir (parent D:/Jay is an unrelated repo, so this is a nested repo).
- Why: steps 1-3 of the brief. Docs and API key were missing, so assumptions are recorded in PRD.md. DESIGN.md skipped (no UI/API).
- How to verify: `cat PRD.md PLAN.md`
- Result: files exist.

## [2] - Synthetic docs and model backends
- What changed: created `src/docs.py` (300 seeded docs with gold, plus a dev set) and `src/models.py` (SimLLM, AnthropicLLM).
- Why: docs and API key were not supplied (PRD assumptions 1-2). Sim error rates were fixed up front: cheap 15% base error, expensive 2%, scaled by hidden doc difficulty; half of errors are "distractor" values already in the text.
- How to verify: `python -c "from src.docs import generate; print(generate(1,42)[0][0].text)"`
- Result: generates invoice/contract/email text; gold is never exposed to the router.

## [3] - Router, verifier, runner
- What changed: `src/router.py` (verifier, risk, budget-capped escalation, calibration, virtual scheduler) and `src/run.py` (CLI + report).
- Why: PLAN.md approach. Bug found and fixed during build: the first version had a meaningless `risk <= 0.5*0` stop condition (risk is never 0 because of the confidence term); replaced with "stop when every field passes checks". Dev set raised from 40 to 100 docs because the priors were noisy.
- How to verify: `python -m src.run`
- Result (seed 42, sim): cost 1800/1800, 75 escalated, measured accuracy 95.2%, expected 94.1%, sim time 60 s, all-cheap 87.3%. Budget sweep: 300->87.3%, 900->91.5%, 1200->92.8%, 1800->95.2%, 3000->98.4% (cost 2820).

## [4] - Tests
- What changed: `tests/test_router.py` with 6 tests (determinism, verifier, budget cap and zero budget, escalation helps, failed expensive call falls back, scheduler).
- How to verify: `python -m pytest -q`
- Result: 6 passed.

## [5] - Security and cleanup pass
- Checked: no hardcoded secrets (grep for key patterns found none); API key only from `ANTHROPIC_API_KEY` and a missing key exits cleanly; model JSON is parsed inside try/retry and values coerced to str; doc text truncated to 20k chars before sending; no doc content logged; output paths fixed (`out/`, git-ignored); only dependency is pytest (anthropic optional). No dead code remained after the fix in [3].
- Result: no issues needing changes. Not done: `pip-audit` was not run.

## [6] - README
- What changed: README.md with design note, results and assumptions. DESIGN.md skipped (no UI/API). Nothing skipped for time except pip-audit.

## [7] - Real data changes the plan (replaces [2]-[6] design)
- What changed: deleted synthetic generator, simulated models and old tests. Added `src/rules.py` (free parser with arithmetic checks), `src/llm.py` (Groq + Mercury client with token-aware rate limiter), rewrote `src/router.py` and `src/run.py`, new tests. PRD.md, PLAN.md, README.md rewritten.
- Why: real documents arrived (`resources/candidate`): budget 2,100, 5-field schema, OCR noise, email threads with decoy amounts, no answer key.
- Decisions: Gemini dropped (Pro quota 0, Flash 404/503/timeouts). Groq `gpt-oss-20b` as cheap was throttled at 8,000 tokens/min (first full run hit the 540 s cutoff with 74 of ~121 cheap calls done) and mislabelled a thread email, so cheap = `mercury-3`, expensive = `gpt-oss-120b`.
- Bugs found and fixed: (a) regex backreference corrupted by shell escaping; (b) OCR decimal comma `123,000,00` parsed as 12,300,000; (c) `snap_names` merged LLC/Inc variants and changed 23 counterparties wrongly, found by checking outputs against the text; now legal-suffix aware; (d) no-op stop condition from the old router.
- How to verify: `python -m pytest -q` (14 pass); `python -m src.run`.
- Result: 817 units, 126 s, 279/300 docs confirmed by two sources, rules-vs-cheap agreement 99.9%. Accuracy is estimated (no key); grounding check passed for all amounts, references and types; 15-doc hand audit and 26 arbitrated docs correct.

## [8] - Security and wrap-up
- Keys only from environment or git-ignored `.env`; never printed. Model JSON validated by `normalise`. Doc text truncated to 6,000 chars, not logged. Not run: pip-audit. Vercel deploy skipped (batch CLI, no UI/API; no Vercel tool available in session).

## [9] - Repo restructure
- What changed: `resources/candidate/*` -> `data/` (documents.jsonl, TASK_RULES.txt, problem-statement.pdf); `output.jsonl`, `report.json` -> `results/`; PRD.md, PLAN.md -> `docs/`. Default paths in `src/run.py` and the corpus test updated; README links and layout section updated.
- Why: clearer structure (input / code / results / docs).
- How to verify: `python -m pytest -q` and `python -m src.run` (writes `results/`).
- Result: see below. Vercel: not connected (no CLI, no tool, no GitHub deployments or webhooks found); not deployed, since this is a batch CLI.
