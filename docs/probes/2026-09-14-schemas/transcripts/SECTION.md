# Claude Code transcripts and on-disk session state

Surface: the files Claude Code writes under `~/.claude/projects/`, the live-session registry under
`~/.claude/sessions/`, `~/.claude.json` project entries, and `claude agents --json`.

All live runs used `claude --version` = `2.1.270 (Claude Code)`, model `claude-haiku-4-5-20251001`,
throwaway working directories from `mktemp -d /tmp/shp-schemas-*`, and a timeout on every run. Each
throwaway directory had `.claude/settings.json` with `"enabledPlugins": {"cc10x@cc10x": false}`.
**No cc10x hook fired in any throwaway session.** Every `stop_hook_summary` in this surface's own throwaways shows `hookCount: 1`, which is the
probe's own Stop hook. The one copied sibling session (`copies/-tmp-shp-hooks-effort-7yb7myuc/…`) shows `hookCount: 2`, and both entries are the sibling hooks probe's own capture scripts. The copied transcripts contain no `hook_*`
attachments and no mention of cc10x.

Audit note (2026-09-14): every example below was traced to its source line in `captures/` or `copies/`, and all of them match byte-for-byte apart from the `...` trims. Counts marked "probe dirs" come from `captures/real-transcripts-stats.json`, which was regenerated at 15:35:39Z. Sibling probes kept writing `-tmp-shp-*` dirs, so the probe-dir counts in this file are the ones in that snapshot. User-data counts did not drift.

Evidence folder: `docs/probes/2026-09-14-schemas/transcripts/`
- `captures/` holds raw outputs. Every run has a `*-meta.txt` that records `claude --version`, the argv and the exit code.
- `copies/<project-dir>/` holds copies of the throwaway transcripts and sidecars, byte-for-byte except for the privacy pass below.
- **Privacy pass** (`redact_copies.py`): Claude Code writes the account email into every session, in the
  `session_context` attachment. It also writes account and organization UUIDs into `bridge-session` entries.
  Both were replaced in place with `<redacted-email>` and `<redacted-uuid>`. The user's own transcripts were
  only **counted** (`stats_real_transcripts.py`). No content from them appears here.

Re-run everything (about $0.60 of haiku usage, about 12 minutes including the binary grep):
```
cd /root/Shepherd && P=docs/probes/2026-09-14-schemas/transcripts && bash $P/probe_lifecycle.sh && bash $P/probe_slug.sh \
 && bash $P/probe_registry.sh && bash $P/probe_registry_interactive.sh && bash $P/probe_fork_live.sh \
 && python3 $P/probe_claude_json.py > $P/captures/claude-json-shape.txt \
 && python3 $P/stats_real_transcripts.py > $P/captures/real-transcripts-stats.json && python3 $P/stats_registry.py > $P/captures/registry-stats.json && date -u +%FT%TZ > $P/captures/real-transcripts-stats.generated_at.txt && bash $P/probe_binary_metadata.sh
```
Helpers: `outline.py` prints a one-line-per-entry outline of a transcript. `excerpt.py FILE N MAX` prints raw line N with long strings cut and marked `...`. Every example below was produced with `excerpt.py` or copied from a capture file.

---

## Project directory layout (`~/.claude/projects/<slug>/`)

- **Produced by:** Claude Code 2.1.270 (all entrypoints: `cli` and `sdk-cli`/`-p`)
- **Consumed by:** §6 `EngineAdapter.locate_transcript` (line 436), §6 engine matrix (line 549), §7 "subagent rows … read from the transcript on demand" (line 609), §12 Fleet subagent lines (line 1870), D24, M1 (workspace→session→subagent tree)
- **Probe:** `docs/probes/2026-09-14-schemas/transcripts/probe_lifecycle.sh` (steps `main bg workflow`). Re-run: `bash docs/probes/2026-09-14-schemas/transcripts/probe_lifecycle.sh main bg workflow`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `captures/layout-listing.txt`)
```text
claude_version: 2.1.270 (Claude Code)
# find ~/.claude/projects/-tmp-shp-schemas-tx-blIf90-work (throwaway probe project dir)
d     4096 ./0141fab3-8bf8-4b69-be1f-89552ccfce5d
f   211715 ./0141fab3-8bf8-4b69-be1f-89552ccfce5d.jsonl
d     4096 ./0141fab3-8bf8-4b69-be1f-89552ccfce5d/subagents
f    87274 ./0141fab3-8bf8-4b69-be1f-89552ccfce5d/subagents/agent-a4388d337bf8a9397.jsonl
f      176 ./0141fab3-8bf8-4b69-be1f-89552ccfce5d/subagents/agent-a4388d337bf8a9397.meta.json
...
f    75012 ./518c280f-3791-4571-ae9a-f002c8f3b33c/subagents/workflows/wf_edb19b07-a69/agent-aff491fda998b3fe0.jsonl
f      149 ./518c280f-3791-4571-ae9a-f002c8f3b33c/subagents/workflows/wf_edb19b07-a69/agent-aff491fda998b3fe0.meta.json
f      315 ./518c280f-3791-4571-ae9a-f002c8f3b33c/subagents/workflows/wf_edb19b07-a69/journal.jsonl
f      205 ./518c280f-3791-4571-ae9a-f002c8f3b33c/workflows/scripts/shp-probe-wf-wf_edb19b07-a69.js
f     1211 ./518c280f-3791-4571-ae9a-f002c8f3b33c/workflows/wf_edb19b07-a69.json
...
d     4096 ./memory
# find /tmp/claude-0/-tmp-shp-schemas-tx-blIf90-work (per-session task output dir)
l ./0141fab3-8bf8-4b69-be1f-89552ccfce5d/tasks/a4388d337bf8a9397.output -> /root/.claude/projects/-tmp-shp-schemas-tx-blIf90-work/0141fab3-8bf8-4b69-be1f-89552ccfce5d/subagents/agent-a4388d337bf8a9397.jsonl
f ./518c280f-3791-4571-ae9a-f002c8f3b33c/tasks/w1x94eiqe.output ->
```

| Path (relative to `~/.claude/projects/<slug>/`) | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `<sessionId>.jsonl` | JSONL file | always (every persisted session) | 83 in probe dirs, 14 in user dirs | Main transcript. File name = session UUID |
| `<sessionId>/subagents/agent-<agentId>.jsonl` | JSONL | sometimes (Agent tool used) | 6 probe, 9 user | `agentId` = 17 hex chars. Nested agents (spawnDepth 2) are stored flat in the same folder (user data: `parentAgentId` present 3×) |
| `<sessionId>/subagents/agent-<agentId>.meta.json` | JSON | always next to each agent jsonl | 6 probe, 9 user (plus 1 probe and 17 user under `workflows/wf_*/`) | See "Subagent .meta.json" |
| `<sessionId>/subagents/workflows/wf_<runId>/agent-<agentId>.{jsonl,meta.json}` | JSONL + JSON | sometimes (Workflow tool used) | 1 probe run, 2 user runs | `runId` is the pattern `wf_[0-9a-f]{8}-[0-9a-f]{3}` |
| `<sessionId>/subagents/workflows/wf_<runId>/journal.jsonl` | JSONL | always per workflow run | 1 probe, 2 user | See "Workflow journal" |
| `<sessionId>/workflows/wf_<runId>.json` | JSON | sometimes (after a run completes) | 1 probe, 1 user (2 runs, 1 file: the running workflow has none yet) | Run summary |
| `<sessionId>/workflows/scripts/<name>-wf_<runId>.js` | JS | always per workflow run | 1 probe, 2 user | Persisted script |
| `<sessionId>/custom-title.json` | JSON | sometimes | 0 probe, 1 user | `{"customTitle": <str>}`. Seen only next to a session renamed with `/rename` (the tmux surface covers /rename) |
| `<sessionId>/tool-results/*.txt` | text | sometimes | 0 probe, 19 files in 3 user sessions | Large tool outputs spilled to disk |
| `memory/` (per project dir) | dir | always created (empty in probes) | user: 4 `*.md` | Auto-memory, not per session |
| `/tmp/claude-<uid>/<slug>/<sessionId>/tasks/<taskId>.output` | symlink or file | sometimes (background agent/workflow) | symlink → agent jsonl; plain file for workflows | Outside `~/.claude`. `<uid>` = `0` here |

**Variants and edge cases:**
- A compaction ran an internal subagent. Its `SubagentStop.agent_transcript_path` (`.../subagents/agent-a4e465b8cdd4fb220.jsonl`) **did not exist** afterwards (`captures/hooks-lifecycle.jsonl`). Do not assume every SubagentStop path exists.
- Only the Agent tool writes a `toolUseId` in meta. Workflow agents do not (see below).
- The D24 glob `~/.claude/projects/*.jsonl`, taken literally, matches **no** files: main transcripts sit one directory down, at `projects/<slug>/<sessionId>.jsonl`. The auditor's re-run found 0 matches. Subagent transcripts are deeper still (`<slug>/<sid>/subagents/agent-*.jsonl` and `<slug>/<sid>/subagents/workflows/wf_*/agent-*.jsonl`), so even `projects/*/*.jsonl` misses them.

**Spec alignment:** aligned for the main transcript location (line 549). The spec says nothing about the nested `subagents/workflows/wf_*/` tree or the `/tmp/claude-<uid>` task-output tree. Line 609 and line 1870 need both trees (see the subagent and workflow sections).

## Project directory slug rule

- **Produced by:** Claude Code 2.1.270
- **Consumed by:** §6 `locate_transcript` (line 436), D22 cwd→repo binding (only if a path is derived from cwd), M1
- **Probe:** `docs/probes/2026-09-14-schemas/transcripts/probe_slug.sh`. Re-run: `bash docs/probes/2026-09-14-schemas/transcripts/probe_slug.sh`
- **Status:** verified live 2026-09-14 (9 cwds. The derived rule matched 9 of 9)

**Real example** (trimmed; full capture: `captures/slug-results.jsonl`)
```json
{"derived_rule": "-tmp-shp-schemas-slug-6V4NfF-wwwwwwww...wwwwwwww-vg1k1m", "derived_equals_real": true, "claude_version": "2.1.270 (Claude Code)", "session_id": "2f6ceb71-54d8-48af-a925-5be3e19418a3", "cwd": "/tmp/shp-schemas-slug.6V4NfF/wwwwwwww...wwwwwwww", "cwd_chars": 201, "cwd_utf8_bytes": 201, "real_dir": "-tmp-shp-schemas-slug-6V4NfF-wwwwwwww...wwwwwwww-vg1k1m", "real_len": 207, ... "naive_len": 201, "naive_equals_real": false, ...}
{"derived_rule": "-tmp-shp-schemas-slug-6V4NfF-emoji----x", "derived_equals_real": true, "claude_version": "2.1.270 (Claude Code)", "session_id": "f8b76831-d92e-49ae-8427-54b430af8cd6", "cwd": "/tmp/shp-schemas-slug.6V4NfF/emoji-😀-x", "cwd_chars": 38, "cwd_utf8_bytes": 41, "real_dir": "-tmp-shp-schemas-slug-6V4NfF-emoji----x", "real_len": 39, "naive_rule": "-tmp-shp-schemas-slug-6V4NfF-emoji---x", "naive_len": 38, "naive_equals_real": false, "transcript_cwd_field": "/tmp/shp-schemas-slug.6V4NfF/emoji-😀-x"}
{"derived_rule": "-tmp-shp-schemas-slug-6V4NfF--n-c-d----", "derived_equals_real": true, "claude_version": "2.1.270 (Claude Code)", "session_id": "822dae80-45e1-4e67-896d-3afe66b42822", "cwd": "/tmp/shp-schemas-slug.6V4NfF/ünïcødé-日本", "cwd_chars": 39, "cwd_utf8_bytes": 47, "real_dir": "-tmp-shp-schemas-slug-6V4NfF--n-c-d----", "real_len": 39, "naive_rule": "-tmp-shp-schemas-slug-6V4NfF--n-c-d----", "naive_len": 39, "naive_equals_real": true, "transcript_cwd_field": "/tmp/shp-schemas-slug.6V4NfF/ünïcødé-日本"}
```

**The rule, derived from these captures:**
```
s = cwd with every UTF-16 code unit outside [A-Za-z0-9] replaced by "-"
slug = s                                        if len(s) <= 200
slug = s[:200] + "-" + base36(abs(javaStringHash(cwd)))   otherwise
```
Here `javaStringHash` is `h = 31*h + codeUnit` in signed 32-bit arithmetic over the UTF-16 code units of the raw cwd, and `base36` uses the alphabet `0-9a-z`.

| Input case | cwd chars | Real dir length | Naive rule equal? | Derived rule equal? |
|---|---|---|---|---|
| `dots.and_under_scores` | 50 | 50 | yes | yes |
| `with space` | 39 | 39 | yes | yes |
| `ünïcødé-日本` (BMP non-ASCII) | 39 | 39 | yes (one `-` per char) | yes |
| `a--b..c` | 36 | 36 | yes (runs of `-` are not collapsed) | yes |
| `UPPER.Case-9` | 41 | 41 | yes (case kept) | yes |
| exactly 200 chars | 200 | 200 | yes | yes |
| 201 chars | 201 | 207 | **no** | yes (`-vg1k1m`) |
| 265 chars, two long components | 265 | 207 | **no** | yes (`-b9qyzo`) |
| `emoji-😀-x` (astral) | 38 | 39 | **no** (emoji becomes 2 dashes) | yes |

**Variants and edge cases:**
- The slug is lossy (`a.b` and `a_b` both become `a-b`). Two cwds can share one project dir. Always read `cwd` from the entries; do not reverse the slug.
- The hash suffix has variable length (6 chars in both captures; base36 of a 31-bit value is at most 6 chars).
- The transcript's `cwd` field keeps the raw path, including Unicode and spaces.

**Spec alignment:** aligned. The spec never states a slug rule; `locate_transcript(engine_session_id)` can glob `~/.claude/projects/*/<id>.jsonl` and never needs one. If a plan derives the directory from cwd, the naive rule is wrong for cwds over 200 UTF-16 units and for astral characters (`captures/slug-results.jsonl`).

## Transcript entry: common envelope

- **Produced by:** Claude Code 2.1.270
- **Consumed by:** §6 `parse_transcript_delta` (line 437), §8 transcript-tail classifier (line 1022), D24, M1/M2
- **Probe:** `docs/probes/2026-09-14-schemas/transcripts/probe_lifecycle.sh`. Re-run: `bash docs/probes/2026-09-14-schemas/transcripts/probe_lifecycle.sh main`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `copies/-tmp-shp-schemas-tx-blIf90-work/0141fab3-8bf8-4b69-be1f-89552ccfce5d.jsonl` line 3, 0-based)
```json
{"parentUuid":null,"isSidechain":false,"promptId":"b842cda1-7298-40d9-87a4-1966249ed00c","type":"user","message":{"role":"user","content":"Step 1: use the Agent tool (subagent_type general-purpose, description..."},"uuid":"32b48930-be22-4ea9-ab0f-16c5ed2796e8","timestamp":"2026-09-14T15:07:08.158Z","permissionMode":"default","promptSource":"sdk","userType":"external","entrypoint":"sdk-cli","cwd":"/tmp/shp-schemas-tx.blIf90/work","sessionId":"0141fab3-8bf8-4b69-be1f-89552ccfce5d","version":"2.1.270","gitBranch":"HEAD"}
```

Two families of entries exist:
1. **Conversation entries** (`user`, `assistant`, `attachment`, `system`) carry the full envelope below.
2. **Metadata entries** (`ai-title`, `custom-title`, `agent-name`, `last-prompt`, `queue-operation`, `mode`, `permission-mode`, `atis-latch`, `bridge-session`, `cost-state`, `frame-link`, `file-history-snapshot`, `file-history-delta`, `artifact-*`) carry only `type`, `sessionId` (absent on `file-history-*`) and their own fields. They have **no `uuid`, `timestamp` or `parentUuid`**, except `queue-operation`, `frame-link` and `file-history-delta`, which have `timestamp`.

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `type` | string | always | 19 top-level types in user data, 15 in probes (see below) | `system` and `attachment` add a subtype level |
| `uuid` | string (UUID) | always on conversation entries | | Preserved across `--fork-session` (see Fork) |
| `parentUuid` | string \| null | always on conversation entries | null on first entry and on `compact_boundary` | Chain order ≠ file order |
| `timestamp` | string ISO-8601 ms `Z` | always on conversation entries | | |
| `sessionId` | string (UUID) | always (except file-history-*) | Subagent entries carry the **parent's** sessionId | |
| `isSidechain` | bool | always on conversation entries | main: false 5643/5643; subagent + workflow files: true 3243/3243 (user data) | |
| `agentId` | string | sometimes | on every entry of subagent files | |
| `cwd` | string | always on conversation entries | raw path | |
| `version` | string | always on conversation entries | `2.1.270` | |
| `gitBranch` | string | always on conversation entries | `HEAD` (non-git dir) | |
| `entrypoint` | string | always on conversation entries | `cli` (interactive), `sdk-cli` (`-p`) | Distinguishes interactive from print mode |
| `userType` | string | always on conversation entries | `external` | |
| `slug` | string | sometimes | e.g. `zesty-splashing-lightning` | A random 3-word session nickname. It appears after compaction and on some interactive entries. **Not** the project dir slug |
| `session_id` | string | sometimes | equal to `sessionId` (11/11 in interactive probe) | Seen on interactive (`cli`) sessions |

**Entry type counts** (`captures/real-transcripts-stats.json`: snapshot at the time in `captures/real-transcripts-stats.generated_at.txt`. User dirs = 12,270 entries in 14 main + 26 agent files. The counts drift because live sessions keep writing. Probe dirs = all `-tmp-shp-*` throwaways, including sibling probes):
`assistant` 4345 · `user` 2477 · `attachment` (27 subtypes) 1,789 · `queue-operation` 462 · `last-prompt` 443 · `mode` 425 · `permission-mode` 425 · `bridge-session` 406 · `agent-name` 264 · `custom-title` 264 · `system/turn_duration` 217 · `file-history-snapshot` 217 · `atis-latch` 182 · `ai-title` 167 · `frame-link` 55 · `file-history-delta` 49 · `system/stop_hook_summary` 39 · `artifact-autoreact-ledger` 14 · `system/bridge_status` 8 · `cost-state` 7 · `system/local_command` 6 · `artifact-comment-monitor` 4 · `system/compact_boundary` 3 · `system/away_summary` 1 · `system/informational` 1. **`summary` 0 · `pr-link` 0.** Malformed lines: 0.

**Variants and edge cases:**
- Only 56% of entries (6,822 of 12,270) are `user` or `assistant`. The rest are metadata and attachments. `attachment/prompt_snapshot` entries embed the full system prompt and tool list, so a one-turn `-p` session is about 167 KB.
- Metadata entries are **re-appended** repeatedly, after every turn and on resume. Observed in the probe: the same `ai-title` appeared at lines 0, 16, 26 and 49 of one file. The binary's merge-policy table marks `ai-title`, `custom-title`, `agent-name`, `summary`, `pr-link`, `mode`, `permission-mode` and `bridge-session` as `last-wins`, `last-prompt` and `file-history-*` as `boundary-cleared`, and `frame-link` as `accumulate` (`captures/binary-metadata-table.txt`). **Readers must take the last occurrence.** The same table names types never observed here: `continued-in`, `fork-context-ref`, `content-replacement`, `ended-by-model`, `tag`, `relocated`, `agent-color`, `agent-setting`, `history-suppression`, `attribution-snapshot`, `marble-origami-*`.
- A metadata entry can appear **before** the first `user` entry: `ai-title` at line 0 (`0141fab3…jsonl`), `custom-title` at line 0 (`8b86e691…jsonl`).

**Spec alignment:** line 1022 says the verdict model reads the "last ~20 entries". In the user data, 44% of entries (5,448 of 12,270) are neither `user` nor `assistant`: 27.6% are metadata-only types, 14.6% are attachments and 2.2% are `system`. Some attachments are the size of a system prompt. Metadata is also re-appended at turn end, so it clusters in the tail. In the 15 copied throwaway main transcripts, the last 20 lines hold only 2 to 9 `user`/`assistant` entries. The tail must filter by `type` before counting (`captures/real-transcripts-stats.json`, `copies/*/*.jsonl`).

## Transcript entry: `assistant`

- **Produced by:** Claude Code 2.1.270
- **Consumed by:** §7 `session.model` / `effort` (line 666), §8 classifier, §12 fleet row "opus-5", D24, M1/M2
- **Probe:** `probe_lifecycle.sh` (steps `main effort`). Re-run: `bash docs/probes/2026-09-14-schemas/transcripts/probe_lifecycle.sh main effort`
- **Status:** partially verified. The haiku envelope was verified live 2026-09-14. Top-level `effort` was seen only on a sonnet throwaway copied from the sibling hooks probe (`captures/effort-copy-provenance.txt`). No opus throwaway was run; opus values come from user-data counts only.

**Real example** (trimmed; full capture: `copies/-tmp-shp-schemas-tx-blIf90-work/0141fab3-8bf8-4b69-be1f-89552ccfce5d.jsonl` line 19)
```json
{"parentUuid":"5c71260f-85e3-4541-ae9f-1b28b3903b6a","isSidechain":false,"message":{"model":"claude-haiku-4-5-20251001","id":"msg_011Cf3YJjCUY6gKrhVLBVgC4","type":"message","role":"assistant","content":[{"type":"tool_use","id":"toolu_01AjU2TvSydb1THCnRCcYCLQ","name":"Agent","input":{"description":"probe child","subagent_type":"general-purpose","prompt":"Reply with exactly the word PONG and nothing else."},"caller":{"type":"direct"}}],"container":null,"stop_reason":"tool_use","stop_sequence":null,"stop_details":null,"usage":{"input_tokens":10,"cache_creation_input_tokens":7853,"cache_read_input_tokens":13607,"output_tokens":406,"output_tokens_details":{"thinking_tokens":229},"server_tool_use":{"web_search_requests":0,"web_fetch_requests":0},"service_tier":"standard","cache_creation":{"ephemeral_1h_input_tokens":7853,"ephemeral_5m_input_tokens":0},"inference_geo":"not_available","iterations":[...],"speed":"standard"},"diagnostics":null,"context_management":null},"wireToolInputs":{...},"apiBlockIndex":1,"requestId":"req_011Cf3YJiZXWo9S8uYzXXRb7","type":"assistant","uuid":"25575054-0003-4bfa-8fd3-ffb3adeb823c","timestamp":"2026-09-14T15:07:11.965Z","perTurnEffort":null,"userType":"external","entrypoint":"sdk-cli","cwd":"/tmp/shp-schemas-tx.blIf90/work","sessionId":"0141fab3-8bf8-4b69-be1f-89552ccfce5d","version":"2.1.270","gitBranch":"HEAD"}
```
With top-level `effort` (sonnet throwaway; full capture: `copies/-tmp-shp-hooks-effort-7yb7myuc/5c59934b-3bd1-43ab-9506-a6a16f581034.jsonl` line 24):
```json
{"parentUuid":"9990e296-2225-43ed-9048-f40119d9f202","isSidechain":false,"message":{"model":"claude-sonnet-5","id":"msg_011Cf3ZGdVyrLrVns9PKFoK8","type":"message","role":"assistant","content":[{"type":"text","text":"DONE"}],"container":null,"stop_reason":"end_turn",...},"apiBlockIndex":0,"requestId":"req_011Cf3ZGcvzzThSm4f1HAaoP","type":"assistant","uuid":"6ba36219-5dca-4e65-a026-bafd34cd2509","timestamp":"2026-09-14T15:19:47.452Z","effort":"low","perTurnEffort":null,"userType":"external","entrypoint":"sdk-cli","cwd":"/tmp/shp-hooks-effort-7yb7myuc","sessionId":"5c59934b-3bd1-43ab-9506-a6a16f581034","version":"2.1.270","gitBranch":"HEAD"}
```

| Field | Type | Presence (user data, n=4345) | Observed values | Notes |
|---|---|---|---|---|
| `message.model` | string | always | `claude-opus-5` 4331, `claude-sonnet-5` 9, `<synthetic>` 5; probes add `claude-haiku-4-5-20251001` | Full model id, not an alias |
| `message.id` | string | always | `msg_…`; a UUID on `<synthetic>` | **One API message is split across several entries**, one per content block (same `message.id` and `requestId`, increasing `apiBlockIndex`, `usage` repeated) |
| `message.content[]` | array | always | exactly 1 block per entry: `thinking` \| `text` \| `tool_use` | `thinking.thinking` is `""` (signature only) |
| `message.stop_reason` | string \| null | always | `tool_use` 3333, `end_turn` 305, null 702, `stop_sequence` 5 | null on non-final blocks of interactive streams |
| `message.usage.{input_tokens, output_tokens, cache_creation_input_tokens, cache_read_input_tokens, cache_creation, service_tier, inference_geo}` | numbers / object / string | always (4345) | | Repeated on each block of one message. Summing per entry overcounts |
| `message.usage.{iterations, server_tool_use, speed}` | array / object / string | sometimes (3643) | | null or absent on `<synthetic>` |
| `message.usage.output_tokens_details` | object | sometimes (1574) | `{"thinking_tokens":N}` | |
| `effort` | string | sometimes (4340/4345 user, **0/319 haiku entries in probe dirs**) | `high` 4307, `medium` 33; probe dirs `high` 10, `low` 4 (all 14 on `claude-sonnet-5`) | **Top-level. Absent on haiku even with `--effort low`** (`captures/effort-meta.txt`) and absent on `<synthetic>` |
| `perTurnEffort` | null | sometimes (2273) | always `null` observed | Separate from `effort` |
| `requestId` | string | almost always (4343) | `req_…` | |
| `apiBlockIndex` | number | sometimes (2273) | 0,1,2… | |
| `wireToolInputs` | object | sometimes (1099) | map tool_use id → input | |
| `attributionAgent` / `attributionSkill` / `attributionPlugin` / `attributionMcpServer` / `attributionMcpTool` | string | sometimes (1417/863/288/33/33) | `<redacted>` | On subagent and skill-driven entries |
| `error`, `isApiErrorMessage`, `apiErrorStatus` | string / bool / number | sometimes (4/5/3) | see `<synthetic>` | |
| `isAbortedMidStream` | bool | sometimes (1) | | |

**Variants and edge cases:** per-block splitting means "the last assistant entry" can be a lone `thinking` block. To get the final text, group by `message.id`.

**Spec alignment:** line 666 says "`effort` is a top-level transcript field; `model` is at `message.model`". This is aligned for opus and sonnet. For haiku, top-level `effort` is **never written**, even when `--effort low` is passed (`copies/-tmp-shp-schemas-tx-blIf90-work/667257d2-9430-4714-a8b1-fb07a95ae0bf.jsonl`), so `session.effort` must stay nullable. `message.model` can be `<synthetic>`, which is not a model.

## Transcript entry: `<synthetic>` assistant

- **Produced by:** Claude Code 2.1.270 (client-side, no API call)
- **Consumed by:** §8 mechanical stop reasons (`rate_limit`, `auth_failed`), §7 `session.model`, D24, M2
- **Probe:** `probe_lifecycle.sh` step `synthetic` (unknown model) and `probe_fork_live.sh` (fork of a mid-turn session). Re-run: `bash docs/probes/2026-09-14-schemas/transcripts/probe_lifecycle.sh synthetic`
- **Status:** verified live 2026-09-14 (`model_not_found`, fork filler). `rate_limit` and `authentication_failed` counted in user data only.

**Real example** (trimmed; full capture: `copies/-tmp-shp-schemas-tx-blIf90-work/89b8683f-b2ea-4874-934a-9cadbb6cb276.jsonl` line 16)
```json
{"parentUuid":"d409bb38-1d39-4161-b040-f1b1c1e28d1a","isSidechain":false,"type":"assistant","uuid":"eb2fa9c6-7eae-4d94-a71a-58b1d9b082ed","timestamp":"2026-09-14T15:09:10.052Z","message":{"diagnostics":null,"id":"9e60ee5c-53b6-4dd6-a771-1e90f7bb3c8c","container":null,"model":"<synthetic>","role":"assistant","stop_details":null,"stop_reason":"stop_sequence","stop_sequence":"","type":"message","usage":{"output_tokens_details":null,"input_tokens":0,"output_tokens":0,"cache_creation_input_tokens":0,"cache_read_input_tokens":0,"server_tool_use":{"web_search_requests":0,"web_fetch_requests":0},"service_tier":null,"cache_creation":{"ephemeral_1h_input_tokens":0,"ephemeral_5m_input_tokens":0},"inference_geo":null,"iterations":null,"speed":null},"content":[{"type":"text","text":"There's an issue with the selected model (claude-nonexistent..."}],"context_management":null},"requestId":"req_011Cf3YTfcB998zosz95sFUe","error":"model_not_found","isApiErrorMessage":true,"apiErrorStatus":404,"userType":"external","entrypoint":"sdk-cli","cwd":"/tmp/shp-schemas-tx.blIf90/work","sessionId":"89b8683f-b2ea-4874-934a-9cadbb6cb276","version":"2.1.270","gitBranch":"HEAD"}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `message.model` | string | always | `<synthetic>` | |
| `message.stop_reason` | string | always | `stop_sequence` | |
| `message.usage.*` | numbers | always | all 0 | |
| `error` | string \| absent | sometimes | `model_not_found` (probe), `rate_limit` 3, `authentication_failed` 1 (user data) | Machine-readable. Use this, not the text |
| `isApiErrorMessage` | bool | always on synthetic | true (API errors), false (fork filler "No response requested.") | |
| `apiErrorStatus` | number \| null | sometimes | 404 (probe), numbers ×3 in user data | |
| `effort`, `perTurnEffort`, `apiBlockIndex` | — | never | | |

**Variants and edge cases:** a fork of a mid-turn session synthesizes `"No response requested."` with `isApiErrorMessage:false` (see Fork). A classifier must not treat every `<synthetic>` entry as an error.

**Spec alignment:** aligned with §8's claim that mechanical reasons are machine-readable, since `error` carries `rate_limit` and `authentication_failed`. The spec does not name the `<synthetic>` marker or the `error` field.

## Transcript entry: `user`

- **Produced by:** Claude Code 2.1.270
- **Consumed by:** §7 `brief` (line 664), §8 classifier, M1/M2
- **Probe:** `probe_lifecycle.sh` (`main bg`). Re-run: `bash docs/probes/2026-09-14-schemas/transcripts/probe_lifecycle.sh main bg`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `copies/-tmp-shp-schemas-tx-blIf90-work/0141fab3-8bf8-4b69-be1f-89552ccfce5d.jsonl` lines 20 and 33)
```json
{"parentUuid":"25575054-0003-4bfa-8fd3-ffb3adeb823c","isSidechain":false,"promptId":"b842cda1-7298-40d9-87a4-1966249ed00c","type":"user","message":{"role":"user","content":[{"tool_use_id":"toolu_01AjU2TvSydb1THCnRCcYCLQ","type":"tool_result","content":[{"type":"text","text":"Async agent launched successfully. (This tool result is internal metad..."}]}]},"uuid":"3395f91e-c746-414a-996f-bac590870388","timestamp":"2026-09-14T15:07:12.340Z","toolUseResult":{"isAsync":true,"status":"async_launched","agentId":"a4388d337bf8a9397","description":"probe child","resolvedModel":"claude-haiku-4-5-20251001","prompt":"Reply with exactly the word PONG and nothing else.","outputFile":"/tmp/claude-0/-tmp-shp-schemas-tx-blIf90-work/0141fab3-8bf8-4b69-be1f-...","canReadOutputFile":true},"sourceToolAssistantUUID":"25575054-0003-4bfa-8fd3-ffb3adeb823c","userType":"external","entrypoint":"sdk-cli","cwd":"/tmp/shp-schemas-tx.blIf90/work","sessionId":"0141fab3-8bf8-4b69-be1f-89552ccfce5d","version":"2.1.270","gitBranch":"HEAD"}
{"parentUuid":"9958eb57-0222-46a6-825c-27cd9fefb2b9","isSidechain":false,"promptId":"b522145f-c441-4adf-b34c-aed11dc38f4d","type":"user","message":{"role":"user","content":"<task-notification>\n<task-id>a4388d337bf8a9397</task-id>\n<tool-use-i..."},"uuid":"f0e5636b-fcf9-4060-b62d-74fa7ae27e4d","timestamp":"2026-09-14T15:07:15.932Z","permissionMode":"default","origin":{"kind":"task-notification"},"promptSource":"sdk","queueSkipAttachments":true,"userType":"external","entrypoint":"sdk-cli","cwd":"/tmp/shp-schemas-tx.blIf90/work","sessionId":"0141fab3-8bf8-4b69-be1f-89552ccfce5d","version":"2.1.270","gitBranch":"HEAD"}
```

| Field | Type | Presence (user data, n=2477) | Observed values | Notes |
|---|---|---|---|---|
| `message.content` | string \| array | always | string (prompt, task-notification, compact summary) or `[tool_result]` / `[text]` | |
| `promptId` | string | always | | Shared by every entry of one turn. Also present in hook payloads |
| `toolUseResult` | object \| string | sometimes (1601) | Agent async: `{isAsync,status:"async_launched",agentId,…}`; Workflow: `{status:"async_launched",taskId,taskType:"local_workflow",runId,transcriptDir,scriptPath,…}`; string on interruption | Tool-specific |
| `sourceToolAssistantUUID` | string | sometimes (2174) | | Links a tool_result to its assistant entry |
| `origin.kind` | string | sometimes (226) | `human` 212, `task-notification` 10, `coordinator` 2, `peer` 2 | Only on prompt-type user entries |
| `promptSource` | string | sometimes (230) | `queued` 192, `typed` 20, `system` 11, `sdk` 7 | |
| `permissionMode` | string | sometimes (230) | | |
| `isCompactSummary`, `isVisibleInTranscriptOnly` | bool | sometimes (3/3) | true | Compaction |
| `isMeta` | bool | sometimes (31) | | e.g. fork filler "Continue from where you left off." |
| `toolDenialKind` | string | sometimes (19) | `interrupted` (probe) | |
| `interruptedMessageId`, `queueSkipAttachments`, `classifierMetaLines`, `mcpMeta`, `sourceToolUseID`, `toolEndsTurn`, `turnCompanion` | various | sometimes (5/9/54/10/11/15/10) | `<redacted>` | Not probed individually |

**Variants and edge cases:** a background-agent completion is a `user` entry whose `content` is a `<task-notification>` string (see queue-operation). Only `origin.kind` separates it from a human prompt.

**Spec alignment:** see `last-prompt` for `brief`.

## Transcript entry: `attachment`

- **Produced by:** Claude Code 2.1.270
- **Consumed by:** §8 transcript tail (line 1022) as noise to filter; nothing in the spec consumes attachments. M2
- **Probe:** `probe_lifecycle.sh main`. Re-run: `bash docs/probes/2026-09-14-schemas/transcripts/probe_lifecycle.sh main`
- **Status:** partially verified. The envelope and the `model`, `environment` and `prompt_snapshot` subtypes were verified live 2026-09-14. This surface's copies contain 11 subtypes, all `-tmp-shp-*` probe dirs contain 20, and 31 distinct subtypes appear once user data is included. The rest are counted from user data only.

**Real example** (trimmed; full capture: `copies/-tmp-shp-schemas-tx-blIf90-work/0141fab3-8bf8-4b69-be1f-89552ccfce5d.jsonl` line 5)
```json
{"parentUuid":"64b6acc0-a884-46f6-9432-7d88e55d8778","isSidechain":false,"attachment":{"type":"model","identity":{"modelId":"claude-haiku-4-5-20251001","marketingName":"Haiku 4.5","knowledgeCutoff":"February 2025"},"text":"You are powered by the model named Haiku 4.5. The exact model ID is cl..."},"type":"attachment","uuid":"9746158c-8690-4d9c-95f5-dbcc12a7d9d4","timestamp":"2026-09-14T15:07:08.156Z","rendered":[{"content":"<system-reminder>\nYou are powered by the model named Haiku 4.5. The e..."}],"userType":"external","entrypoint":"sdk-cli","cwd":"/tmp/shp-schemas-tx.blIf90/work","sessionId":"0141fab3-8bf8-4b69-be1f-89552ccfce5d","version":"2.1.270","gitBranch":"HEAD"}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `attachment.type` | string | always | user data: `total_tokens_reminder` 1101, `task_reminder` 149, `prompt_snapshot` 80, `environment` 48, `remote_session_change` 44, `date` 44, `model` 43, `session_context` 40, `skill_listing` 40, `deferred_tools_delta` 39, `auto_mode` 27, `edited_text_file` 24, `agent_listing_delta` 21, `queued_command` 17, `structured_output` 15, `command_permissions` 11, `compact_file_reference` 8, `date_change` 8, `deferred_tools_record` 7, `file` 4, `silent_turn_reminder` 4, `hook_additional_context` 3, `hook_success` 3, `invoked_skills` 3, `mcp_instructions_delta` 3, `read_truncation_notice` 2, `hook_system_message` 1; probes add `hook_cancelled`, `hook_non_blocking_error`, `instructions`, `plan_mode` | |
| `attachment.*` | object | always | `model`: `{identity{modelId,marketingName,knowledgeCutoff},text}`; `environment`: `{snapshot{workingDirectory,isWorktree,isGitRepo,additionalWorkingDirectories,platform,shell,osVersion}}`; `prompt_snapshot`: `{systemPrompt[],tools[],cliPrefix}` | Per-subtype |
| `rendered` | array | sometimes (absent on `prompt_snapshot`) | `[{content:"<system-reminder>…"}]` | |

**Variants and edge cases:** `session_context` holds the **account email** and `bridge-session` holds account and org UUIDs. Anything that copies or displays transcripts must redact them (§13).

**Spec alignment:** not described in the spec. The spec's "never return a raw transcript entry to the browser" rule (line 2107) covers this.

## Transcript entry: `system` (stop_hook_summary, turn_duration, others)

- **Produced by:** Claude Code 2.1.270
- **Consumed by:** §8 stop classification (turn boundaries), M2
- **Probe:** `probe_lifecycle.sh main` (stop_hook_summary) and `probe_registry_interactive.sh` (turn_duration). Re-run: `bash docs/probes/2026-09-14-schemas/transcripts/probe_registry_interactive.sh`
- **Status:** partially verified. `stop_hook_summary`, `turn_duration`, `compact_boundary` and `local_command` were verified live 2026-09-14. `away_summary`, `bridge_status` and `informational` are counted in user data only.

**Real example** (trimmed; full captures: `copies/-tmp-shp-schemas-tx-blIf90-work/0141fab3-8bf8-4b69-be1f-89552ccfce5d.jsonl` line 31, `copies/-tmp-shp-schemas-regint-KD6xG3-work/2efd1f5f-1b93-481a-8469-0f589a48d7ae.jsonl` line 39)
```json
{"parentUuid":"6c5c2237-9ae3-4878-8070-03683a9bb2b1","isSidechain":false,"type":"system","subtype":"stop_hook_summary","hookCount":1,"hookInfos":[{"command":"python3 /root/Shepherd/docs/probes/2026-09-14-schemas/transcripts/hook...","durationMs":161}],"hookErrors":[],"hookAdditionalContext":[],"preventedContinuation":false,"stopReason":"","hasOutput":false,"level":"suggestion","timestamp":"2026-09-14T15:07:15.925Z","uuid":"9958eb57-0222-46a6-825c-27cd9fefb2b9","toolUseID":"74fb939e-c2f2-4f5b-aad4-0b2ae06bc66f","userType":"external","entrypoint":"sdk-cli","cwd":"/tmp/shp-schemas-tx.blIf90/work","sessionId":"0141fab3-8bf8-4b69-be1f-89552ccfce5d","version":"2.1.270","gitBranch":"HEAD"}
{"parentUuid":"fc761860-8b74-4b7b-bef9-888d793459cc","isSidechain":false,"type":"system","subtype":"turn_duration","durationMs":22830,"messageCount":18,"timestamp":"2026-09-14T15:16:40.423Z","uuid":"8d8429e4-9335-414d-8b7f-c78da28eab22","isMeta":false,"userType":"external","entrypoint":"cli","cwd":"/tmp/shp-schemas-regint.KD6xG3/work","sessionId":"2efd1f5f-1b93-481a-8469-0f589a48d7ae","version":"2.1.270","gitBranch":"HEAD"}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `subtype` | string | always | `turn_duration` 217, `stop_hook_summary` 39, `local_command` 6, `bridge_status` 8, `compact_boundary` 3, `away_summary` 1, `informational` 1 | |
| `stop_hook_summary.{hookCount,hookInfos[{command,durationMs}],hookErrors,hookAdditionalContext,preventedContinuation,stopReason,hasOutput,level,toolUseID}` | mixed | always on that subtype | `level: suggestion` | Written **only when a Stop hook is configured**. In `-p` runs it is the turn-end marker |
| `turn_duration.{durationMs,messageCount,isMeta}` | numbers / bool | always on that subtype | | **Written by interactive (`cli`) sessions only.** None was written by a `-p` run. A `-p` fork copies the target's `turn_duration` entries with `entrypoint` rewritten to `sdk-cli`, and the uuid stays the same as in the target (`copies/-tmp-shp-schemas-fork-*`) |
| `turn_duration.pendingBackgroundAgentCount` / `pendingWorkflowCount` | number | sometimes (6/2 of 217) | `<number>` | A turn can end while agents are still running |
| `level` | string | sometimes | `suggestion`, `info` | |

**Variants and edge cases:** the turn-end marker depends on the entrypoint. Interactive sessions write `turn_duration`. Print-mode sessions write nothing unless a Stop hook exists.

**Spec alignment:** not described in the spec. §8 relies on the `Stop` hook for turn ends, which is consistent.

## Compaction entries (`system/compact_boundary` + compact summary `user`)

- **Produced by:** Claude Code 2.1.270 (`/compact`)
- **Consumed by:** §8 `context_exhausted` (line 966), §8 transcript tail, `shepherd recompute`, M2
- **Probe:** `probe_lifecycle.sh compact`. Re-run: `bash docs/probes/2026-09-14-schemas/transcripts/probe_lifecycle.sh main compact`
- **Status:** verified live 2026-09-14 (manual trigger). `auto` trigger counted once in user data only.

**Real example** (trimmed; full capture: `copies/-tmp-shp-schemas-tx-blIf90-work/0141fab3-8bf8-4b69-be1f-89552ccfce5d.jsonl` lines 52 and 53)
```json
{"parentUuid":null,"logicalParentUuid":"b64bcef1-3451-4327-95f4-6bdeab16ec77","isSidechain":false,"type":"system","subtype":"compact_boundary","content":"Conversation compacted","isMeta":false,"timestamp":"2026-09-14T15:09:06.987Z","uuid":"6568005a-8565-49b6-8724-2d1d7f37e81b","level":"info","compactMetadata":{"trigger":"manual","preTokens":23010,"durationMs":17516,"preservedSegment":{"headUuid":"b92cb616-7df8-4b00-9021-8cdb2d42b86a","anchorUuid":"469d71ee-11a6-44bd-bca6-64295b2ed4fb","tailUuid":"a0f601a0-f071-4fc6-b3fa-969600f80e5c"},"preservedMessages":{"anchorUuid":"469d71ee-11a6-44bd-bca6-64295b2ed4fb","uuids":[...],"allUuids":[...]},"postTokens":1873,"cumulativeDroppedTokens":21137},"userType":"external","entrypoint":"sdk-cli","cwd":"/tmp/shp-schemas-tx.blIf90/work","sessionId":"0141fab3-8bf8-4b69-be1f-89552ccfce5d","version":"2.1.270","gitBranch":"HEAD","slug":"zesty-splashing-lightning"}
{"parentUuid":"6568005a-8565-49b6-8724-2d1d7f37e81b","isSidechain":false,"promptId":"8be54374-8f32-46f9-9fe2-1378da857b9f","type":"user","message":{"role":"user","content":"This session is being continued from a previous conversation..."},"isVisibleInTranscriptOnly":true,"isCompactSummary":true,"uuid":"469d71ee-11a6-44bd-bca6-64295b2ed4fb","timestamp":"2026-09-14T15:09:06.985Z","userType":"external","entrypoint":"sdk-cli","cwd":"/tmp/shp-schemas-tx.blIf90/work","sessionId":"0141fab3-8bf8-4b69-be1f-89552ccfce5d","version":"2.1.270","gitBranch":"HEAD","slug":"zesty-splashing-lightning"}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `parentUuid` | null | always | null | Chain restarts. `logicalParentUuid` points to the pre-compaction leaf |
| `compactMetadata.trigger` | string | always | `manual` (2 user + 2 probe), `auto` (1 user) | |
| `compactMetadata.{preTokens,postTokens,durationMs,cumulativeDroppedTokens}` | number | always (3/3) | | |
| `compactMetadata.{preservedSegment,preservedMessages}` | object | always (3/3) | uuids | |
| `compactMetadata.preCompactDiscoveredTools` | array | sometimes (2/3) | | |
| summary `user.isCompactSummary` | bool | always right after the boundary | true | Content starts "This session is being continued from a previous conversation" |

**Variants and edge cases:** compaction happens **in the same file with the same sessionId** (probe: `0141fab3…` went from 47 to 63 lines). No `summary`-type entry was written by `/compact`, and the user data has 0 of them. The hook side showed `SessionStart` with `source:"compact"` between `PreCompact` and `PostCompact` (`captures/hooks-lifecycle.jsonl`).

**Spec alignment:** aligned. §8 uses `PreCompact{auto}` and the transcript carries a matching `compactMetadata.trigger`.

## Title and name entries: `ai-title`, `custom-title`, `agent-name` (title sources)

- **Produced by:** Claude Code 2.1.270
- **Consumed by:** §7.1 title / `title_source` (lines 700–736), D29, §18 title write-back probe, M1 (engine title), M3 (rename)
- **Probe:** `probe_lifecycle.sh main named` and `probe_registry_interactive.sh`. Re-run: `bash docs/probes/2026-09-14-schemas/transcripts/probe_lifecycle.sh main named`
- **Status:** verified live 2026-09-14 for `ai-title` (unnamed session) and for `custom-title` + `agent-name` (`--name`). What `/rename` writes is out of scope here (tmux surface).

**Real example** (full captures: `copies/-tmp-shp-schemas-tx-blIf90-work/0141fab3-8bf8-4b69-be1f-89552ccfce5d.jsonl` line 0; `copies/-tmp-shp-schemas-tx-blIf90-work/8b86e691-5e1a-46b3-9bc0-bc7dc694abb3.jsonl` lines 0–1)
```json
{"type":"ai-title","aiTitle":"Agent probe and notes","sessionId":"0141fab3-8bf8-4b69-be1f-89552ccfce5d"}
{"type":"custom-title","customTitle":"shp probe named","sessionId":"8b86e691-5e1a-46b3-9bc0-bc7dc694abb3"}
{"type":"agent-name","agentName":"shp probe named","sessionId":"8b86e691-5e1a-46b3-9bc0-bc7dc694abb3"}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `aiTitle` | string | always on `ai-title` | "Agent probe and notes", "Probe prompt truncation test" | Generated by Claude Code |
| `customTitle` | string | always on `custom-title` | the `--name` value | |
| `agentName` | string | always on `agent-name` | same value as `customTitle` in every observation (264 = 264 in user data) | |
| per main file | — | — | user data (14 files): ai-title only 12, custom-title + agent-name only 1, all three 1. Probe dirs: ai-title only 54, custom + agent-name only 4, none 25 | |

**Title sources, observed:**
- **Unnamed session** (`-p` or interactive): `ai-title` is written during the first turn and re-appended after later turns. In file order it can come before the first `user` entry (line 0 of `0141fab3…`). One-shot "Reply with exactly OK." sessions got one too (all 9 slug-probe sessions).
- **`--name "<n>"`** (`-p` or interactive): `custom-title` + `agent-name` are written at line 0, **and no `ai-title` is generated** (`8b86e691…`, `2efd1f5f…`). The hooks `SessionStart` and `UserPromptSubmit` carry `session_title: "<n>"`. The registry file has `name` and `nameSource:"user"`.
- **`/rename`** writes the sidecar `<sessionId>/custom-title.json` `{"customTitle": …}` (1 user file; tmux surface).
- User interactive sessions launched with `--remote-control <name>` show `nameSource:"derived"` in the registry (`captures/registry-stats.json`).
- The session that failed before any model reply (`89b8683f…`, model_not_found) wrote **no title**. 25 probe-dir transcripts have no title entry at all; they are mostly other surfaces' probes and were not examined individually.

**Spec alignment:**
- spec line 713–714 says "Claude Code writes `ai-title` entries … so a generated title arrives for free, including for `attached` sessions". In reality a session started with `--name` gets `custom-title` + `agent-name` and **no** `ai-title`. This held for both named throwaways: `-p` `8b86e691…` and interactive `2efd1f5f…`. In user data, 1 of the 2 main files that have `custom-title` also has no `ai-title`; the other has all three (`copies/-tmp-shp-schemas-tx-blIf90-work/8b86e691-5e1a-46b3-9bc0-bc7dc694abb3.jsonl`, `captures/real-transcripts-stats.json`). Unnamed sessions, attached ones included, do get `ai-title`. The spec never mentions `custom-title`, which is Claude Code's user-title channel. It should map to a title source rather than being ignored.
- spec line 724 says "the candidate mechanism is appending an `ai-title` entry". In reality `ai-title` is the engine-generated channel. A user-supplied name in Claude Code is `custom-title` (`--name` writes it, and the registry then reports `nameSource:"user"`). The `/rename` sidecar is also `custom-title.json`. The binary's merge table gives each type its own `last-wins` policy (`captures/binary-metadata-table.txt`). It does not show which of the two wins when both exist, and no write-back was attempted. Appending `ai-title` would therefore at best record a user title in the engine-title channel, and it may be hidden by an existing `custom-title`. The candidate mechanism targets the wrong entry type.

## `last-prompt` entry

- **Produced by:** Claude Code 2.1.270
- **Consumed by:** §7 `session.brief` for attached sessions (line 664), Appendix A (line 2446), M1
- **Probe:** `probe_lifecycle.sh longprompt resume`. Re-run: `bash docs/probes/2026-09-14-schemas/transcripts/probe_lifecycle.sh longprompt`
- **Status:** verified live 2026-09-14

**Real example** (full captures: `copies/-tmp-shp-schemas-tx-blIf90-work/6fcb72cd-b6f3-4acd-a43d-6c7e3e89bd28.jsonl` line 15; `copies/-tmp-shp-schemas-tx-blIf90-work/0141fab3-8bf8-4b69-be1f-89552ccfce5d.jsonl` lines 37 and 45)
```json
{"type":"last-prompt","lastPrompt":"Line one of a deliberately long probe prompt. Line two continues so that the prompt is well over two hundred characters long, which lets us see whether last-prompt truncates it and what happens to new…","leafUuid":"57a7dd84-7465-4259-99c7-26e6a45ca551","sessionId":"6fcb72cd-b6f3-4acd-a43d-6c7e3e89bd28"}
{"type":"last-prompt","lastPrompt":"Step 1: use the Agent tool (subagent_type general-purpose, description 'probe ch...","leafUuid":"bd49cc8c-e6db-498c-b676-c0a47e892433","sessionId":"0141fab3-8bf8-4b69-be1f-89552ccfce5d"}
{"type":"last-prompt","lastPrompt":"Reply with exactly RESUMED.","leafUuid":"a0f601a0-f071-4fc6-b3fa-969600f80e5c","sessionId":"0141fab3-8bf8-4b69-be1f-89552ccfce5d"}
```
Input (`captures/longprompt-input.txt`): 269 chars with 2 newlines.

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `lastPrompt` | string | sometimes (440/443 user; 206/208 probe dirs) | length ≤ 201. Truncated as the first 200 chars + `…` (U+2026). User data: 160 values are longer than 200 chars (max 201) and 188 end with `…` | **Newlines are flattened to spaces**. The probe value equals the input's first 200 chars with `\n`→space, plus `…` |
| `leafUuid` | string | always | uuid of the conversation leaf at write time | |

**Variants and edge cases:**
- The value is the **latest human or SDK prompt**. After `--resume … "Reply with exactly RESUMED."` it became `Reply with exactly RESUMED.`. A queued `<task-notification>` prompt did **not** replace it (line 37 still shows the original prompt).
- `last-prompt` without a `lastPrompt` field was observed 3× (user) and 2× (probe dirs).
- **In a `-p` fork it is stale.** Fork `7c27bb7f…` (argv `-p "Reply with exactly FORKED." --resume 0141fab3… --fork-session`) wrote its own `last-prompt` entries at lines 37 and 44, whose `leafUuid`s point at the fork's new entries. Both carry `lastPrompt` = the history's **first** prompt ("Step 1: use the Agent tool…"). They carry neither the fork's own prompt nor the target's then-latest "Reply with exactly RESUMED." (`copies/-tmp-shp-schemas-tx-blIf90-work/7c27bb7f-5390-48b0-8b2e-cf4004113d09.jsonl`, `captures/fork-meta.txt`). A `/compact` local command did not replace it either (`0141fab3…` line 62 still says RESUMED).

**Spec alignment:** spec line 664 and line 2446 say `brief` for attached sessions is "the transcript's `lastPrompt`". In reality `lastPrompt` is the most recent prompt, not the task the session was started with. It is cut to 200 chars + "…" and its newlines become spaces (`copies/-tmp-shp-schemas-tx-blIf90-work/6fcb72cd-b6f3-4acd-a43d-6c7e3e89bd28.jsonl`). A faithful brief needs the first `user` entry with `origin.kind` in {human, absent} and string content, or the `UserPromptSubmit.prompt` hook field.

## `queue-operation` and task-notification entries

- **Produced by:** Claude Code 2.1.270
- **Consumed by:** §12 subagent state (line 1870), §8 `SubagentStop`/`active_subagents`, M1
- **Probe:** `probe_lifecycle.sh main bg`. Re-run: `bash docs/probes/2026-09-14-schemas/transcripts/probe_lifecycle.sh bg`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `copies/-tmp-shp-schemas-tx-blIf90-work/0141fab3-8bf8-4b69-be1f-89552ccfce5d.jsonl` lines 1, 2, 28)
```json
{"type":"queue-operation","operation":"enqueue","timestamp":"2026-09-14T15:07:07.509Z","sessionId":"0141fab3-8bf8-4b69-be1f-89552ccfce5d","content":"Step 1: use the Agent tool (subagent_type general-purpose, description..."}
{"type":"queue-operation","operation":"dequeue","timestamp":"2026-09-14T15:07:07.511Z","sessionId":"0141fab3-8bf8-4b69-be1f-89552ccfce5d"}
{"type":"queue-operation","operation":"enqueue","timestamp":"2026-09-14T15:07:13.811Z","sessionId":"0141fab3-8bf8-4b69-be1f-89552ccfce5d","content":"<task-notification>\n<task-id>a4388d337bf8a9397</task-id>\n<tool-use-id>toolu_01AjU2TvSydb1THCnRCcYCLQ</tool-use-id>\n<output-file>/tmp/claude-0/-tmp-shp-schemas-tx-blIf90-work/0141fab3-8bf8-4b69-be1f-89552ccfce5d/tasks/a4388d337bf8a9397.output</output-file>\n<status>completed</status>\n<summary>Agent \"probe child\" finished</summary>\n<note>A task-notification fires each time this agent stops with no live background children of its own. The user can send it another message and resume it, so the same task-id may notify more than once.</note>\n<result>PONG</result>\n<usage><subagent_tokens>115..."}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `operation` | string | always | `enqueue` 232, `dequeue` 213, `remove` 16, `popAll` 1 (user) | |
| `content` | string | sometimes (on enqueue) | prompt text, or `<task-notification>` XML (36 user, 5 probe) | |
| `reason` | string | sometimes (8 user) | `<redacted>` | |
| task-notification XML tags | text | — | `task-id`, `tool-use-id`, `output-file`, `status` (`completed`), `summary`, `note`, `result`, `usage` | `tool-use-id` equals meta.json `toolUseId` |

**Variants and edge cases:**
- In `-p`, an Agent call without `run_in_background` was still **started in the background** (`result.subagent_stats.requested.unset=1, started_in_background=1`, `captures/main-stdout.jsonl`). Its completion arrived only as a task-notification, **never as a `tool_result`**.
- The note says the same task-id "may notify more than once".
- A notification is also delivered as a `user` entry with `origin.kind:"task-notification"` (see `user`).
- The `-p` stream-json output adds `system/task_started`, `task_updated` (`patch.status:"completed"`) and `task_notification` events that are not in the transcript (`captures/bg-stdout.jsonl`).

**Spec alignment:** spec line 1870 says each subagent line shows "type, description, elapsed, state", and line 609 says the list is read from the transcript. Agent-tool state is readable from the transcript only as free text. No structured field in the subagent `.jsonl` or `.meta.json` records it. It has to be parsed from the `<status>` tag of a `<task-notification>` (queue-operation `content` or `user` entry), taken from a `tool_result` for `toolUseId` (foreground only), or read from `journal.jsonl` / `wf_<runId>.json` for workflow agents (`copies/-tmp-shp-schemas-tx-blIf90-work/0141fab3-8bf8-4b69-be1f-89552ccfce5d.jsonl` line 28). The `SubagentStop` hook's `background_tasks[]` still lists the stopping agent itself as `status:"running"` (`captures/hooks-lifecycle.jsonl` lines 7, 29, 51), so that field is no substitute either.

## Subagent transcript and `.meta.json` (Agent tool)

- **Produced by:** Claude Code 2.1.270
- **Consumed by:** §7 "subagent rows" (line 609), §12 subagent lines (line 1870), `list_subagents` (§11), M1
- **Probe:** `probe_lifecycle.sh main bg`. Re-run: `bash docs/probes/2026-09-14-schemas/transcripts/probe_lifecycle.sh main bg`
- **Status:** verified live 2026-09-14

**Real example** (full captures: `copies/-tmp-shp-schemas-tx-blIf90-work/7515f181-14c5-4540-9107-4f1d1267cf83/subagents/agent-a1a6271c8023a6c65.meta.json`; trimmed first line of `copies/-tmp-shp-schemas-tx-blIf90-work/0141fab3-8bf8-4b69-be1f-89552ccfce5d/subagents/agent-a4388d337bf8a9397.jsonl`)
```json
{"agentType":"general-purpose","description":"probe bg child","toolUseId":"toolu_01KeyyCiTPjwVZLFwG6wEwnp","spawnDepth":1,"requestShape":"background","requestNonInteractive":true}
{"parentUuid":null,"isSidechain":true,"promptId":"b842cda1-7298-40d9-87a4-1966249ed00c","agentId":"a4388d337bf8a9397","type":"user","message":{"role":"user","content":"Reply with exactly the word PONG and nothing else."},"uuid":"dd540906-96b9-4e47-be0b-8bb9ce513cda","timestamp":"2026-09-14T15:07:12.183Z","userType":"external","entrypoint":"sdk-cli","cwd":"/tmp/shp-schemas-tx.blIf90/work","sessionId":"0141fab3-8bf8-4b69-be1f-89552ccfce5d","version":"2.1.270","gitBranch":"HEAD"}
```

| Field (meta.json) | Type | Presence (n=26 user + 7 probe) | Observed values | Notes |
|---|---|---|---|---|
| `agentType` | string | always | `general-purpose`, plugin types (`<plugin>:<name>`), `workflow-subagent` | |
| `description` | string | always | Agent `description`, or the workflow `label` | |
| `toolUseId` | string | sometimes (Agent tool only: 9/9 user, 6/6 probe) | `toolu_…` | Absent on workflow agents |
| `spawnDepth` | number | always | 1, 2 | |
| `parentAgentId` | string | sometimes (3, depth-2 agents) | agentId | |
| `requestShape` | string | always | `background` 8 user / 4 probe; `foreground` 18 user / 3 probe | Our "no run_in_background" call was stored as `background` |
| `requestNonInteractive` | bool | always | true (Agent), false (user workflow agents), true (probe `-p` workflow agent) | |
| `model` | string | sometimes (6 user) | `opus`, `sonnet` | Alias, not a full id. Absent when inherited |
| `workflowPhase` | string | sometimes (workflow agents) | `Ping` (probe) | |

Subagent `.jsonl` entries: every entry has `isSidechain:true`, `agentId`, and the **parent's** `sessionId`. Assistant entries add `attributionAgent`. The first entry is a `user` entry with the prompt and a `timestamp`.

**Variants and edge cases:** an agent transcript file for the internal compaction agent was announced by SubagentStop but never written (see layout).

**Spec alignment:** aligned with line 609 ("read from the transcript on demand"): `agentType`, `description` and start/last `timestamp` exist. For state, see the queue-operation section.

## Workflow subagents: `journal.jsonl`, `workflows/wf_<runId>.json`, script

- **Produced by:** Claude Code 2.1.270 (Workflow tool)
- **Consumed by:** §12 subagent lines (line 1870), §7 subagent rows (line 609), M1
- **Probe:** `probe_lifecycle.sh workflow`. Re-run: `bash docs/probes/2026-09-14-schemas/transcripts/probe_lifecycle.sh workflow`
- **Status:** verified live 2026-09-14

**Real example** (full capture: `copies/-tmp-shp-schemas-tx-blIf90-work/518c280f-3791-4571-ae9a-f002c8f3b33c/subagents/workflows/wf_edb19b07-a69/journal.jsonl` and `.../agent-aff491fda998b3fe0.meta.json`; trimmed `.../518c280f-3791-4571-ae9a-f002c8f3b33c/workflows/wf_edb19b07-a69.json`)
```json
{"type":"launched"}
{"type":"started","key":"v2:790ace0b7a70b7ce22b41ec6c8a1903b01ee817a5738b79071f6aafe00f92aef","agentId":"aff491fda998b3fe0","label":"ping","phase":"Ping"}
{"type":"result","key":"v2:790ace0b7a70b7ce22b41ec6c8a1903b01ee817a5738b79071f6aafe00f92aef","agentId":"aff491fda998b3fe0","result":"PONG"}
{"agentType":"workflow-subagent","description":"ping","workflowPhase":"Ping","spawnDepth":1,"requestShape":"foreground","requestNonInteractive":true}
{"runId":"wf_edb19b07-a69","timestamp":"2026-09-14T15:09:58.745Z","taskId":"w1x94eiqe","script":"export const meta = { name: 'shp-probe-wf', description: 'sc...","scriptPath":"/root/.claude/projects/-tmp-shp-schemas-tx-blIf90-work/518c2...","result":"PONG","agentCount":1,"logs":[],"durationMs":1530,"summary":"schema probe","workflowName":"shp-probe-wf","status":"completed","startTime":1789398597206,"phases":[{"title":"Ping"}],"defaultModel":"claude-haiku-4-5-20251001","workflowProgress":[{"type":"workflow_phase","index":1,"title":"Ping"},{"type":"workflow_agent","index":1,"label":"ping","phaseIndex":1,"phaseTitle":"Ping","agentId":"aff491fda998b3fe0","model":"claude-haiku-4-5-20251001","state":"done","startedAt":1789398597241,"queuedAt":1789398597235,"attempt":1,"promptPreview":"Reply with exactly the word PONG.","promptFramed":false,"lastProgressAt":1789398598743,"tokens":10077,"toolCalls":0,"durationMs":1502,"resultPreview":"PONG"}],"totalTokens":10077,"totalToolCalls":0}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| journal `type` | string | always | `launched` (first line, no other fields), `started`, `result` | user data: 2 launched, 17 started, 15 result (a running workflow has started entries without results) |
| journal `key` | string | on started/result | `v2:<sha256>` | Resume cache key |
| journal `agentId`, `label`, `phase` | string | on started | | `label` = meta `description` |
| journal `result` | any | on result | string, or an object when a schema is used | Can carry the full agent output |
| `wf_<runId>.json` | object | after completion (1/2 user runs) | `status: completed`; `workflowProgress[].state: done` | Per-agent `state`, `model`, `tokens`, `durationMs`. User file also has `args` |
| workflow `toolUseResult` (parent `user` entry) | object | always | `{status:"async_launched",taskId,taskType:"local_workflow",workflowName,runId,summary,transcriptDir,scriptPath}` | Links the parent transcript to the run dir |

**Variants and edge cases:** SubagentStop for a workflow agent carries `agent_type:"workflow-subagent"` and `background_tasks[{type:"workflow",name}]` (`captures/hooks-lifecycle.jsonl`). `wf_<runId>.json` does not exist while the run is in flight (a live user run had only the journal).

**Spec alignment:** the spec does not cover workflow agents. They are not under `subagents/agent-*.jsonl`, have no `toolUseId`, and have the fixed `agentType:"workflow-subagent"`. Their state is readable from `journal.jsonl` (started without result = running) or from `wf_<runId>.json` `workflowProgress[].state`.

## Other metadata entries (`mode`, `permission-mode`, `atis-latch`, `bridge-session`, `cost-state`, `file-history-*`, `frame-link`, `artifact-*`, `pr-link`)

- **Produced by:** Claude Code 2.1.270
- **Consumed by:** §7 `pr_url` (line 681), §8 needs-you (permission mode), M1/M2
- **Probe:** `probe_registry_interactive.sh` (interactive entries) and `probe_binary_metadata.sh` (static, pr-link). Re-run: `bash docs/probes/2026-09-14-schemas/transcripts/probe_registry_interactive.sh && bash docs/probes/2026-09-14-schemas/transcripts/probe_binary_metadata.sh`
- **Status:** partially verified. `mode`, `permission-mode`, `atis-latch`, `bridge-session`, `cost-state` and `file-history-snapshot` were verified live 2026-09-14. Counted in user data only for `file-history-delta`, `frame-link` and `artifact-*`. **`pr-link` is not verifiable here**: no probe or user session created a PR, so the only evidence is static.

**Real example** (full capture: `copies/-tmp-shp-schemas-regint-KD6xG3-work/2efd1f5f-1b93-481a-8469-0f589a48d7ae.jsonl` lines 2, 3, 5, 6, 42; privacy-redacted UUIDs)
```json
{"type":"mode","mode":"normal","sessionId":"2efd1f5f-1b93-481a-8469-0f589a48d7ae"}
{"type":"permission-mode","permissionMode":"default","sessionId":"2efd1f5f-1b93-481a-8469-0f589a48d7ae"}
{"type":"bridge-session","sessionId":"2efd1f5f-1b93-481a-8469-0f589a48d7ae","bridgeSessionId":"cse_01RmL9HDvfCZ5Wrrfpr2mM4x","lastSequenceNum":0,"ownerAccountUuid":"<redacted-uuid>","ownerOrganizationUuid":"<redacted-uuid>"}
{"type":"file-history-snapshot","messageId":"4c6578ff-280f-4929-8baa-c99461b6f5f5","snapshot":{"messageId":"4c6578ff-280f-4929-8baa-c99461b6f5f5","trackedFileBackups":{},"timestamp":"2026-09-14T15:16:17.588Z"},"isSnapshotUpdate":false}
{"type":"cost-state","sessionId":"2efd1f5f-1b93-481a-8469-0f589a48d7ae","totalCostUSD":0.031924600000000004,"totalAPIDuration":7914,"totalAPIDurationWithoutRetries":7896,"totalToolDuration":20106,"totalLinesAdded":0,"totalLinesRemoved":0,"totalDuration":50401,"startTime":1789398960924,"modelUsage":{"claude-haiku-4-5-20251001":{"inputTokens":368,"outputTokens":516,"thinkingTokens":426,"cacheReadInputTokens":106786,"cacheCreationInputTokens":9149,"webSearchRequests":0,"costUSD":0.031924600000000004}},"hasUnknownModelCost":false}
```
Static evidence for `pr-link` (trimmed; full capture: `captures/binary-metadata-table.txt`, from `probe_binary_metadata.sh`, a grep of the 2.1.270 binary):
```text
claude_version: 2.1.270 (Claude Code)
binary: /root/.local/share/claude/versions/2.1.270
...
# pr-link writer
ber!==void 0&&this.currentSessionPrUrl&&this.currentSessionPrRepository)P.push({type:"pr-link",sessionId:d,prNumber:this.currentSessionPrNumber,prUrl:this.currentSessionPrUrl,prRepository:this.currentSessionPrRepository,timestamp:new Date().toISOString()});...
leChanged.emit()}async function _Dr(e,n,r,s,d,m){let _=d??hf(e);try{await pA(_,{type:"pr-link",sessionId:e,prNumber:n,prUrl:r,prRepository:s,timestamp:new Date().toISOString()},m),i("tengu_session_linked_to_pr",{prNumber:n})}catch(E){let A=k(E);if(Fo(E))t(`linkSessionToPR: failed to append pr-link entry to ${_} (...
```

| Type | Fields | Presence | Observed values | Notes |
|---|---|---|---|---|
| `mode` | `mode` | always (interactive), sometimes (`-p` after resume) | `normal` 425 | |
| `permission-mode` | `permissionMode` | written by interactive sessions (also copied into a `-p` fork of one) | `auto` 412, `default` 7, `acceptEdits` 6 (user) | Live permission mode |
| `atis-latch` | `atis` | always | `""` | Meaning unknown |
| `bridge-session` | `bridgeSessionId`, `lastSequenceNum`, `ownerAccountUuid`, `ownerOrganizationUuid` | Remote Control sessions (406 user; 142 carry owner UUIDs) | `cse_…` | The same suffix appears as `session_…` in the registry `bridgeSessionId` |
| `cost-state` | `totalCostUSD`, `totalAPIDuration`, `totalDuration`, `modelUsage{<model>:{…}}`, … | interactive, at exit (7 user) | | Written at session end |
| `file-history-snapshot` | `messageId`, `snapshot{messageId,trackedFileBackups,timestamp}`, `isSnapshotUpdate` | interactive only (217 user; 0 in `-p` probes, even after a Write) | | No `sessionId` |
| `file-history-delta` | `backup`, `messageId`, `snapshotMessageId`, `timestamp`, `trackingPath` | sometimes (49 user) | | No `sessionId` |
| `frame-link` | `artifactCount`, `timestamp`; sometimes `frameUrl`, `path`, `title` | 55 user | | |
| `artifact-autoreact-ledger` / `artifact-comment-monitor` | `v`, `artifacts`, `accountUuid` (ledger) | 14 / 4 user | | Contains accountUuid |
| `pr-link` | `sessionId`, `prNumber`, `prUrl`, `prRepository`, `timestamp` (static) | **never observed** (0 user, 0 probe) | — | Emitted only when the session tracked a PR |

**Variants and edge cases:** `permission-mode` is written only by interactive sessions. A `-p` session's mode is visible only on `user.permissionMode`.

**Spec alignment:** spec line 681 says `pr_url` is "free — the transcript emits `pr-link` entries". That is unverified: 0 `pr-link` entries in 14 user transcripts and in every probe. The binary writes `{type:"pr-link",sessionId,prNumber,prUrl,prRepository,timestamp}` only when `currentSessionPrNumber`, `currentSessionPrUrl` and `currentSessionPrRepository` are all set, or from `linkSessionToPR` (`captures/binary-metadata-table.txt`). Until a PR-creating session is probed, `pr_url` should be treated as possibly always null.

## Resume (`--resume <id>`)

- **Produced by:** Claude Code 2.1.270
- **Consumed by:** §6 matrix "steer / resume" (line 548), `MasterRuntime.resume` (§6), D10/D30, M3/M4
- **Probe:** `probe_lifecycle.sh resume`. Re-run: `bash docs/probes/2026-09-14-schemas/transcripts/probe_lifecycle.sh main resume`
- **Status:** verified live 2026-09-14 (`-p` resume of a stopped session)

**Real example** (trimmed; full captures: `captures/resume-filecheck.txt`, `copies/-tmp-shp-schemas-tx-blIf90-work/0141fab3-8bf8-4b69-be1f-89552ccfce5d.jsonl` line 45)
```text
file: /root/.claude/projects/-tmp-shp-schemas-tx-blIf90-work/0141fab3-8bf8-4b69-be1f-89552ccfce5d.jsonl
lines_before: 38
lines_after: 47
files_named_id: 1
```
```json
{"type":"last-prompt","lastPrompt":"Reply with exactly RESUMED.","leafUuid":"a0f601a0-f071-4fc6-b3fa-969600f80e5c","sessionId":"0141fab3-8bf8-4b69-be1f-89552ccfce5d"}
```

| Observation | Value | Evidence |
|---|---|---|
| sessionId kept | yes: `result.session_id` = original id | `captures/resume-stdout.jsonl` |
| same file appended | yes (38 → 47 lines), no new file | `captures/resume-filecheck.txt` |
| hook `SessionStart.source` | `resume` (+ `seconds_since_last_response`, `context_tokens`, `prompt_cache_likely_expired`, `estimated_cache_write_usd`) | `captures/hooks-lifecycle.jsonl` |
| new metadata entries | `mode`, `queue-operation`, re-appended `ai-title` / `last-prompt` | outline of the copy |

**Variants and edge cases:** `--session-id <uuid>` on a new session sets the id, the transcript file name and the hook `session_id` before the process emits anything (steps `main`, `named`, `bg`, `effort`).

**Spec alignment:** aligned. Note that spec line 652 says `engine_session_id` is "Null until the engine emits it". For owned sessions, `--session-id` can make it known at spawn. That is not a contradiction, but it is an option the spec does not use.

## Fork (`--resume <id> --fork-session`) — the basis of `ask()`

- **Produced by:** Claude Code 2.1.270
- **Consumed by:** §9 `ask()` (lines 1197–1217), D13, `EngineCapabilities.can_fork` (line 495), engine matrix "fork: yes" (line 551), §18 fork risk (line 2326), M3
- **Probe:** `probe_lifecycle.sh fork` (stopped target) and `probe_fork_live.sh` (target is a live interactive tmux session **mid-tool-call**). Re-run: `bash docs/probes/2026-09-14-schemas/transcripts/probe_fork_live.sh`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full captures: `captures/forklive-meta.txt`, `captures/forklive-fork-stdout.json`, `captures/hooks-lifecycle.jsonl` line 16, `copies/-tmp-shp-schemas-fork-RgNHRN-work/76d51cc7-3b32-4274-9ee4-e08f21f79042.jsonl` line 25)
```text
claude_version: 2.1.270 (Claude Code)
target_file: /root/.claude/projects/-tmp-shp-schemas-fork-RgNHRN-work/de7c8ce7-f01c-4dcb-8219-b3d3d8b46178.jsonl
target_lines_before_fork: 37
fork_exit: 0
target_lines_right_after_fork: 37
fork_session_id: 76d51cc7-3b32-4274-9ee4-e08f21f79042
target_lines_after_target_turn: 42
...
target_entries_mentioning_fork_id: 0
target_entries_with_fork_question: 0
fork_sessionId_values: ['76d51cc7-3b32-4274-9ee4-e08f21f79042']
fork_uuids_total: 30 shared_with_target: 19
fork_contains_target_turn2_prompt: True
```
```json
{"event_arg": "SessionStart", "captured_at": "2026-09-14T15:08:05.812927+00:00", "claude_version": "2.1.270 (Claude Code)", "ancestry": [...], "raw_stdin": "{\"session_id\":\"7c27bb7f-5390-48b0-8b2e-cf4004113d09\",\"transcript_path\":\"/root/.claude/projects/-tmp-shp-schemas-tx-blIf90-work/7c27bb7f-5390-48b0-8b2e-cf4004113d09.jsonl\",\"cwd\":\"/tmp/shp-schemas-tx.blIf90/work\",\"hook_event_name\":\"SessionStart\",\"source\":\"fork\",\"seconds_since_last_response\":2,\"context_tokens\":23008,\"prompt_cache_likely_expired\":false,\"estimated_cache_write..."}
{"parentUuid":"6d232855-d22b-4f36-a839-a1f541363810","isSidechain":false,"promptId":"032c2faa-6baf-49a3-af8b-2cadabf82c59","type":"user","message":{"role":"user","content":[{"type":"tool_result","content":"[Request interrupted by user for tool use]","is_error":true,"tool_use_id":"toolu_01Te4G4F86V1UF8hZrZz6gu5"}]},"uuid":"f0eea781-a211-4c17-803d-dac89fb21ca8","timestamp":"2026-09-14T15:22:42.306Z","toolUseResult":"[Request interrupted by user for tool use]","toolDenialKind":"interrupted","sourceToolAssistantUUID":"6d232855-d22b-4f36-a839-a1f541363810","userType":"external","entrypoint":"sdk-cli","cwd":"/tmp/shp-schemas-fork.RgNHRN/work","sessionId":"76d51cc7-3b32-4274-9ee4-e08f21f79042","version":"2.1.270","gitBranch":"HEAD"}
```
The fork's answer (`captures/forklive-fork-stdout.json` `.result`) was `PINEAPPLE-42`, the codeword given to the target in an earlier turn.

| Observation | Value | Evidence |
|---|---|---|
| new session id | yes, generated by the engine and reported in `result.session_id` | `captures/fork-session-id.txt`, `captures/forklive-meta.txt` |
| new file | `<slug>/<newId>.jsonl` in the same project dir. The source file is unchanged (47 → 47 stopped; 37 → 37 live) | `captures/fork-filecheck.txt` |
| history copied | the conversation entries are copied with **`uuid` preserved**, **`sessionId` rewritten** to the new id, and **`entrypoint` rewritten** (`cli` → `sdk-cli` when an interactive target is forked with `-p`). There is no `forkedFrom` field. In the stopped-target fork, 30 of the fork's 35 uuids also occur in the source | `copies/-tmp-shp-schemas-tx-blIf90-work/7c27bb7f-5390-48b0-8b2e-cf4004113d09.jsonl`, `copies/-tmp-shp-schemas-fork-*` |
| not copied | the `subagents/` dir (no `7c27bb7f…/` directory in the layout listing). The source's `queue-operation` and `last-prompt` entries are not copied; the fork writes its own, and its `last-prompt` value is stale (see `last-prompt`) | `captures/layout-listing.txt`, fork copy lines 3–4, 37, 44 |
| hook | `SessionStart.source = "fork"` | `captures/hooks-lifecycle.jsonl` |
| fork of a live, mid-tool-call target | the fork answered from context. The target got **0** fork entries and finished its own turn afterwards (37 → 42). The fork synthesizes, for the in-flight `tool_use`: `tool_result` "[Request interrupted by user for tool use]" (`toolDenialKind:"interrupted"`), an `isMeta` user "Continue from where you left off.", and a `<synthetic>` assistant "No response requested." | `copies/-tmp-shp-schemas-fork-RgNHRN-work/76d51cc7-3b32-4274-9ee4-e08f21f79042.jsonl` lines 25–27 |
| registry | **not captured**. No registry or `claude agents --json` snapshot was taken while a fork ran. Absence is only expected by analogy to the `-p` negative, which is itself inconclusive (see registry) | — |

**Variants and edge cases:**
- A fork of an idle live session (first live run, `captures/forklive-run1-idle/`) also answered correctly and left the target untouched.
- A fork leaves a permanent transcript file in the target's project dir. `ask()` must delete it or filter it, or else attached-session discovery that globs `*.jsonl` will list it.
- The environment blocked a bare `sleep 45` Bash call ("Blocked: standalone sleep"), which is why the live probe uses `python3 -c "import time; time.sleep(45)"`.

**Spec alignment:**
- spec line 1204–1205 says "the `SessionStart` hook's `start_reason` enum includes `fork`". The field is named **`source`** (`"source":"fork"`, `captures/hooks-lifecycle.jsonl` line 16).
- Otherwise aligned with D13. The target is never interrupted or polluted, even mid-turn. Line 551 "fork: yes" holds.

## `~/.claude.json` — `projects[<cwd>]` (trust and last-session fields)

- **Produced by:** Claude Code 2.1.270
- **Consumed by:** §13 trust posture, attached-session discovery (§8 line 926), M1
- **Probe:** `docs/probes/2026-09-14-schemas/transcripts/probe_claude_json.py` (read-only). Re-run: `python3 docs/probes/2026-09-14-schemas/transcripts/probe_claude_json.py`
- **Status:** verified live 2026-09-14 (field names and types. Values shown only for the probe's own throwaway project)

**Real example** (trimmed; full capture: `captures/claude-json-shape.txt`)
```text
claude_version: 2.1.270 (Claude Code)
## projects: object keyed by absolute cwd path; 11 entries
## per-project fields (name: types, present in N of 11 entries)
  allowedTools: array  11
  ...
  hasTrustDialogAccepted: bool  11
  ...
  lastGracefulShutdown: bool  11
  ...
  lastSessionId: string  9
  ...
  lastVersionBase: string  11
  ...
## hasTrustDialogAccepted value counts: {(True,): 9, (False,): 2}
## entries for throwaway probe dirs (/tmp/shp-schemas-*), scalar values shown (our own sessions), arrays/objects typed only
  "/tmp/shp-schemas-regint.KD6xG3/work" {"allowedTools": "array(0)", "mcpContextUris": "array(0)", "mcpServers": "object(0 keys)", "enabledMcpjsonServers": "array(0)", "disabledMcpjsonServers": "array(0)", "hasTrustDialogAccepted": true, "hasClaudeMdExternalIncludesApproved": false, "hasClaudeMdExternalIncludesWarningShown": false, "lastGracefulShutdown": true, "lastVersionBase": "2.1.270", "lastCost": 0.031924600000000004, ... "lastSessionId": "2efd1f5f-1b93-481a-8469-0f589a48d7ae"}
```

| Field (`projects[<abs cwd>]`) | Type | Presence (of 11) | Observed values | Notes |
|---|---|---|---|---|
| key | string (absolute cwd) | — | raw path, not slugged | |
| `hasTrustDialogAccepted` | bool | always | true 9, false 2 | Set to true by accepting the dialog (probe) |
| `hasClaudeMdExternalIncludesApproved`, `hasClaudeMdExternalIncludesWarningShown` | bool | always | | |
| `allowedTools`, `mcpContextUris`, `enabledMcpjsonServers`, `disabledMcpjsonServers` | array | always | | |
| `mcpServers` | object | always | | |
| `lastSessionId` | string | sometimes (9) | UUID of the most recent session in that cwd | When it is written was not captured. The regint throwaway's value equals its session id after exit |
| `lastGracefulShutdown` | bool | always | | |
| `lastVersionBase` | string | always | `2.1.270` | |
| `lastCost`, `lastDuration`, `lastAPIDuration`, `lastAPIDurationWithoutRetries`, `lastToolDuration`, `lastStartTime`, `lastLinesAdded`, `lastLinesRemoved`, `lastTotal{Input,Output,CacheCreationInput,CacheReadInput}Tokens`, `lastTotalWebSearchRequests` | number | sometimes (9) | | |
| `lastModelUsage` | object | sometimes (9) | | |
| `lastSessionMetrics` | object | sometimes (4) | | |
| `lastFpsAverage`, `lastFpsLow1Pct` | number | sometimes (8) | | Interactive rendering |
| `exampleFiles`, `exampleFilesGeneratedAt`, `hasUnseenTeamArtifacts` | array / number / bool | sometimes (2/1/2) | | |

Top level: 62 keys, including `projects`, `oauthAccount` (object, 20 keys; sensitive), `userID`, `machineID`, `numStartups`, `hasUsedRemoteControl` (full list in the capture).

**Variants and edge cases:** **`-p` sessions create no `projects[]` entry**. The capture lists only 3 `/tmp/shp-schemas-*` entries, and each is a cwd where an interactive throwaway ran (regint and the two fork targets). The `-p`-only cwds (`/tmp/shp-schemas-tx.*`, `/tmp/shp-schemas-slug.*`, `/tmp/shp-schemas-reg.*`) have none; `-p` skips the trust dialog. Whether a declined trust dialog adds an entry is not in any capture. `lastSessionId` holds only one id per cwd.

**Spec alignment:** the spec does not reference `~/.claude.json`. Discovery must not rely on it, because it misses every `-p` session and keeps one id per cwd.

## Live-session registry `~/.claude/sessions/<pid>.json`

- **Produced by:** Claude Code 2.1.270 (interactive sessions only)
- **Consumed by:** §8 attached-session registration (lines 926–927), D1 attached sessions, §12 fleet (`needs_you`, running), M1
- **Probe:** `probe_registry_interactive.sh` and `probe_registry.sh` (`-p` negative), plus `stats_registry.py`. Re-run: `bash docs/probes/2026-09-14-schemas/transcripts/probe_registry_interactive.sh`
- **Status:** partially verified. The interactive file shape and the `idle`/`busy` lifecycle were verified live 2026-09-14. `waiting` / `waitingFor` are a user-data shape only, and the `-p` negative is inconclusive (see below).

**Real example** (full capture: `captures/regint-registry-busy.json`)
```json
{
    "pid": 4033805,
    "sessionId": "2efd1f5f-1b93-481a-8469-0f589a48d7ae",
    "cwd": "/tmp/shp-schemas-regint.KD6xG3/work",
    "startedAt": 1789398970793,
    "procStart": "543621664",
    "version": "2.1.270",
    "peerProtocol": 1,
    "peerFeatures": [
        "notify_idle",
        "reply_across_default_dirs",
        "artifact_yield"
    ],
    "kind": "interactive",
    "entrypoint": "cli",
    "pidDomain": "linux:64835ff781b0486f95b67b152a8cf404:pid:[4026531836]",
    "tmux": "probe:@0.%0",
    "messagingSocketPath": "/run/user/0/cc-socks/4033805.sock",
    "name": "shp regint probe",
    "nameSource": "user",
    "nameSince": 1789398970794,
    "updatedAt": 1789398977680,
    "status": "busy",
    "statusUpdatedAt": 1789398977680,
    "bridgeSessionId": "session_01RmL9HDvfCZ5Wrrfpr2mM4x"
}
```

| Field | Type | Presence (4 user files + probe) | Observed values | Notes |
|---|---|---|---|---|
| `pid` | number | always | = file name | |
| `sessionId`, `cwd` | string | always | | |
| `startedAt`, `updatedAt`, `statusUpdatedAt`, `nameSince` | number (epoch ms) | always | | |
| `procStart` | string | always | | Process start ticks, which guard against pid reuse |
| `version` | string | always | `2.1.270` 3, `2.1.269` 1 | |
| `kind` | string | always | `interactive` | |
| `entrypoint` | string | always | `cli` | |
| `status` | string | always | `idle`, `busy`, `waiting` | Changed idle → busy → idle during the probe turn |
| `waitingFor` | string | sometimes (1 user, with `status:waiting`) | `<redacted>` | |
| `name`, `nameSource` | string | always | `nameSource`: `user` (`--name`), `derived` (user's RC sessions) | |
| `peerProtocol`, `peerFeatures` | number / array | always | 1; `notify_idle`, `reply_across_default_dirs`, `artifact_yield` | |
| `pidDomain` | string | always | `linux:<hex>:pid:[<ns inode>]` | |
| `messagingSocketPath` | string | always | `/run/user/0/cc-socks/<pid>.sock` | |
| `tmux` | string | sometimes (3/4 user; probe) | `<session>:@<window>.%<pane>` | Present when launched inside tmux |
| `bridgeSessionId` | string | sometimes (3/4) | `session_…` | Remote Control |
| sibling `<pid>.<64 hex>.key` | file (mode 0600) | always | not read | Contains a peer token. Never read it |

**Variants and edge cases:**
- The file appears only **after the trust dialog is accepted**. During the dialog there was no file (`captures/regint-meta.txt`: `startup registry_file: none`).
- The file is **deleted on exit** (`after_exit registry_file: none`).
- **`-p` sessions: not verified.** `captures/registry-meta.txt` shows `registry_file:` empty, but the check ran about 15 s after launch. The `-p` model had its `sleep 40` blocked and backgrounded, and its last transcript entry is at 15:14:30.270Z, about 9 s after launch (`copies/-tmp-shp-schemas-reg-Jv4MTo-work/ea5a5348-….jsonl`). The process may already have exited when the registry was read. Absence during a live `-p` turn still needs a probe that confirms the pid is alive at check time.

**Spec alignment:** spec lines 926–927 say a hand-launched session "registers itself on its first turn with no filesystem polling" via `SessionStart`. That is an omission more than a contradiction. `SessionStart` can only register sessions started after hooks are installed. Sessions already running at install time have already passed `SessionStart`. Whether they pick up newly installed hooks on their next event was **not probed**. `~/.claude/sessions/<pid>.json` lists interactive sessions with `sessionId`, `cwd`, `status` and `tmux` pane, and the spec does not mention this source (`captures/regint-registry-busy.json`, `captures/regint-meta.txt`, `captures/registry-stats.json`).

## `claude agents --json`

- **Produced by:** Claude Code 2.1.270 (`claude agents --json [--all] [--cwd <path>]`)
- **Consumed by:** candidate discovery source for attached sessions (§8 line 926, D1), M1
- **Probe:** `probe_registry_interactive.sh` (own entry) and `probe_registry.sh` (other entries as redacted shapes, `-p` negative). Re-run: `bash docs/probes/2026-09-14-schemas/transcripts/probe_registry_interactive.sh`
- **Status:** partially verified. Entries for an interactive session (`idle`/`busy`) were verified live 2026-09-14. `waiting`, `--bg` sessions and `-p` absence are not verified.

**Real example** (full capture: `captures/regint-agents-busy.json`; the other entries are redacted shapes in `captures/agents-json-others-shape.json`)
```json
{
 "total_entries": 6,
 "own": [
  {
   "pid": 4033805,
   "cwd": "/tmp/shp-schemas-regint.KD6xG3/work",
   "kind": "interactive",
   "startedAt": 1789398970793,
   "sessionId": "2efd1f5f-1b93-481a-8469-0f589a48d7ae",
   "name": "shp regint probe",
   "status": "busy"
  }
 ]
}
```
(`total_entries` and `own` are the probe's wrapper. The CLI prints a bare JSON array of these objects.)

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `pid` | number | always | | |
| `cwd` | string | always | raw path | |
| `kind` | string | always | `interactive` (all observed) | Other kinds (e.g. background sessions) are not captured; no help-text capture exists |
| `startedAt` | number (epoch ms) | always | | |
| `sessionId` | string | always | | |
| `name` | string | always (observed) | | |
| `status` | string | always | `idle`, `busy`, `waiting` | Same values as the registry file |
| `waitingFor` | string | sometimes | `<redacted>` (1 user entry, status `waiting`) | |

**Variants and edge cases:**
- It is a projection of `~/.claude/sessions/<pid>.json`. It lacks `tmux`, `procStart`, `nameSource`, `bridgeSessionId` and `messagingSocketPath`.
- `-p` sessions: the one check (`captures/agents-json-own.json`, `"own": []`) is inconclusive, for the same timing reason as the registry `-p` check.
- `--all` returned the same entries (no completed background sessions existed).
- Exit code 0, no stderr, no TTY needed.
- Background (`--bg`) sessions were not probed (see not verified).

**Spec alignment:** not referenced by the spec. It is a supported CLI contract that could replace reading registry files, but it forks a `claude` process per poll and omits the `tmux` pane.
