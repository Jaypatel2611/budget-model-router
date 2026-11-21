import json
import pathlib

from src.llm import normalise
from src.router import Ledger, route, same, vote
from src.rules import parse, parse_amt, parse_date, snap_names

INVOICE = """Halcyon Analytics Pvt Ltd
253 Canal Street

INVOICE

Invoice No: INV-2026-76795
Invoice Date: 30-Jun-2026
Due Date: 14 August 2026

Bill To:
Meridian Works Ltd

Subtotal: EUR 100.00
Tax: EUR 5.00
Total Due: EUR 105.00
"""
CONTRACT_OCR = """[scanned document, text recognised automatically]

SERVICE AGREEMENT
Agreement No, CTR-75494

This Service Agrecment (fhe "Agreernent") is entered into on Ju1y 3, 2026 between Meridian Works Ltd (the "C1ient") ond Maplestone Software Group (the "Provider").

3. Fees. The total contract valueis INR 123,000,00, payable in 2 instolments of INR 61,500,00 each.
"""
THREAD = """From: Sana Mirza <sana@skylark.example>
To: accounts@meridianworks.example
Date: Wed, 08 Apr 2026 18:38
Subject: RE: Replacement parts - PO-53317

Hi,

We can confirm the final agreed figure of EUR 132,700.00 and we have raised PO-53317.

Regards,
Sana Mirza
Skylark Engineering Group

On Mon, 06 Apr 2026 17:11, Tom <tom@meridianworks.example> wrote:
> Our budget for this is EUR 141,656.08 at most.
"""


def test_invoice_parses_and_passes_arithmetic_check():
    f, ok, _ = parse(INVOICE)
    assert ok and f == {"doc_type": "invoice", "date": "2026-06-30", "total_amount": 105.0,
                        "counterparty": "Halcyon Analytics Pvt Ltd", "reference": "INV-2026-76795"}


def test_ocr_contract_is_repaired():
    f, ok, flags = parse(CONTRACT_OCR)
    assert "scanned" in flags and ok
    assert f["date"] == "2026-07-03" and f["total_amount"] == 123000.0
    assert f["counterparty"] == "Maplestone Software Group" and f["reference"] == "CTR-75494"


def test_thread_ignores_quoted_amounts():
    f, _, flags = parse(THREAD)
    assert f["total_amount"] == 132700.0 and "thread" in flags
    assert f["counterparty"] == "Skylark Engineering Group" and f["reference"] == "PO-53317"


def test_unparseable_doc_fails_checks():
    assert parse("hello world")[1] is False


def test_parsers_and_snap():
    assert parse_date("Fri, 08 May 2026 11:23") == "2026-05-08" and parse_amt("1,241.30") == 1241.3
    names = snap_names([{"counterparty": "Summit Packaging Group"}] * 3 + [{"counterparty": "Summit Packoging Group"}])
    assert names[-1]["counterparty"] == "Summit Packaging Group"


def test_legal_suffix_variants_are_different_companies():
    names = snap_names([{"counterparty": "Pinecrest Packaging Inc"}] * 3 + [{"counterparty": "Pinecrest Packaging LLC"}])
    assert names[-1]["counterparty"] == "Pinecrest Packaging LLC"
    assert not same("counterparty", "Corvid Energy Co", "Corvid Energy Inc")


def test_rare_misspelled_word_snaps_to_common_word():
    names = snap_names([{"counterparty": "Vantage Robotics LLC"}] * 3 + [{"counterparty": "Vontage Robotics LLC"}])
    assert names[-1]["counterparty"] == "Vantage Robotics LLC"


def test_vote_majority_and_tie_priority():
    assert vote("reference", [("expensive", "A"), ("rules", "B"), ("cheap", "B")]) == ("B", 2)
    assert vote("reference", [("expensive", "A"), ("rules", "B")])[0] == "A"
    assert same("total_amount", 1.0, 1.004) and not same("total_amount", 1.0, None)


def test_ledger_never_exceeds_budget():
    led = Ledger(25)
    assert led.reserve(20) and not led.reserve(20) and led.reserve(5)
    led.refund(5)
    assert led.spent == 20


def test_normalise_rejects_bad_model_output():
    assert normalise({"doc_type": "email", "date": "2026-01-02", "total_amount": "1,000.5", "counterparty": "X", "reference": "Y"})["total_amount"] == 1000.5
    assert normalise({"doc_type": "memo", "date": "2026-01-02", "total_amount": 1, "counterparty": "X", "reference": "Y"}) is None
    assert normalise({"doc_type": "email", "date": "02/01/2026", "total_amount": 1, "counterparty": "X", "reference": "Y"}) is None


class Fake:
    """Offline model: answers with whatever the rules parse, optionally wrong."""
    def __init__(self, wrong=False):
        self.wrong, self.calls = wrong, 0

    def extract(self, text):
        self.calls += 1
        f = parse(text)[0]
        f = {k: (v if v is not None else "x") for k, v in f.items()}
        f["date"] = f["date"] if f["date"] != "x" else "2026-01-01"
        f["total_amount"] = 0.0 if f["total_amount"] == "x" else f["total_amount"]
        if self.wrong:
            f["reference"] = "WRONG"
        return f


def docs():
    return [{"id": "A", "text": INVOICE}, {"id": "B", "text": CONTRACT_OCR}, {"id": "C", "text": THREAD}, {"id": "D", "text": "garbage"}]


def test_route_respects_budget_and_counts_calls():
    cheap, exp = Fake(), Fake()
    res, rep = route(docs(), cheap, exp, budget=45, audit=1, workers=2)
    assert rep["units_spent"] <= 45
    assert rep["units_spent"] == rep["cheap_calls"] + 20 * rep["expensive_calls"]
    assert [r["cheap_calls"] for r in res.values()].count(1) == rep["cheap_calls"]


def test_disagreement_escalates_and_expensive_wins_ties():
    res, rep = route(docs()[2:3], Fake(wrong=True), Fake(), budget=100, audit=0, workers=1)
    assert res["C"]["expensive_calls"] == 1 and res["C"]["reference"] == "PO-53317"


def test_zero_budget_falls_back_to_rules():
    res, rep = route(docs()[:1], Fake(), Fake(), budget=0, audit=1, workers=1)
    assert rep["units_spent"] == 0 and res["A"]["total_amount"] == 105.0


def test_real_corpus_is_parsed_if_present():
    p = pathlib.Path("data/documents.jsonl")
    if p.exists():
        d = [json.loads(l) for l in p.open(encoding="utf-8")]
        assert len(d) == 300 and sum(parse(x["text"])[1] for x in d) >= 250
