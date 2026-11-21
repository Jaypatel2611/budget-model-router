"""One command: python -m src.run [--backend sim|anthropic] [--budget N]"""
import argparse, json, os, time
from .docs import generate
from .models import AnthropicLLM, SimLLM, EXP_COST
from .router import calibrate, route

ap = argparse.ArgumentParser()
ap.add_argument("--backend", default="sim", choices=["sim", "anthropic"])
ap.add_argument("--budget", type=int, default=1800, help="cost units; cheap=1, expensive=20")
ap.add_argument("--n", type=int, default=300)
ap.add_argument("--seed", type=int, default=42)
ap.add_argument("--workers", type=int, default=16)
a = ap.parse_args()

docs, gold, alts, diff = generate(a.n, a.seed)
dev, dgold, dalts, ddiff = generate(100, a.seed + 1, prefix="d")  # disjoint calibration set
gold.update(dgold); alts.update(dalts); diff.update(ddiff)
if a.backend == "sim":
    cheap, exp = SimLLM("cheap", gold, alts, diff, a.seed), SimLLM("expensive", gold, alts, diff, a.seed)
else:
    cheap, exp = AnthropicLLM("cheap"), AnthropicLLM("expensive")

t = time.time()
priors = calibrate(dev, gold, cheap, exp)
res, rep = route(docs, cheap, exp, a.budget, priors, a.workers)
rep["wall_time_s"] = time.time() - t
tot = sum(len(gold[d.id]) for d in docs)
rep["measured_accuracy"] = sum(res[d.id]["fields"].get(f) == v for d in docs for f, v in gold[d.id].items()) / tot
rep["all_expensive_cost"] = a.n * EXP_COST
rep["all_cheap_cost"] = a.n * cheap.cost
rep["all_cheap_measured_accuracy"] = sum(cheap.extract(d)[0].get(f) == v for d in docs for f, v in gold[d.id].items()) / tot
rep["priors"], rep["backend"] = priors, a.backend
os.makedirs("out", exist_ok=True)
with open("out/results.jsonl", "w") as fh:
    for d in docs:
        fh.write(json.dumps({"id": d.id, "kind": d.kind, **{k: v for k, v in res[d.id].items() if k != "ok"}}) + "\n")
json.dump(rep, open("out/report.json", "w"), indent=2)
ok = rep["measured_accuracy"] >= 0.92 and rep["cost"] <= a.budget and rep["sim_time_s"] < 600
print(json.dumps(rep, indent=2))
print(f"\nTARGETS: accuracy>=92% {'PASS' if rep['measured_accuracy']>=0.92 else 'FAIL'} | cost<=budget {'PASS' if rep['cost']<=a.budget else 'FAIL'} | time<10min {'PASS' if rep['sim_time_s']<600 else 'FAIL'}")
