# budget-model-router

Routes 300 real business documents (invoices, contracts, emails) between a free rules parser, a **cheap** LLM (1 unit) and an **expensive** LLM (20 units) under a 2,100-unit budget and a 10-minute limit. Output: `results/output.jsonl` (spec format) and `results/report.json`.

## Models picked and why
- **Cheap: `mercury-3`** (Inception Labs diffusion LLM). Very fast, no throttling in testing (40 calls in 8 s). It also got a thread email right where Groq `gpt-oss-20b` did not.
- **Expensive: `openai/gpt-oss-120b`** on Groq. Larger and more accurate. Free tier allows about 10 calls a minute, which is enough for the 27 arbitrations.

## Approach
1. **Rules (free, `src/rules.py`)** parse every document and self-check (invoice subtotal + tax = total; instalments x count = total; PO appears twice in emails). Handles OCR noise (`Ju1y`, `123,000,00`, `ond`). Verifies 278 of 300.
2. **Cheap model cross-checks** every document the rules verified or partly parsed (1 unit each, independent second opinion).
3. **Expensive model arbitrates** documents the rules could not verify (22 damaged scans, sent straight to it) and any rules-vs-cheap disagreement. Budget is enforced by a ledger; failed calls are refunded (not charged).
4. **Final value = majority vote** (expensive wins ties). Company names are snapped to the corpus spelling when only an OCR slip differs; names that differ in legal suffix (LLC vs Inc) are kept distinct. A rare misspelled word (e.g. "Vontage") is also snapped to a common word one OCR slip away ("Vantage").
5. Quoted email history is stripped before LLM calls (decoy amounts, fewer tokens).

## Run
```
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements-dev.txt
# .env (git-ignored) needs MERCURY_API_KEY and GROQ_API_KEY
python -m src.run          # writes results/output.jsonl and results/report.json
python -m pytest -q        # 14 offline tests, no network
python scripts/export_site.py   # refresh the static site data in public/
```

## Results (real run on the 300 documents, see `results/report.json`)
| | value |
|---|---|
| Units spent | 817 of 2,100 (277 cheap + 27 expensive calls) |
| Time, first to last call | 126 s (limit 600 s) |
| Documents confirmed by two sources | 279 of 300 |
| Rules vs cheap agreement | 99.9% of fields |
| Expected accuracy | ~97.4% (see caveat) |

**Accuracy caveat:** no answer key was provided, so accuracy is *estimated*: fields confirmed by two independent sources are assumed 98% right, others lower. Independent checks I ran: every amount, reference and doc type is grounded in its document; a 15-document hand audit and the 26 arbitrated documents were all correct. A bug found this way (merging LLC/Inc names) was fixed.

## Design note: 5M documents / month
- **Rules first, models second.** Regular layouts are parsed for free; models only cross-check and arbitrate. Cost scales with ambiguity, not volume.
- **Per-document escalation threshold**, adjusted by a controller so monthly spend tracks budget; the ledger here becomes a rolling budget.
- **Models are config** (endpoint, key, cost, rate limit in `PROVIDERS`). A price or model change is a one-line edit.
- **Continuous calibration:** send ~1% of traffic to the expensive model or a human as a gold sample; alert when estimated and measured accuracy drift.
- **Throughput:** per-model token-aware rate limiter, retries with backoff, cheap and expensive lanes run in parallel, idempotent per-document results.
- **Safety:** shadow-test new models, keep the old as fallback, never log document text.

## Assumptions and limitations
- Date = invoice date / contract "entered into" date / email Date header. Total = total due / total contract value / final agreed figure. Counterparty = the company that is not Meridian Works Ltd. Reference = invoice no / agreement no / PO. **Ambiguous in the spec**; contract date is the largest risk.
- Currency is dropped (output is a number). Rules are tuned to this corpus's layouts; other layouts fall to the LLMs.
- D-152 keeps an OCR-corrupted name (no clean variant exists in the corpus).
- Not deployed to Vercel: this is a batch CLI with no UI or API.

Links: [PRD](docs/PRD.md) | [PLAN](docs/PLAN.md) | [CHANGELOG.md](CHANGELOG.md)

## Live demo
A static results page (`public/index.html`) reads `public/report.json` and `public/output.jsonl` and shows the key metrics, run details and a searchable per-document table. No build step, no framework. **Live URL: https://budget-model-router.vercel.app/**

Preview locally: `python -m http.server -d public` then open http://localhost:8000.

Deploy to Vercel:
1. After any new run, refresh the site data: `python scripts/export_site.py`, then commit.
2. In Vercel: Add New > Project > import `Jaypatel2611/budget-model-router`.
3. Leave Framework Preset as "Other"; `vercel.json` sets no framework, no build or install command, and `outputDirectory` to `public`. If Vercel still reports a Python entrypoint error, set Settings > General > Root Directory to `public` and redeploy.

Note: the dependency file is named `requirements-dev.txt` on purpose. A `requirements.txt` in the repo root makes Vercel treat the project as Python and fail with `PYTHON_ENTRYPOINT_NOT_FOUND`.
4. Deploy. Every push to `main` redeploys.

## Repo layout
```
src/       rules.py (free parser), llm.py (Groq + Mercury client), router.py (tiers, voting, budget), run.py (CLI)
tests/     offline tests
data/      documents.jsonl (input), TASK_RULES.txt, problem-statement.pdf
results/   output.jsonl (deliverable), report.json (cost, time, accuracy estimate)
docs/      PRD.md, PLAN.md
public/    static results page (index.html) + exported report.json, output.jsonl
scripts/   export_site.py (copies results/ into public/)
vercel.json  static deploy config
CHANGELOG.md  README.md  requirements-dev.txt
```
