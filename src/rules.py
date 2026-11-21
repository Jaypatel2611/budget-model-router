"""Tier 0: free deterministic parser + self-consistency checks. No gold, no network."""
import difflib, re

FIELDS = ["doc_type", "date", "total_amount", "counterparty", "reference"]
OURS = "meridian works"
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]
SCAN = "[scanned document, text recognised automatically]"
AMT = r"([\d][\d,\. ]*\d)"


def month_no(tok):
    """Month name/abbrev -> 1..12, tolerant to OCR (1->l, 0->o, rn->m)."""
    t = tok.lower().replace("1", "l").replace("0", "o").replace("rn", "m").strip(".")
    if len(t) < 3:
        return None
    for i, m in enumerate(MONTHS, 1):
        if m.startswith(t) or difflib.SequenceMatcher(None, t, m).ratio() >= 0.8:
            return i
    return None


def parse_date(s):
    """First date in s -> YYYY-MM-DD or None. Handles ISO, 30-Jun-2026, 14 August 2026, July 3, 2026."""
    if m := re.search(r"(\d{4})-(\d{2})-(\d{2})", s):
        return f"{m[1]}-{m[2]}-{m[3]}"
    if m := re.search(r"\b(\d{1,2})[\s-]+([A-Za-z01]{3,9})\.?,?[\s-]+(\d{4})\b", s):
        mo = month_no(m[2])
        return f"{m[3]}-{mo:02d}-{int(m[1]):02d}" if mo else None
    if m := re.search(r"\b([A-Za-z01]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})\b", s):
        mo = month_no(m[1])
        return f"{m[3]}-{mo:02d}-{int(m[2]):02d}" if mo else None
    return None


def parse_amt(s):
    s = re.sub(r"[Oo]", "0", s).replace(" ", "")
    s = re.sub(r",(\d{2})$", r".\1", s)  # OCR: "123,000,00" -> decimal comma
    s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def money(pattern, text, flags=re.I):
    m = re.search(pattern + r"\s*(?:[A-Z]{3})?\s*" + AMT, text, flags)
    return parse_amt(m[1]) if m else None


def parse(text):
    """-> (fields dict with None for unparsed, checks_ok bool, flags set)."""
    scanned = text.startswith(SCAN)
    t = text.replace(SCAN, "").strip()
    f = dict.fromkeys(FIELDS)
    flags = {"scanned"} if scanned else set()
    checks = []
    if t.startswith("From:"):
        f["doc_type"] = "email"
        top = re.split(r"\n\s*On .{5,60}wrote:", t)[0]  # drop quoted history
        if re.search(r"^Subject:\s*RE", top, re.M | re.I):
            flags.add("thread")
        f["date"] = parse_date((re.search(r"^Date:(.*)$", top, re.M) or [0, ""])[1])
        subj = re.search(r"^Subject:(.*)$", top, re.M)
        po = re.search(r"PO-\d+", subj[1]) if subj else None
        f["reference"] = po[0] if po else None
        f["total_amount"] = money(r"final agreed figure of", top) or money(r"total comes to", top)
        sig = re.search(r"Regards,\s*\n(.+)\n(.+)", top)
        f["counterparty"] = sig[2].strip() if sig else None
        checks.append(bool(po) and top.count(po[0]) >= 2 if po else False)
    elif re.search(r"CTR-\d+|Agre\w*ment\s*No", t, re.I):
        f["doc_type"] = "contract"
        m = re.search(r"entered\s*into\s*on\s*(.+?)\s*between", t, re.I | re.S)
        f["date"] = parse_date(m[1]) if m else None
        f["total_amount"] = money(r"total\s*contract\s*val\w*\s*is", t)
        ref = re.search(r"Agre\w*ment\s*No[.,]?\s*([A-Z0-9-]+)", t, re.I)
        f["reference"] = ref[1].upper() if ref else None
        flat = re.sub(r"\s+", " ", t)
        pm = re.search(r"betw\w+ (.+?) ?\( ?[tf]he ?[\"“”']?\w+[\"“”']? ?\) ?\w{2,4} (.+?) ?\( ?[tf]he", flat)
        other = [p.strip() for p in (pm.groups() if pm else []) if OURS not in p.lower()]
        f["counterparty"] = other[0] if other else None
        inst = re.search(r"(\d+)\s*inst\w+\s*of\s*(?:[A-Z]{3})?\s*" + AMT, t, re.I)
        each = parse_amt(inst[2]) if inst else None
        if each and f["total_amount"]:
            checks.append(abs(int(inst[1]) * each - f["total_amount"]) <= int(inst[1]) * 0.01 + 0.005)
        else:
            checks.append(False)
    elif re.search(r"INV\w*[-\s]\d{4}|Invoice\s*No", t, re.I):
        f["doc_type"] = "invoice"
        f["counterparty"] = next((l.strip() for l in t.split("\n") if l.strip()), None)
        m = re.search(r"Invoice\s*Da\w*\s*:?\s*(.+)", t, re.I)
        f["date"] = parse_date(m[1]) if m else None
        f["total_amount"] = money(r"Total\s*Due\s*:?", t)
        ref = re.search(r"Invoice\s*No\.?\s*:?\s*([A-Z0-9-]+)", t, re.I)
        f["reference"] = ref[1].upper().replace("O", "0") if ref else None
        sub, tax = money(r"Subtotal\s*:?", t), money(r"Tax\s*:?", t)
        checks.append(None not in (sub, tax, f["total_amount"]) and abs(sub + tax - f["total_amount"]) <= 0.011)
    ok = all(v is not None for v in f.values()) and all(checks) and bool(checks)
    return f, ok, flags


SUFFIX = {"ltd", "llc", "inc", "plc", "co", "pvt", "group", "corp", "limited"}


def close_name(a, b):
    """Same company up to OCR noise: same token count, at most one differing token, and never a differing legal suffix
    (Foods LLC and Foods Inc are different companies)."""
    x, y = a.lower().split(), b.lower().split()
    if len(x) != len(y):
        return False
    diff = [(p, q) for p, q in zip(x, y) if p != q]
    if not diff:
        return True
    p, q = diff[0]
    return len(diff) == 1 and p not in SUFFIX and q not in SUFFIX and difflib.SequenceMatcher(None, p, q).ratio() >= 0.75


def snap_names(fields_list):
    """OCR can corrupt a company name; snap it to the most common close spelling seen across the corpus."""
    from collections import Counter
    cnt = Counter(f["counterparty"] for f in fields_list if f.get("counterparty"))
    for f in fields_list:
        n = f.get("counterparty")
        if n:
            close = [c for c in cnt if close_name(n, c)]
            f["counterparty"] = max(close, key=lambda c: cnt[c]) if close else n
    # word level: a rare word (<3 uses) that is one OCR slip away from a common word (>=3 uses) is that common word
    words = Counter(w for f in fields_list for w in (f.get("counterparty") or "").split())
    common = [w for w, c in words.items() if c >= 3 and w.lower() not in SUFFIX]
    for f in fields_list:
        if f.get("counterparty"):
            f["counterparty"] = " ".join(
                next((c for c in common if len(c) == len(w) and sum(x != y for x, y in zip(c, w)) == 1), w)
                if words[w] < 3 and w.lower() not in SUFFIX else w for w in f["counterparty"].split())
    return fields_list
