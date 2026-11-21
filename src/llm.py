"""Chat client for Groq and Mercury (stdlib only). Keys come from the environment or a git-ignored .env file."""
import json, os, re, threading, time, urllib.error, urllib.request

PROMPT = """Extract fields from the business document below. Our company is Meridian Works Ltd.
Reply with JSON only: {"doc_type": "invoice|contract|email", "date": "YYYY-MM-DD", "total_amount": number without currency, "counterparty": "the OTHER company, clean spelling (fix OCR typos)", "reference": "string"}
- invoice: invoice date (not due date), grand total due incl. tax, vendor name, invoice number.
- contract: date the agreement was entered into (not the start date), total contract value (not instalments), the Provider, agreement number.
- email: the Date header, the final agreed total (ignore quoted history and earlier quotes), the sender's company from the signature, the PO number.

DOCUMENT:
"""


def load_env(path=".env"):
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.strip().split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"\''))


def clean_for_llm(text):
    """Drop quoted email history (saves tokens, removes decoy amounts) and the scan banner."""
    return re.split(r"\n\s*On .{5,60}wrote:", text)[0].replace("[scanned document, text recognised automatically]\n\n", "")[:6000]


def normalise(j):
    """Coerce a model answer to the output schema; None if unusable."""
    try:
        dt = str(j["doc_type"]).strip().lower()
        date = str(j["date"]).strip()
        amt = float(str(j["total_amount"]).replace(",", ""))
        if dt not in ("invoice", "contract", "email") or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            return None
        return {"doc_type": dt, "date": date, "total_amount": amt,
                "counterparty": str(j["counterparty"]).strip(), "reference": str(j["reference"]).strip()}
    except (KeyError, ValueError, TypeError):
        return None


PROVIDERS = {  # model-name prefix -> (endpoint, key env var, tokens/min we allow ourselves; None = rely on 429 + retry-after)
    "mercury": ("https://api.inceptionlabs.ai/v1/chat/completions", "MERCURY_API_KEY", None),
    "openai/": ("https://api.groq.com/openai/v1/chat/completions", "GROQ_API_KEY", 7000),  # Groq free tier: 8000 tokens/min per model
}


class Chat:
    """OpenAI-compatible chat client for Groq and Mercury."""
    def __init__(self, model, deadline=None):
        load_env()
        self.url, key_env, self.tpm = next(v for k, v in PROVIDERS.items() if model.startswith(k))
        self.key, self.model, self.deadline = os.environ.get(key_env), model, deadline
        self.window, self.lock = [], threading.Lock()  # sliding 60 s window of [time, tokens]
        if not self.key:
            raise SystemExit(f"{key_env} missing (set it in the environment or .env)")

    def _acquire(self, est):
        """Block until est tokens fit in the per-minute window. Returns the window entry, or None past the deadline."""
        if self.tpm is None:
            return [0, 0]
        while not (self.deadline and time.time() > self.deadline):
            with self.lock:
                now = time.time()
                self.window = [e for e in self.window if now - e[0] < 60]
                if sum(e[1] for e in self.window) + est <= self.tpm:
                    self.window.append([now, est])
                    return self.window[-1]
                wait = self.window[0][0] + 60 - now
            time.sleep(min(max(wait, 0.3), 3))
        return None

    def extract(self, text, attempts=6):
        """-> normalised dict, or None if the call failed (a failed call returns no answer, so it is not charged)."""
        body = {"model": self.model, "temperature": 0, "response_format": {"type": "json_object"},
                "messages": [{"role": "user", "content": PROMPT + clean_for_llm(text)}]}
        if "gpt-oss" in self.model:
            body["reasoning_effort"] = "low"
        req = lambda: urllib.request.Request(self.url, json.dumps(body).encode(),
                                             {"Authorization": "Bearer " + self.key, "Content-Type": "application/json", "User-Agent": "model-router/1.0"})
        for i in range(attempts):
            entry = self._acquire(len(body["messages"][0]["content"]) // 3 + 250)
            if entry is None:
                return None
            try:
                with urllib.request.urlopen(req(), timeout=45) as r:
                    j = json.load(r)
                    entry[1] = j["usage"]["total_tokens"]  # replace the estimate with the real count
                    return normalise(json.loads(j["choices"][0]["message"]["content"]))
            except urllib.error.HTTPError as e:  # 429 = token-per-minute limit: wait as told, then retry
                wait = float(e.headers.get("retry-after") or 2 ** i)
                time.sleep(min(wait, 20) if e.code in (429, 500, 502, 503) else 0)
                if e.code not in (429, 500, 502, 503):
                    return None
            except (urllib.error.URLError, TimeoutError, ValueError, KeyError):
                time.sleep(1)
        return None
