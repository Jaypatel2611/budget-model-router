"""Three-tier router: free rules -> cheap LLM cross-check -> expensive LLM arbiter, under a unit budget."""
import random, threading, time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from .rules import FIELDS, close_name, parse, snap_names

CHEAP_COST, EXP_COST = 1, 20


def same(field, a, b):
    if a is None or b is None:
        return False
    if field == "total_amount":
        return abs(a - b) < 0.01
    if field == "counterparty":
        return close_name(a, b)
    return str(a).strip().lower() == str(b).strip().lower()


def vote(field, cands):
    """cands = [(source, value)] in priority order (expensive > rules > cheap). Majority wins, ties go to priority."""
    cands = [(s, v) for s, v in cands if v is not None]
    if not cands:
        return None, 0
    score = [sum(same(field, v, w) for _, w in cands) for _, v in cands]
    best = max(range(len(cands)), key=lambda i: (score[i], -i))
    return cands[best][1], score[best]


class Ledger:
    """Counts units. Reservation happens before a call; a failed call (no answer) is refunded."""
    def __init__(self, budget):
        self.budget, self.spent, self.lock = budget, 0, threading.Lock()

    def reserve(self, n):
        with self.lock:
            if self.spent + n > self.budget:
                return False
            self.spent += n
            return True

    def refund(self, n):
        with self.lock:
            self.spent -= n


def route(docs, cheap, expensive, budget=2100, audit=300, workers=6, deadline=None, seed=42):
    """docs = [{"id","text"}]. Returns (per-doc results, report dict)."""
    t0, ledger, rnd = time.time(), Ledger(budget), random.Random(seed)
    first = last = None
    parsed = {d["id"]: parse(d["text"]) for d in docs}
    risk = {i: 2 if not ok else 1 if fl else 0 for i, (_, ok, fl) in parsed.items()}
    hard = [d for d in docs if risk[d["id"]] == 2]  # rules could not parse/verify: straight to the expensive model
    clean = [d for d in docs if risk[d["id"]] == 0]
    audited = rnd.sample(clean, min(audit, len(clean)))  # random clean docs: measure how often the rules are right
    queue = [d for d in docs if risk[d["id"]] == 1] + audited  # cross-check these with the cheap model
    audited = {d["id"] for d in audited}
    max_exp = max(0, (budget - len(queue) * CHEAP_COST) // EXP_COST)  # cheap pass is planned first, the rest funds the arbiter
    res = {d["id"]: {"cheap": None, "expensive": None, "cheap_calls": 0, "expensive_calls": 0} for d in docs}
    exp_slots = threading.Semaphore(max_exp)
    timing = threading.Lock()

    def call(model, text, cost):
        nonlocal first, last
        if not ledger.reserve(cost):
            return None
        with timing:
            first = first or time.time()
        out = model.extract(text)
        with timing:
            last = time.time()
        if out is None:
            ledger.refund(cost)
        return out

    def arbitrate(d):
        if exp_slots.acquire(blocking=False):
            out = call(expensive, d["text"], EXP_COST)
            if out:
                res[d["id"]]["expensive"], res[d["id"]]["expensive_calls"] = out, 1
            else:
                exp_slots.release()

    def cross_check(d, ex_exp):
        out = call(cheap, d["text"], CHEAP_COST)
        if out:
            res[d["id"]]["cheap"], res[d["id"]]["cheap_calls"] = out, 1
        f0 = parsed[d["id"]][0]
        if out is None or any(not same(k, f0[k], out[k]) for k in FIELDS):
            futs.append(ex_exp.submit(arbitrate, d))

    futs = []
    with ThreadPoolExecutor(workers) as ex_cheap, ThreadPoolExecutor(workers) as ex_exp:
        futs += [ex_exp.submit(arbitrate, d) for d in hard]
        for f in [ex_cheap.submit(cross_check, d, ex_exp) for d in queue]:
            f.result()
        for f in futs:
            f.result()

    final, support = {}, {}
    for d in docs:
        i, r = d["id"], res[d["id"]]
        f0 = parsed[i][0]
        final[i], support[i] = {}, {}
        for k in FIELDS:
            final[i][k], support[i][k] = vote(k, [("expensive", (r["expensive"] or {}).get(k)), ("rules", f0[k]), ("cheap", (r["cheap"] or {}).get(k))])
    snap_names(list(final.values()))

    # Expected accuracy: no gold exists, so each field gets the accuracy implied by how it was confirmed.
    audit_fields = [(k, i) for i in audited if res[i]["cheap"] for k in FIELDS]
    agree = sum(same(k, parsed[i][0][k], res[i]["cheap"][k]) for k, i in audit_fields) / max(1, len(audit_fields))
    p_single = agree if audit_fields else 0.9  # rules-only fields: measured rules/cheap agreement on the audit sample
    p = 0.0
    for d in docs:
        for k in FIELDS:
            s = support[d["id"]][k]
            p += 0.98 if s >= 2 else (p_single if parsed[d["id"]][1] else 0.7)
    rep = dict(units_spent=ledger.spent, budget=budget,
               cheap_calls=sum(r["cheap_calls"] for r in res.values()), expensive_calls=sum(r["expensive_calls"] for r in res.values()),
               time_first_to_last_call_s=round((last - first), 1) if first else 0.0, total_runtime_s=round(time.time() - t0, 1),
               expected_accuracy=round(p / (len(docs) * len(FIELDS)), 4), rules_vs_cheap_agreement_on_clean_audit=round(agree, 4),
               docs_rules_only=sum(1 for r in res.values() if not r["cheap_calls"] and not r["expensive_calls"]),
               docs_confirmed_by_two_sources=sum(all(s >= 2 for s in support[d["id"]].values()) for d in docs),
               rules_checks_passed=sum(parsed[d["id"]][1] for d in docs), field_support=dict(Counter(s for v in support.values() for s in v.values())))
    return {i: dict(final[i], cheap_calls=res[i]["cheap_calls"], expensive_calls=res[i]["expensive_calls"]) for i in final}, rep

