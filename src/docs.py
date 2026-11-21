"""Seeded synthetic documents + gold labels. The router never sees gold; only the simulated models do."""
import random
from dataclasses import dataclass

FIELDS = {
    "invoice": ["invoice_no", "date", "vendor", "total", "currency"],
    "contract": ["party_a", "effective_date", "term_months", "governing_law", "value"],
    "email": ["sender", "date", "subject", "deadline", "amount"],
}
# Cue words a correct value should sit next to (used by the verifier).
CUES = {
    "invoice_no": "invoice", "date": "issue", "vendor": "vendor", "total": "total", "currency": "currency",
    "party_a": "provider", "effective_date": "effective", "term_months": "term", "governing_law": "governing",
    "value": "value", "sender": "from", "deadline": "by", "amount": "payment", "subject": "subject",
}
# 'date' means different things per kind; email date cue differs.
CUES_EMAIL = {"date": "date"}
VENDORS = ["Acme Corp", "Globex Ltd", "Initech", "Umbrella Supply", "Hooli Systems", "Stark Parts", "Wayne Logistics", "Soylent Foods"]
LAWS = ["Delaware", "California", "England and Wales", "New York", "Singapore", "Ontario"]
SUBJ = ["Payment reminder", "Contract renewal", "Q3 delivery schedule", "Overdue balance", "Updated terms"]


@dataclass(frozen=True)
class Doc:
    id: str
    kind: str
    text: str


def _date(r):
    return f"20{r.randint(23, 26)}-{r.randint(1, 12):02d}-{r.randint(1, 28):02d}"


def _money(r, lo=200, hi=90000):
    return f"{r.uniform(lo, hi):.2f}"


def _comma(m):
    return f"{float(m):,.2f}"


def make_doc(r, doc_id):
    kind = r.choice(list(FIELDS))
    g, alts = {}, {}
    if kind == "invoice":
        no, d, d2, v, v2 = f"INV-{r.randint(1000, 99999)}", _date(r), _date(r), r.choice(VENDORS), r.choice(VENDORS)
        tot, sub, cur = _money(r), _money(r), r.choice(["USD", "EUR", "GBP"])
        g = dict(invoice_no=no, date=d, vendor=v, total=tot, currency=cur)
        alts = dict(date=[d2], vendor=[v2], total=[sub])
        lines = [f"INVOICE {no}", f"Vendor: {v}", f"Bill to: {v2}", f"Issue date: {d}", f"Due date: {d2}",
                 f"Subtotal: {_comma(sub)}", f"Total due: {_comma(tot)}", f"Currency: {cur}"]
    elif kind == "contract":
        a, b, d, d2 = r.choice(VENDORS), r.choice(VENDORS), _date(r), _date(r)
        n, k, law, val = str(r.choice([6, 12, 24, 36])), str(r.choice([30, 60, 90])), r.choice(LAWS), _money(r, 5000, 900000)
        g = dict(party_a=a, effective_date=d, term_months=n, governing_law=law, value=val)
        alts = dict(party_a=[b], effective_date=[d2], term_months=[k])
        lines = ["SERVICE AGREEMENT", f"Provider: {a}", f"Client: {b}", f"Effective date: {d}", f"Signed on: {d2}",
                 f"Term: {n} months, renewal notice {k} days", f"Governing law: {law}", f"Contract value: {_comma(val)}"]
    else:
        em, cc, d, dl, old = f"{r.choice(['ann', 'raj', 'li', 'sam'])}{r.randint(1, 99)}@{r.choice(['corp', 'mail', 'biz'])}.com", "cc1@corp.com", _date(r), _date(r), _date(r)
        subj, amt = r.choice(SUBJ), _money(r, 100, 20000)
        g = dict(sender=em, date=d, subject=subj, deadline=dl, amount=amt)
        alts = dict(deadline=[old, d], date=[dl])
        lines = [f"From: {em}", f"Cc: {cc}", f"Date: {d}", f"Subject: {subj}", f"Hi, last review was on {old}.",
                 f"Please send payment of {_comma(amt)} by {dl}."]
    # prose layout: one long line, so cue-based checks cannot tell a distractor from the real value
    text = " ".join(lines) if r.random() < 0.35 else "\n".join(lines)
    return Doc(doc_id, kind, text), g, alts, r.random()


def generate(n, seed, prefix="c"):
    r = random.Random(seed)
    docs, gold, alts, diff = [], {}, {}, {}
    for i in range(n):
        d, g, a, df = make_doc(r, f"{prefix}{i:04d}")
        docs.append(d); gold[d.id] = g; alts[d.id] = a; diff[d.id] = df
    return docs, gold, alts, diff
