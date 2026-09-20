"""Render SECTION.md from SECTION.tmpl.md, pulling every example out of captures/.
Re-run: python3 docs/probes/2026-09-14-schemas/agent-sdk-mcp/build_section.py

Faithfulness rule: for every JSON excerpt the UNTRIMMED object is first re-serialized in the capture
file's own style and asserted to be a byte-substring of the capture line it came from; only then is
it trimmed. Trims are marked: a cut string ends in "...", a cut list has a "..." element, a dict with
keys removed gets a trailing "...": "..." entry. Text excerpts are verbatim line slices; omitted lines
are replaced by a line containing only "...".
"""
import json, pathlib, re, sys

HERE = pathlib.Path(__file__).parent
CAP = HERE / "captures"
REL = "docs/probes/2026-09-14-schemas/agent-sdk-mcp/"
E = "..."

STYLES = {"py": {"separators": (", ", ": ")}, "compact": {"separators": (",", ":")}}

def dump(o, style, ascii_):
    return json.dumps(o, ensure_ascii=ascii_, **STYLES[style])

def verified(obj, raw, style):
    for a in (True, False):
        if dump(obj, style, a) in raw:
            return a
    sys.exit(f"FAITHFULNESS CHECK FAILED ({style}): {dump(obj, style, False)[:200]} not in capture line {raw[:200]}")

def cut(x, s=110, n=None):
    if isinstance(x, str):
        return x if len(x) <= s else x[:s] + E
    if isinstance(x, list):
        items = [cut(v, s, n) for v in x]
        return items if n is None or len(items) <= n else items[:n] + [E]
    if isinstance(x, dict):
        return {k: cut(v, s, n) for k, v in x.items()}
    return x

def pick(d, keys):
    out = {k: v for k, v in d.items() if k in keys}
    if len(out) < len(d):
        out[E] = E
    return out

def drop(d, keys):
    out = {k: v for k, v in d.items() if k not in keys}
    if len(out) < len(d):
        out[E] = E
    return out

def lines(path):
    return (CAP / path).read_text().splitlines()

def raw_stream(scen, pred, direction="in"):
    """[(raw_line, wire_obj)] from an SDK scenario, CLI<->SDK objects."""
    out = []
    for l in lines(f"{scen}/raw-stream.jsonl"):
        rec = json.loads(l)
        if rec["_dir"] == direction and pred(rec["line"]):
            out.append((l, rec["line"]))
    return out

def show(pairs_and_transforms, style):
    """pairs_and_transforms: [(raw_line, obj, transform)] -> text block, one JSON per line."""
    rows = []
    for raw, obj, tf in pairs_and_transforms:
        a = verified(obj, raw, style)
        rows.append(dump(tf(obj), style, a))
    return "\n".join(rows)

def req(o, sub):
    return o.get("type") == "control_request" and o["request"].get("subtype") == sub

def mcp_method(o, m):
    return req(o, "mcp_message") and o["request"]["message"].get("method") == m

def text_slice(path, patterns=None, start=None, end=None, width=None):
    ls = lines(path)
    if patterns is None:
        sel = ls[start:end]
    else:
        keep = [i for i, l in enumerate(ls) if any(re.search(p, l) for p in patterns)]
        sel, prev = [], None
        for i in keep:
            if prev is not None and i != prev + 1:
                sel.append(E)
            sel.append(ls[i]); prev = i
    if width:
        sel = [l if len(l) <= width else l[:width] + E for l in sel]
    return "\n".join(sel)

def region(path, start_re, end_re, width=None):
    """Verbatim contiguous lines from the first line matching start_re through the next matching end_re."""
    ls = lines(path)
    i = next(k for k, l in enumerate(ls) if re.search(start_re, l))
    j = next(k for k in range(i + 1, len(ls)) if re.search(end_re, ls[k]))
    sel = ls[i:j + 1]
    if width:
        sel = [l if len(l) <= width else l[:width] + E for l in sel]
    return "\n".join(sel)

X = {}

# ---------------- package / options ----------------
X["install"] = text_slice("introspect/sdk-install.txt", width=160)
X["options_sig"] = text_slice("introspect/options-signature.txt", patterns=[
    r"^dataclasses", r"^  (tools|allowed_tools|system_prompt|mcp_servers|strict_mcp_config|permission_mode|resume|session_id|max_turns|disallowed_tools|model|cwd|cli_path|settings|env|can_use_tool|hooks|include_partial_messages|fork_session|setting_sources|skills|effort):"], width=230)
X["options_doc"] = text_slice("introspect/options-source.txt", patterns=[
    r"^    tools: ", r"Specify the base set", r"``\[\]`` \(empty list\)", r"^    allowed_tools: ", r"auto-allowed without prompting", r"To restrict which tools are available at all",
    r"^    can_use_tool: ", r"It is \*not\*", r"invoked for tool calls already permitted", r"``permission_mode`` \(e.g.", r"never reach a prompt",
    r"^    setting_sources: ", r"^    strict_mcp_config: ", r"only use MCP servers passed via", r"ignoring all other MCP configurations"])
X["argv_locked"] = region("locked/meta.json", r'^  "argv": \[', r'^  \],', width=200)
X["shadow_warning"] = text_slice("locked/meta.json", patterns=[r"CanUseToolShadowedWarning"], width=400)
X["mcp_source"] = text_slice("introspect/mcp-server-source.txt", patterns=[
    r"^def tool\(", r"^    name: str,$", r"^    description: str,$", r"^    input_schema: type \| dict", r"^    annotations: _McpToolAnnotations", r"^\) -> Callable",
    r"^def create_sdk_mcp_server\(", r"^    name: str, version: str", r"^\) -> McpSdkServerConfig", r"jsonschema.validate", r"Input validation error", r'"isError": result.get',
    r"except Exception as e:", r"return _tool_error_result\(str\(e\)\)", r"McpSdkServerConfig\(type=\"sdk\""])

# ---------------- control protocol handshake ----------------
init_out = raw_stream("locked", lambda o: req(o, "initialize"), "out")[0]
X["cp_initialize"] = show([(init_out[0], init_out[1], lambda o: o)], "py")
init_in = raw_stream("locked", lambda o: o.get("type") == "control_response" and "commands" in json.dumps(o))[0]
def tf_init_resp(o):
    r = o["response"]["response"]
    keep = pick(r, ["commands", "agents", "models", "account", "pid", "current_permission_mode", "hooks_applied", "analytics_disabled", "remote_control_available", "session_state"])
    keep = cut(keep, 90, 1)
    return {"type": o["type"], "response": {"subtype": o["response"]["subtype"], "request_id": o["response"]["request_id"], "response": keep}}
X["cp_initialize_resp"] = show([(init_in[0], init_in[1], tf_init_resp)], "py")

# ---------------- system/init ----------------
si = raw_stream("locked", lambda o: o.get("type") == "system" and o.get("subtype") == "init")[0]
X["system_init_locked"] = show([(si[0], si[1], lambda o: cut(o, 90, 3))], "py")
sb = raw_stream("basic", lambda o: o.get("type") == "system" and o.get("subtype") == "init")[0]
def tf_basic_tools(o):
    t = o["tools"]
    return {"type": o["type"], "subtype": o["subtype"], "tools": t[:33] + [E] + t[-5:], "mcp_servers": o["mcp_servers"], "plugins": o["plugins"], "apiKeySource": o["apiKeySource"], E: E}
X["system_init_basic"] = show([(sb[0], sb[1], tf_basic_tools)], "py")

# ---------------- assistant / user / result ----------------
a_think = raw_stream("locked", lambda o: o.get("type") == "assistant" and o["message"]["content"][0]["type"] == "thinking")[0]
a_text = raw_stream("locked", lambda o: o.get("type") == "assistant" and o["message"]["content"][0]["type"] == "text")[0]
a_tool = raw_stream("locked", lambda o: o.get("type") == "assistant" and o["message"]["content"][0]["type"] == "tool_use" and o["message"]["content"][0]["name"] == "mcp__shepherd__kill_session")[0]
def tf_asst(o):
    m = dict(o["message"]); m["usage"] = pick(m["usage"], ["input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens", "service_tier"])
    return cut({**o, "message": m}, 60)
X["assistant"] = show([(a_think[0], a_think[1], tf_asst), (a_text[0], a_text[1], tf_asst), (a_tool[0], a_tool[1], tf_asst)], "py")

u_ok = raw_stream("locked", lambda o: o.get("type") == "user" and "killed ses_a1" in json.dumps(o))[0]
u_err = raw_stream("locked", lambda o: o.get("type") == "user" and "max_children_per_session" in json.dumps(o))[0]
u_raise = raw_stream("locked", lambda o: o.get("type") == "user" and "handler exploded" in json.dumps(o))[0]
u_val = raw_stream("locked", lambda o: o.get("type") == "user" and "Input validation error" in json.dumps(o))[0]
u_deny = raw_stream("deny", lambda o: o.get("type") == "user")[0]
X["user_tool_results"] = show([(p[0], p[1], lambda o: o) for p in (u_ok, u_err, u_raise, u_val, u_deny)], "py")

r_ok = raw_stream("basic", lambda o: o.get("type") == "result")[0]
def tf_result(o):
    o = dict(o)
    o["usage"] = pick(o["usage"], ["input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens", "service_tier"])
    o["subagent_stats"] = pick(o["subagent_stats"], ["spawned", "max_depth"])
    return o
X["result_success"] = show([(r_ok[0], r_ok[1], tf_result)], "py")
r_int = raw_stream("interrupt", lambda o: o.get("type") == "result" and o["subtype"] != "success")[0]
r_intp = raw_stream("interrupt_pending_approval", lambda o: o.get("type") == "result" and o["subtype"] != "success")[0]
tf_result_short = lambda o: drop(o, ["usage", "modelUsage", "subagent_stats", "fast_mode_state", "fast_mode_disabled_reason"])
X["result_interrupted"] = show([(r_int[0], r_int[1], tf_result_short), (r_intp[0], r_intp[1], tf_result_short)], "py")
X["result_parsed"] = "\n".join(l if len(l) < 700 else l[:700] + E for l in lines("locked/messages.jsonl") if '"_class": "ResultMessage"' in l)

# ---------------- other stream objects ----------------
rl = raw_stream("resume", lambda o: o.get("type") == "rate_limit_event")[0]
st = raw_stream("interrupt", lambda o: o.get("type") == "system" and o.get("subtype") == "status")[0]
tt = raw_stream("interrupt", lambda o: o.get("type") == "system" and o.get("subtype") == "thinking_tokens")[0]
se = raw_stream("interrupt", lambda o: o.get("type") == "stream_event" and o["event"]["type"] == "content_block_delta")[0]
X["other_stream"] = show([(p[0], p[1], lambda o: cut(o, 80)) for p in (rl, st, tt, se)], "py")

# ---------------- SDK MCP over the control protocol ----------------
m_init = raw_stream("locked", lambda o: mcp_method(o, "initialize"))[0]
m_init_r = raw_stream("locked", lambda o: o.get("type") == "control_response" and '"serverInfo"' in json.dumps(o), "out")[0]
m_list = raw_stream("locked", lambda o: mcp_method(o, "tools/list"))[0]
m_list_r = raw_stream("locked", lambda o: o.get("type") == "control_response" and '"inputSchema"' in json.dumps(o), "out")[0]
X["sdk_mcp_handshake"] = show([(m_init[0], m_init[1], lambda o: o), (m_init_r[0], m_init_r[1], lambda o: o), (m_list[0], m_list[1], lambda o: o), (m_list_r[0], m_list_r[1], lambda o: o)], "py")
calls = []
for name, marker in (("kill_session", "killed ses_a1"), ("fail_tool", "max_children_per_session"), ("raise_tool", "handler exploded"), ("spawn_session", "Input validation error")):
    rq = raw_stream("locked", lambda o, n=name, mk=marker: mcp_method(o, "tools/call") and o["request"]["message"]["params"]["name"] == n and (n != "spawn_session" or "task" not in o["request"]["message"]["params"]["arguments"]))[0]
    rs = raw_stream("locked", lambda o, mk=marker: o.get("type") == "control_response" and mk in json.dumps(o), "out")[0]
    calls += [(rq[0], rq[1], lambda o: o), (rs[0], rs[1], lambda o: o)]
X["sdk_mcp_calls"] = show(calls, "py")
X["handler_calls"] = "\n".join(lines("locked/handler-calls.jsonl"))

# ---------------- can_use_tool ----------------
cu = raw_stream("locked", lambda o: req(o, "can_use_tool"))[0]
cu_r = raw_stream("locked", lambda o: o.get("type") == "control_response" and '"behavior"' in json.dumps(o), "out")[0]
cd = raw_stream("deny", lambda o: req(o, "can_use_tool"))[0]
cd_r = raw_stream("deny", lambda o: o.get("type") == "control_response" and '"behavior"' in json.dumps(o), "out")[0]
X["can_use_tool_wire"] = show([(cu[0], cu[1], lambda o: o), (cu_r[0], cu_r[1], lambda o: o), (cd[0], cd[1], lambda o: o), (cd_r[0], cd_r[1], lambda o: o)], "py")
X["can_use_tool_callback"] = "\n".join(lines("locked/can-use-tool.jsonl"))

# ---------------- Bash in the spec-configured master ----------------
b_use = raw_stream("basic", lambda o: o.get("type") == "assistant" and o["message"]["content"][0].get("name") == "Bash")[0]
b_hook = raw_stream("basic", lambda o: req(o, "hook_callback") and o["request"]["input"].get("tool_name") == "Bash" and o["request"]["input"]["hook_event_name"] == "PreToolUse")[0]
b_res = raw_stream("basic", lambda o: o.get("type") == "user" and '"hi"' in json.dumps(o))[0]
b_cu = raw_stream("basic", lambda o: req(o, "can_use_tool"))
X["bash_master"] = show([(b_use[0], b_use[1], lambda o: {"type": o["type"], "message": {"content": o["message"]["content"]}, E: E}),
                         (b_hook[0], b_hook[1], lambda o: cut(o, 100)),
                         (b_res[0], b_res[1], lambda o: o)], "py")
X["bash_master_cu_count"] = f"can_use_tool control_requests in basic/raw-stream.jsonl: {len(b_cu)} (tool_name(s): {sorted({json.loads(r)['line']['request']['tool_name'] for r, _ in b_cu})})"

# ---------------- hooks inside the SDK master ----------------
hk_pre = raw_stream("locked", lambda o: req(o, "hook_callback") and o["request"]["input"]["hook_event_name"] == "PreToolUse")[0]
hk_post = raw_stream("locked", lambda o: req(o, "hook_callback") and o["request"]["input"]["hook_event_name"] == "PostToolUse")[0]
hk_fail = raw_stream("locked", lambda o: req(o, "hook_callback") and o["request"]["input"]["hook_event_name"] == "PostToolUseFailure")[0]
X["sdk_hooks"] = show([(hk_pre[0], hk_pre[1], lambda o: o)] + [(p[0], p[1], lambda o: {"type": o["type"], "request": {"subtype": o["request"]["subtype"], "callback_id": o["request"]["callback_id"], "input": drop(o["request"]["input"], ["session_id", "transcript_path", "cwd", "prompt_id"]), E: E}, E: E}) for p in (hk_post, hk_fail)], "py")

# ---------------- interrupt ----------------
i_req = raw_stream("interrupt", lambda o: req(o, "interrupt"), "out")[0]
i_resp = raw_stream("interrupt", lambda o: o.get("type") == "control_response" and "still_queued" in json.dumps(o))[0]
i_asst = raw_stream("interrupt", lambda o: o.get("type") == "assistant" and o["message"]["content"][0]["type"] == "text" and "one\ntwo" in o["message"]["content"][0]["text"])[0]
i_user = raw_stream("interrupt", lambda o: o.get("type") == "user")[0]
X["interrupt_wire"] = show([(i_req[0], i_req[1], lambda o: o), (i_resp[0], i_resp[1], lambda o: o),
                            (i_asst[0], i_asst[1], lambda o: cut(pick(o, ["type", "message", "aborted", "session_id"]), 60)),
                            (i_user[0], i_user[1], lambda o: o)], "py")
X["interrupt_meta"] = text_slice("interrupt/meta.json", patterns=[r'"interrupt"', r'"after_stream_events"', r'"since_query_s"', r'"returned"', r'"call_s"', r'"interrupt_when_idle"', r'^  \},'])
p_cu = raw_stream("interrupt_pending_approval", lambda o: req(o, "can_use_tool"))[0]
p_int = raw_stream("interrupt_pending_approval", lambda o: req(o, "interrupt"), "out")[0]
p_cancel = raw_stream("interrupt_pending_approval", lambda o: o.get("type") == "control_cancel_request")[0]
p_users = raw_stream("interrupt_pending_approval", lambda o: o.get("type") == "user")
X["interrupt_pending"] = show([(p_cu[0], p_cu[1], lambda o: o), (p_int[0], p_int[1], lambda o: o), (p_cancel[0], p_cancel[1], lambda o: o)]
                              + [(u[0], u[1], lambda o: cut(o, 160)) for u in p_users[:2]], "py")
X["interrupt_pending_cb"] = "\n".join(lines("interrupt_pending_approval/can-use-tool.jsonl"))
X["slow_approval_cb"] = "\n".join(lines("slow_approval/can-use-tool.jsonl")) + "\n" + text_slice("slow_approval/meta.json", patterns=[r'"turn_wall_s"', r'"status"'])

# ---------------- resume / fork ----------------
X["resume_meta"] = region("resume/meta.json", r'^  "turns": \[', r'^  \],') + "\n" + region("resume/meta.json", r'^  "first_session_id"', r'^  \],')
X["resume_argv"] = "\n".join(sorted({re.sub(r".*(\"--resume=[^\"]+\"|\"--fork-session\").*", r"\1", l).strip() for l in lines("resume/meta.json") if "--resume=" in l or "--fork-session" in l}))
X["resume_other_cwd"] = region("resume_other_cwd/meta.json", r'^  "turns": \[', r'^  \],') + "\n" + region("resume_other_cwd/meta.json", r'^  "resume_from_b"', r'^  \},') + "\n" + region("resume_other_cwd/meta.json", r'^  "transcript_dirs_after_resume_from_b"', r'^  \},')
rtx = [l for l in lines("resume/transcript-e6fed1a4-c0b1-41d6-be36-b445e606c5a1.jsonl") if '"session_context"' in l or '"skill_listing"' in l or '"deferred_tools_delta"' in l]
def tf_tx(o):
    return cut(pick(o, ["type", "attachment", "sessionId", "entrypoint", "version"]), 100, 4)
X["resume_transcript_attachments"] = show([(l, json.loads(l), tf_tx) for l in rtx], "compact")

# ---------------- isolation ----------------
X["isolation_meta"] = text_slice("isolation/meta.json", patterns=[r'--setting-sources']) + "\n...\n" + region("isolation/meta.json", r'^  "isolation_results"', r'^  \},')
iso_inits = raw_stream("isolation", lambda o: o.get("type") == "system" and o.get("subtype") == "init")
X["isolation_init"] = show([(iso_inits[0][0], iso_inits[0][1], lambda o: {"type": o["type"], "subtype": o["subtype"], "mcp_servers": o["mcp_servers"], "plugins": o["plugins"], "skills": cut(o["skills"], 40, 3), "memory_paths": o["memory_paths"], E: E})], "py")
X["syscli"] = text_slice("locked-syscli/meta.json", patterns=[r'"cli_path"', r'"claude_version"', r'"status"'])
sys_init = raw_stream("locked-syscli", lambda o: o.get("type") == "system" and o.get("subtype") == "init")[0]
X["syscli_init"] = show([(sys_init[0], sys_init[1], lambda o: pick(o, ["tools", "mcp_servers", "apiKeySource", "claude_code_version"]))], "py")

# ---------------- stdio MCP (tier-2) ----------------
wire = [json.loads(l) for l in lines("stdio-mcp/mcp-wire.jsonl")]
start = wire[0]
X["stdio_meta"] = text_slice("stdio-mcp/meta.txt", width=300)
def raw_wire(pred):
    return [w for w in wire[1:] if pred(w)]
def wire_show(ws, tf=lambda o: o):
    rows = []
    for w in ws:
        o = json.loads(w["raw"])
        style = "compact" if w["raw"].startswith('{"method"') or w["raw"].startswith('{"jsonrpc":"') else "py"
        a = verified(o, w["raw"], style)
        rows.append(f"[{w['_dir']:3s}] " + dump(tf(o), style, a))
    return "\n".join(rows)
X["stdio_handshake"] = wire_show(raw_wire(lambda w: any(k in w["raw"] for k in ('"initialize"', '"notifications/initialized"', '"tools/list"', '"serverInfo"', '"tools": ['))))
X["stdio_calls"] = wire_show(raw_wire(lambda w: '"tools/call"' in w["raw"] or ('"id": ' in w["raw"] and '"id": 0' not in w["raw"] and '"id": 1,' not in w["raw"])))
sstart = {k: start[k] for k in ("_dir", "pid", "cwd", "env_values_allowlisted", "secret_env_names_present_values_not_logged", "ancestry")}
raw_start = lines("stdio-mcp/mcp-wire.jsonl")[0]
for k in sstart:  # each "key": value pair must exist byte-for-byte in the capture line
    if dump({k: start[k]}, "py", True)[1:-1] not in raw_start:
        sys.exit(f"FAITHFULNESS CHECK FAILED for start record key {k}")
env_mcp = [e for e in start["env_names"] if e.startswith(("CLAUDE", "ANTHROPIC", "MCP", "PROBE", "SHP"))]
X["stdio_start"] = dump({**sstart, "env_names": env_mcp + [E], E: E}, "py", True)
stream = lines("stdio-mcp/stream.jsonl")
def stream_pick(pred):
    return [(l, json.loads(l)) for l in stream if pred(json.loads(l))]
s_init = stream_pick(lambda o: o.get("type") == "system" and o.get("subtype") == "init")[0]
s_users = stream_pick(lambda o: o.get("type") == "user")
s_pd = stream_pick(lambda o: o.get("type") == "system" and o.get("subtype") == "permission_denied")[0]
s_res = stream_pick(lambda o: o.get("type") == "result")[0]
X["stdio_stream"] = show([(s_init[0], s_init[1], lambda o: pick(o, ["type", "subtype", "tools", "mcp_servers", "apiKeySource", "claude_code_version"]))]
                         + [(u[0], u[1], lambda o: pick(o, ["type", "message", "tool_use_result"])) for u in s_users]
                         + [(s_pd[0], s_pd[1], lambda o: o), (s_res[0], s_res[1], lambda o: pick(o, ["type", "subtype", "is_error", "permission_denials", "terminal_reason"]))], "compact")
hooks = lines("stdio-mcp/hooks.jsonl")
def hook_line(ev, tool):
    for l in hooks:
        o = json.loads(l)
        if o["_event"] == ev and o["payload"]["tool_name"] == tool:
            return l, o
    sys.exit(f"no hook {ev} {tool}")
hsel = [hook_line("PreToolUse", "mcp__probe__echo_note"), hook_line("PostToolUse", "mcp__probe__echo_note"),
        hook_line("PostToolUseFailure", "mcp__probe__fail_note"), hook_line("PostToolUseFailure", "mcp__probe__rpc_error_note"),
        hook_line("PermissionRequest", "mcp__probe__danger_note")]
X["stdio_hooks"] = show([(l, o, (lambda o: {**o, "_ancestry": o["_ancestry"][:3] + [E]}) if i == 0 else
                          (lambda o: {"_event": o["_event"], "_claude_version": o["_claude_version"], "payload": drop(o["payload"], ["session_id", "transcript_path", "cwd", "prompt_id"]), E: E}))
                         for i, (l, o) in enumerate(hsel)], "compact")
X["stdio_hook_counts"] = "\n".join(f"{ev}: {sum(1 for l in hooks if json.loads(l)['_event'] == ev)}" for ev in ("PreToolUse", "PostToolUse", "PostToolUseFailure", "PermissionRequest", "PermissionDenied"))
X["stdio_cc10x"] = text_slice("stdio-mcp/debug-cc10x-lines.txt", patterns=[r"cc10x \(enabled=false", r"0 enabled, 1 disabled", r"Registered 0 hooks from 0 plugins"])
X["settings_sha"] = "\n".join(lines("user-settings-sha256-before.txt") + lines("user-settings-sha256-after.txt") + lines("stdio-mcp/user-settings-sha256-before.txt") + lines("stdio-mcp/user-settings-sha256-after.txt"))
X["auth_context"] = "\n".join(lines("auth-context.txt"))
r_seat = raw_stream("basic", lambda o: o.get("type") == "result")[0]
X["seat_model_usage"] = show([(r_seat[0], r_seat[1], lambda o: pick(o, ["total_cost_usd", "modelUsage"]))], "py")
X["seat_account"] = show([(init_in[0], init_in[1], lambda o: {"type": o["type"], "response": {"response": {"account": o["response"]["response"]["account"], E: E}, E: E}})], "py")

tmpl = (HERE / "SECTION.tmpl.md").read_text()
missing = set(re.findall(r"\{\{(\w+)\}\}", tmpl)) - set(X)
if missing:
    sys.exit(f"template references unknown excerpts: {missing}")
out = re.sub(r"\{\{(\w+)\}\}", lambda m: X[m.group(1)], tmpl)
(HERE / "SECTION.md").write_text(out)
print("SECTION.md written,", len(out), "bytes,", len(X), "excerpts")
