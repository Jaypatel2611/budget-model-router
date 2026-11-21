from src.docs import generate
from src.models import SimLLM
from src.router import calibrate, check_fields, route, schedule


def setup(n=60, seed=1):
    docs, gold, alts, diff = generate(n, seed)
    mk = lambda t: SimLLM(t, gold, alts, diff, seed)
    return docs, gold, mk("cheap"), mk("expensive")


PRIORS = {"cheap_ok": 0.95, "cheap_flagged": 0.1, "expensive": 0.98}


def test_generation_is_deterministic():
    assert generate(5, 7)[0] == generate(5, 7)[0]


def test_gold_passes_checks_and_hallucination_fails():
    docs, gold, *_ = setup()
    d = docs[0]
    assert all(check_fields(d, gold[d.id]).values())
    bad = dict(gold[d.id]); k = next(iter(bad)); bad[k] = "zzz-not-in-text"
    assert not check_fields(d, bad)[k]


def test_budget_never_exceeded_and_zero_budget_means_cheap_only():
    docs, _, cheap, exp = setup()
    _, rep = route(docs, cheap, exp, budget=150, priors=PRIORS)
    assert rep["cost"] <= 150
    _, rep0 = route(docs, cheap, exp, budget=0, priors=PRIORS)
    assert rep0["escalated"] == 0


def test_escalation_improves_accuracy():
    docs, gold, cheap, exp = setup(120)
    acc = lambda res: sum(res[d.id]["fields"][f] == v for d in docs for f, v in gold[d.id].items())
    low, _ = route(docs, cheap, exp, 120, PRIORS)
    high, _ = route(docs, cheap, exp, 900, PRIORS)
    assert acc(high) > acc(low)


def test_failed_expensive_call_falls_back_to_cheap():
    docs, _, cheap, exp = setup(20)
    exp.extract = lambda d: (_ for _ in ()).throw(RuntimeError("api down"))
    res, rep = route(docs, cheap, exp, 600, PRIORS)
    assert all(r["model"] == "cheap" for r in res.values())


def test_schedule_makespan():
    assert schedule([1, 1, 1, 1], 2) == 2 and schedule([], 4) == 0
