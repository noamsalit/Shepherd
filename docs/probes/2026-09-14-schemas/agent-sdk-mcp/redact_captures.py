"""Privacy pass over captures/: the CLI's `initialize` control_response carries account.email and
account.organization, and transcripts carry an injected userEmail context line. Replace every occurrence
of those identifying strings (discovered from the captures themselves) with <redacted>, in every file.
subscriptionType / apiProvider are kept (D30-relevant, non-identifying).
Re-run: python3 redact_captures.py captures
"""
import json, pathlib, re, sys
root = pathlib.Path(sys.argv[1])
secrets = set()
for f in root.rglob("*.jsonl"):
    for line in f.read_text(errors="replace").splitlines():
        if '"account"' not in line:
            continue
        try:
            o = json.loads(line)
        except Exception:
            continue
        def walk(x):
            if isinstance(x, dict):
                if isinstance(x.get("account"), dict):
                    for k in ("email", "organization"):
                        v = x["account"].get(k)
                        if isinstance(v, str) and v and v != "<redacted>":
                            secrets.add(v)
                for v in x.values():
                    walk(v)
            elif isinstance(x, list):
                for v in x:
                    walk(v)
        walk(o)
emails = {s for s in secrets if "@" in s}
# organization is often "<email>'s Organization"; also redact bare emails found anywhere
pat = re.compile("|".join(re.escape(s) for s in sorted(secrets, key=len, reverse=True))) if secrets else None
n = 0
for f in root.rglob("*"):
    if not f.is_file() or f.is_symlink():
        continue
    t = f.read_text(errors="surrogateescape") if f.suffix in (".jsonl", ".json", ".txt", ".log", ".md") else None
    if t is None:
        continue
    new = pat.sub("<redacted>", t) if pat else t
    for e in emails:
        new = new.replace(e, "<redacted>")
    if new != t:
        f.write_text(new, errors="surrogateescape"); n += 1
print(f"identifying strings found: {len(secrets)}; files rewritten: {n}")
