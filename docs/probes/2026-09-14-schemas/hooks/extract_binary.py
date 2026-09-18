#!/usr/bin/env python3
"""Extract Claude Code hook schemas from the installed CLI binary (2026-09-14).

Re-run:  python3 docs/probes/2026-09-14-schemas/hooks/extract_binary.py
Writes into docs/probes/2026-09-14-schemas/hooks/binary/:
  version.txt                       claude --version + binary path + sha256
  hook-events.json                  the settings-side event enum (var Im=[...])
  sdk-hook-events.json              the SDK-side event enum (Sle=[...])
  hook-input-schemas.txt            zod input schemas, one per event (descriptions kept)
  hook-output-schemas.txt           zod hook stdout-JSON schemas
  settings-hook-config-schema.txt   settings.json hooks schema + validator code
  enums.json                        SessionEnd reasons, StopFailure errors, SessionStart sources,
                                    Notification types (literals), PreCompact triggers, ...
  hook-env-and-exit-strings.txt     strings about exit codes / timeouts / env for hooks
The binary is a Bun single-file executable whose JS is embedded as text, so this is
byte-search + regex, not decompilation. Offsets change per build.
"""
import hashlib, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "binary")
os.makedirs(OUT, exist_ok=True)

claude = subprocess.run(["bash", "-lc", "readlink -f $(which claude)"], capture_output=True, text=True).stdout.strip()
ver = subprocess.run(["claude", "--version"], capture_output=True, text=True).stdout.strip()
data = open(claude, "rb").read()
with open(os.path.join(OUT, "version.txt"), "w") as f:
    f.write(f"claude --version: {ver}\nbinary: {claude}\nsha256: {hashlib.sha256(data).hexdigest()}\nsize: {len(data)}\n")


def find_all(pat: bytes):
    return [m.start() for m in re.finditer(re.escape(pat), data)]


def js_array_at(off: int) -> list:
    end = data.index(b"]", off)
    return json.loads(data[off:end + 1].decode())


# 1. event enums
im = find_all(b'var Im=["PreToolUse"')
sle = find_all(b'Sle=["PreToolUse"')
events = js_array_at(im[0] + len(b"var Im=")) if im else None
sdk_events = js_array_at(sle[0] + len(b"Sle=")) if sle else None
json.dump({"offset": im[0] if im else None, "count": len(events or []), "events": events},
          open(os.path.join(OUT, "hook-events.json"), "w"), indent=1)
json.dump({"offset": sle[0] if sle else None, "count": len(sdk_events or []), "events": sdk_events},
          open(os.path.join(OUT, "sdk-hook-events.json"), "w"), indent=1)

# 2. input + output schemas: region from the base schema to the union of outputs
start = data.index(b"var we=f(()=>u({session_id:o(),transcript_path:o(),cwd:o()")
end = data.index(b"Zz=f(()=>Ne([sce(),ode()]))", start) + 40
region = data[start:end].decode("utf8", "replace")
parts = re.split(r",(?=[A-Za-z_$][A-Za-z0-9_$]{1,4}=f\(\(\)=>)", region)
inp, outp = [], []
for p in parts:
    (outp if "hookEventName:" in p or p.startswith(("ode=", "sce=", "Zz=")) else inp).append(p)
with open(os.path.join(OUT, "hook-input-schemas.txt"), "w") as f:
    f.write(f"# claude {ver}; byte offset {start}. zod minified: u=object o=string v=number H=boolean "
            f"R=literal V=enum T=array ie=unknown de=record Ne=union .and=intersection\n")
    for p in inp:
        f.write(p + "\n\n")
with open(os.path.join(OUT, "hook-output-schemas.txt"), "w") as f:
    f.write(f"# claude {ver}\n")
    for p in outp:
        f.write(p + "\n\n")

# 3. settings hooks config schema + validator
s2 = data.index(b'function Rd(){let e=u({type:R("command")')
e2 = data.index(b"var HMe=500", s2)
with open(os.path.join(OUT, "settings-hook-config-schema.txt"), "w") as f:
    f.write(f"# claude {ver}; byte offset {s2}\n")
    f.write(data[s2:e2].decode("utf8", "replace"))

# 4. enums
def enum_after(anchor: bytes):
    i = data.find(anchor)
    if i < 0:
        return None
    j = data.index(b"[", i)
    return js_array_at(j)

enums = {
    "SessionEnd.reason (rce)": enum_after(b"rce=["),
    "StopFailure.error (o_)": enum_after(b'o_=f(()=>V(['),
    "SessionStart.source": re.search(rb'R\("SessionStart"\),source:V\((\[[^\]]*\])', data).group(1).decode(),
    "PreCompact/PostCompact.trigger": re.search(rb'R\("PreCompact"\),trigger:V\((\[[^\]]*\])', data).group(1).decode(),
    "UserPromptSubmit.source": re.search(rb'R\("UserPromptSubmit"\),prompt:o\(\),source:V\((\[[^\]]*\])', data).group(1).decode(),
    "FileChanged.event": re.search(rb'R\("FileChanged"\),file_path:o\(\),event:V\((\[[^\]]*\])', data).group(1).decode(),
    "ConfigChange.source (Wle)": enum_after(b"Wle=["),
    "InstructionsLoaded.load_reason (Yle)": enum_after(b"Yle=["),
    "InstructionsLoaded.memory_type (qle)": enum_after(b"qle=["),
    "Setup.trigger": re.search(rb'R\("Setup"\),trigger:V\((\[[^\]]*\])', data).group(1).decode(),
    "Notification.notification_type literals (notificationType:\"...\" in source; schema types it as free string)":
        sorted(set(m.decode() for m in re.findall(rb'notificationType:"([a-z_]+)"', data))),
    "Notification types list (VAr, next to preferredNotifChannel list P2)": enum_after(b"VAr=["),
    "Notification dispatcher (source text)": re.search(rb'async function ZT\(e,n,\{[^}]*\}=\{\}\)\{.{0,400}?matchQuery:E', data).group(0).decode("utf8", "replace"),
    "permission_mode values (Xt)": re.search(rb'V\((\["default","acceptEdits","bypassPermissions","plan","dontAsk","auto"\])\)', data).group(1).decode(),
}
json.dump(enums, open(os.path.join(OUT, "enums.json"), "w"), indent=1)
# raw source text of the enums, byte-for-byte from the binary
with open(os.path.join(OUT, "enum-sources.txt"), "w") as f:
    f.write(f"# claude {ver}: raw bytes from the binary\n")
    for rx in [rb'o_=f\(\(\)=>V\(\[[^\]]*\]\)\)', rb'rce=\[[^\]]*\]', rb'R\("SessionStart"\),source:V\(\[[^\]]*\]\)',
               rb'VAr=\[[^\]]*\]', rb'var Im=\[[^\]]*\]', rb'R\("Notification"\),message:o\(\),title:o\(\)\.optional\(\),notification_type:o\(\)']:
        m = re.search(rx, data)
        f.write((m.group(0).decode("utf8", "replace") if m else f"NOT FOUND {rx!r}") + "\n")

# 4b. runtime source snippets (common-field builder, default timeout, Notification/MessageDisplay dispatch)
snips = [
    ("common hook input builder La()", rb"function La\(e,n,r,s\)\{let d=s\?\.agentType.{0,900}?effort:A\}\}"),
    ("default hook timeout Mp (ms)", rb"var Mp=600000,[^;]{0,60}"),
    ("Notification + MessageDisplay dispatchers", rb"async function\*rXt\(e,n,r,s,d=Mp.{0,900}?matchQuery:E[^}]*\}\)\}"),
    ("hook runner VE() head", rb"async function VE\(e\)\{.{0,1400}"),
    ("events awaited with sync gating q5s", rb"var q5s=new Set\(\[[^\]]*\]\)"),
    ("StopFailure dispatcher pet()", rb"async function pet\(e,n,r=Mp\)\{.{0,700}"),
    ("PermissionDenied dispatch condition", rb".{0,300}decisionReason\?\.type===\"classifier\"&&hn\.decisionReason\.classifier===\"auto-mode\".{0,200}"),
    ("idle_prompt sender", rb"sendIdleNotification:\(\)=>\{[^}]*\}"),
    ("hook stdout JSON parse fet()", rb"function fet\(e\)\{.{0,600}"),
]
with open(os.path.join(OUT, "runtime-source-snippets.txt"), "w") as f:
    f.write(f"# claude {ver}\n")
    for name, rx in snips:
        m = re.search(rx, data, re.S)
        f.write(f"== {name} @{m.start() if m else None}\n{m.group(0).decode('utf8', 'replace') if m else 'NOT FOUND'}\n\n")

# 4c. where StopFailure.error values are assigned (Ho({... error:"<value>"})) -> count per enum value
errvals = enums["StopFailure.error (o_)"]
with open(os.path.join(OUT, "stopfailure-error-assignments.txt"), "w") as f:
    f.write(f"# claude {ver}: occurrences of the literal error:\"<value>\" per StopFailure enum value\n")
    for v in errvals:
        n = len(re.findall(rb'error:"' + v.encode() + rb'"', data))
        f.write(f"{v}\t{n}\n")
    m = re.search(rb"function MGo\(e,n,r\)\{.{0,6000}", data, re.S)
    f.write("\n== API-error -> assistant error message mapper MGo() (first 6000 chars)\n")
    f.write(m.group(0).decode("utf8", "replace") if m else "NOT FOUND")
    f.write("\n")

# 5. strings about hook runtime contract
pats = [rb"CLAUDE_CODE_SESSIONEND_HOOKS_TIMEOUT_MS", rb"exit code 2", rb"Hook output does not start with \{",
        rb"CLAUDE_ENV_FILE", rb"CLAUDE_PROJECT_DIR", rb"CLAUDE_EFFORT\b", rb"hook_event_name:\"StopFailure\"",
        rb"Hook cancelled", rb"timed out", rb"TOOL_HOOK_EXECUTION_TIMEOUT_MS", rb"blocking error"]
with open(os.path.join(OUT, "hook-env-and-exit-strings.txt"), "w") as f:
    f.write(f"# claude {ver}\n")
    for p in pats:
        hits = [m.start() for m in re.finditer(p, data)][:4]
        for h in hits:
            ctx = data[max(0, h - 350): h + 350].decode("utf8", "replace").replace("\n", " ")
            f.write(f"== {p.decode()} @{h}\n{ctx}\n\n")
print("ok", ver, len(events or []), "events")
