# PRD - Model Router Under a Budget

## Problem
Extract doc_type, date, total_amount, counterparty, reference from 300 business documents (`data/documents.jsonl`) using a cheap model (1 unit) and an expensive one (20 units). Budget 2,100 units, under 10 minutes, target 92% fields correct. Report accuracy expected, cost, time.

## Goals / non-goals
Goals: output.jsonl in the given format; budget and time respected; estimated accuracy reported. Non-goals: fine-tuning, a production API. A small static results page (`public/`) was added later for Vercel.

## Inputs / outputs
In: documents.jsonl (`id`, `text`; includes OCR-noisy scans and email threads with decoy quoted amounts). Out: `results/output.jsonl` (+ call counts per document), `results/report.json`, and a static page in `public/`.

## Edge cases
OCR typos and decimal commas, RE: threads with older quotes, near-identical company names with different legal suffixes, failed or rate-limited API calls (not charged, refunded), budget exhaustion.

## Success metrics
>= 92% fields correct (estimated; no answer key), units <= 2,100, time < 600 s.

## Assumptions (spec is ambiguous)
Date = invoice date / contract entered-into date / email Date. Total = total due / contract value / final agreed figure. Counterparty = non-Meridian company. Reference = invoice no / agreement no / PO. Currency dropped.

## Open questions
Is the contract date the signing date or the start date? Is there a hidden answer key to validate against?
