"""Model backends. extract(doc) -> (fields, confidence 0..1, latency_s)."""
import json, os, random, time

CHEAP_COST, EXP_COST = 1, 20


def mutate(v, r, text):
    """Make a plausible-looking but wrong value that is not present in the text."""
    for _ in range(20):
        s = list(v)
        idx = [i for i, c in enumerate(s) if c.isdigit()] or list(range(len(s)))
        i = r.choice(idx)
        s[i] = str((int(s[i]) + r.randint(1, 8)) % 10) if s[i].isdigit() else r.choice("xyzq")
        m = "".join(s)
        if m != v and m.replace(",", "") not in text.replace(",", ""):
            return m
    return v + "x"


class SimLLM:
    """Deterministic simulated model. Error rate scales with hidden doc difficulty."""
    PARAMS = {"cheap": dict(err=0.15, cost=CHEAP_COST, lat=0.6, ok=(0.9, 0.07), bad=(0.7, 0.15)),
              "expensive": dict(err=0.02, cost=EXP_COST, lat=8.0, ok=(0.95, 0.04), bad=(0.8, 0.1))}

    def __init__(self, tier, gold, alts, diff, seed=0):
        self.tier, self.p, self.cost = tier, self.PARAMS[tier], self.PARAMS[tier]["cost"]
        self.gold, self.alts, self.diff, self.seed = gold, alts, diff, seed

    def extract(self, doc):
        r = random.Random(f"{self.seed}:{self.tier}:{doc.id}")
        out, confs = {}, []
        for f, v in self.gold[doc.id].items():
            wrong = r.random() < self.p["err"] * (0.5 + self.diff[doc.id])
            a = self.alts[doc.id].get(f)
            out[f] = (r.choice(a) if a and r.random() < 0.5 else mutate(v, r, doc.text)) if wrong else v
            mu, sd = self.p["bad" if wrong else "ok"]
            confs.append(min(1.0, max(0.0, r.gauss(mu, sd))))
        return out, sum(confs) / len(confs), self.p["lat"] * r.uniform(0.7, 1.5)


class AnthropicLLM:
    """Real backend (untested without a key). Needs `pip install anthropic` and ANTHROPIC_API_KEY."""
    IDS = {"cheap": "claude-haiku-5-5", "expensive": "claude-opus-5-5"}

    def __init__(self, tier):
        import anthropic  # imported lazily so the sim path has no dependency
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise SystemExit("ANTHROPIC_API_KEY not set")
        self.client, self.model, self.cost = anthropic.Anthropic(), self.IDS[tier], CHEAP_COST if tier == "cheap" else EXP_COST

    def extract(self, doc):
        from .docs import FIELDS
        prompt = (f"Extract these fields from the {doc.kind} below. Reply with ONLY JSON: "
                  f'{{"fields": {{{", ".join(f"{f!r}: string" for f in FIELDS[doc.kind])}}}, "confidence": 0-1}}. '
                  f"Dates as YYYY-MM-DD, amounts as plain numbers with 2 decimals.\n\n<document>\n{doc.text[:20000]}\n</document>")
        t = time.time()
        msg = self.client.messages.create(model=self.model, max_tokens=400, messages=[{"role": "user", "content": prompt}])
        j = json.loads(msg.content[0].text)
        return {k: str(v) for k, v in j["fields"].items()}, float(j.get("confidence", 0.5)), time.time() - t
