"""Cascade router: cheap model on everything, risk-ranked escalation within a cost budget."""
import heapq, re
from concurrent.futures import ThreadPoolExecutor
from .docs import CUES, CUES_EMAIL, FIELDS

FORMAT = {"date": r"\d{4}-\d{2}-\d{2}", "effective_date": r"\d{4}-\d{2}-\d{2}", "deadline": r"\d{4}-\d{2}-\d{2}",
          "total": r"\d+\.\d\d", "value": r"\d+\.\d\d", "amount": r"\d+\.\d\d", "term_months": r"\d+",
          "sender": r"[^@\s]+@[^@\s]+\.\w+", "currency": r"[A-Z]{3}"}
norm = lambda s: s.replace(",", "").lower()


def check_fields(doc, fields):
    """Text-only verification (no gold). Returns {field: True if value passes all checks}."""
    text, lines, ok = norm(doc.text), [norm(l) for l in doc.text.split("\n")], {}
    for f in FIELDS[doc.kind]:
        v = norm(str(fields.get(f, "")))
        cue = (CUES_EMAIL if doc.kind == "email" else {}).get(f, CUES[f])
        fmt = re.fullmatch(FORMAT[f], str(fields.get(f, ""))) if f in FORMAT else True
        ok[f] = bool(v) and v in text and bool(fmt) and any(v in l and cue in l for l in lines)
    return ok


def risk(doc, fields, conf):
    ok = check_fields(doc, fields)
    return sum(not x for x in ok.values()) + 0.5 * (1 - conf), ok


def schedule(latencies, workers):
    """Virtual makespan of tasks on a worker pool (greedy, in order)."""
    pool = [0.0] * workers
    heapq.heapify(pool)
    for l in latencies:
        heapq.heappush(pool, heapq.heappop(pool) + l)
    return max(pool)


def call(model, doc, retries=2):
    for _ in range(retries + 1):
        try:
            return model.extract(doc)
        except Exception:  # bad JSON / API error: retry, then give up (caller falls back)
            pass
    return None


def calibrate(dev_docs, gold, cheap, expensive):
    """Measure priors on a labelled dev set that is disjoint from the eval set."""
    hit = {True: [0, 0], False: [0, 0]}
    exp = [0, 0]
    for d in dev_docs:
        fields, conf, _ = cheap.extract(d)
        for f, passed in check_fields(d, fields).items():
            hit[passed][0] += fields[f] == gold[d.id][f]; hit[passed][1] += 1
        ef = expensive.extract(d)[0]
        exp[0] += sum(ef[f] == gold[d.id][f] for f in gold[d.id]); exp[1] += len(gold[d.id])
    return {"cheap_ok": hit[True][0] / max(1, hit[True][1]), "cheap_flagged": hit[False][0] / max(1, hit[False][1]),
            "expensive": exp[0] / exp[1]}


def route(docs, cheap, expensive, budget, priors, workers=16):
    with ThreadPoolExecutor(workers) as ex:
        first = list(ex.map(lambda d: call(cheap, d), docs))
    res, lat1 = {}, []
    for d, out in zip(docs, first):
        fields, conf, lat = out if out else ({}, 0.0, 0.0)
        r, ok = risk(d, fields, conf)
        res[d.id] = dict(model="cheap", fields=fields, risk=r, ok=ok)
        lat1.append(lat)
    spent = len(docs) * cheap.cost
    todo = []
    for d in sorted(docs, key=lambda d: -res[d.id]["risk"]):
        if all(res[d.id]["ok"].values()) or spent + expensive.cost > budget:
            break
        todo.append(d); spent += expensive.cost
    with ThreadPoolExecutor(workers) as ex:
        second = list(ex.map(lambda d: call(expensive, d), todo))
    lat2 = []
    for d, out in zip(todo, second):
        if out:  # on failure keep the cheap answer, but the call was still paid for
            res[d.id].update(model="expensive", fields=out[0]); lat2.append(out[2])
    n = sum(len(FIELDS[d.kind]) for d in docs)
    exp_correct = sum(priors["expensive"] * len(FIELDS[d.kind]) if res[d.id]["model"] == "expensive"
                      else sum(priors["cheap_ok" if p else "cheap_flagged"] for p in res[d.id]["ok"].values()) for d in docs)
    return res, dict(cost=spent, budget=budget, escalated=len(todo), expected_accuracy=exp_correct / n,
                     sim_time_s=schedule(lat1, workers) + schedule(lat2, workers))
