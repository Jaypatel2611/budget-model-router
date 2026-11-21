"""One command: python -m src.run [--docs PATH] [--budget N]"""
import argparse, json, os

from .llm import Chat
from .router import route

ap = argparse.ArgumentParser()
ap.add_argument("--docs", default="data/documents.jsonl")
ap.add_argument("--budget", type=int, default=2100, help="units: cheap=1, expensive=20")
ap.add_argument("--cheap", default="mercury-3")
ap.add_argument("--expensive", default="openai/gpt-oss-120b")
ap.add_argument("--audit", type=int, default=300, help="clean docs also sent to the cheap model to measure rules accuracy")
ap.add_argument("--deadline", type=int, default=540, help="seconds after which no new calls start (limit is 600)")
ap.add_argument("--out", default="results", help="directory for output.jsonl and report.json")
a = ap.parse_args()

docs = [json.loads(l) for l in open(a.docs, encoding="utf-8")]
import time
dl = time.time() + a.deadline
res, rep = route(docs, Chat(a.cheap, dl), Chat(a.expensive, dl), a.budget, a.audit, deadline=a.deadline)
rep.update(cheap_model=a.cheap, expensive_model=a.expensive, documents=len(docs))
os.makedirs(a.out, exist_ok=True)
with open(os.path.join(a.out, "output.jsonl"), "w", encoding="utf-8") as fh:
    for d in docs:
        fh.write(json.dumps({"id": d["id"], **res[d["id"]]}) + "\n")
json.dump(rep, open(os.path.join(a.out, "report.json"), "w"), indent=2)
print(json.dumps(rep, indent=2))
