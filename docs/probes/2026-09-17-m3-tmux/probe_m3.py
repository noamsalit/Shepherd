#!/usr/bin/env python3
"""Shepherd M3 Task 1 probes P1-P4 (2026-09-17).

Re-run:  PYTHONPATH=src .venv/bin/python docs/probes/2026-09-17-m3-tmux/probe_m3.py [--only p1,p2,p3,p4]
Output:  docs/probes/2026-09-17-m3-tmux/<name>-<UTC stamp>/

  P1  p1-keys         C-a C-k, C-w x N, and C-u against the post-Esc *restored* prompt.
                      (Plain C-u after a history recall is already captured in
                      docs/probes/2026-09-14-schemas/gap-fill/keys-claude-20260914T180105Z/
                      01b-after-ctrl-u.txt and is deliberately NOT re-probed.)
  P2  p2-fork         does `--resume <id> --fork-session` accept `--session-id <uuid>`;
                      does `--no-session-persistence` apply with `-p` in that combination and
                      is a transcript left; does the result object still carry `session_id` at
                      the installed engine version.
  P3  p3-concurrent   a browser-equivalent writer sending `send-keys -H` while a second tmux
                      client, attached from an outer throwaway pane, types at the same pane.
  P4  p4-permission   at a permission dialog: what do 1 / 2 / 3 / Esc / Tab do.

P5 (`/rename` against a session live in another process) and P6 (xterm.js rendering) are
deliberately not run: P5 risks two writers on one transcript, P6 is not probeable on this host.

--------------------------------------------------------------------------------------------
SAFETY (CLAUDE.md rules 1-4, spec section 18 incident of 2026-09-12)

This file is a copy of `docs/probes/2026-09-14-schemas/tmux-tui/probe_tui.py`'s harness with the
**two defects named in the M3 plan's Task 1 fixed in the copy** (the original is frozen evidence
and is not edited):

  (i)  `probe_tui.py:136` runs a bare `tmux -V` with no `-L` — CLAUDE.md rule 3's forbidden form
       even though `-V` contacts no server. Here it is `VERSION_ARGV`, the exact tuple
       `check_tmux_argv` allows, matched by equality and never by prefix.
  (ii) `probe_tui.py:392-395` tears down with `kill-server` on socket `shepherd-probe`, which
       does not match `^shepherd-m3-` and which K6-a now permits only on a throwaway. Every
       socket here is one of `shepherd-m3-probe` / `shepherd-m3-outer` / `shepherd-m3-inner`.

Beyond the two fixes:
  * every tmux argv this file builds is handed to the product's own runtime guard,
    `shepherd.runner.tmux_cmd.check_tmux_argv`, before it is executed — both whole and from the
    binary onward, so an `env -i` wrapper prefix cannot hide it (the `_tmux_tail` scan, T8-2);
  * the permitted set is exactly the three sockets above. `shepherd` (the user's live sessions)
    and `shepherd-runner` are not in it and the guard refuses them by name;
  * session names never contain ':' or '.'; pane targets are the exact form `=<name>:`;
  * tmux servers start under `env -i` so panes inherit no $TMUX and no CLAUDECODE;
  * every `claude` run gets a throwaway `mktemp` working directory and an explicit `--settings`;
  * every subprocess call has a timeout;
  * nothing under ~/.claude is written or read by this script except the transcripts `claude`
    itself writes for its own throwaway project dirs, which P2 must list to answer its question.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "src"))

from shepherd.runner.tmux_cmd import (  # noqa: E402
    VERSION_ARGV,
    check_tmux_argv,
    permitted_sockets,
    session_name,
    target,
    tmux_argv,
)
from shepherd.runner.tmux_cmd import _is_binary  # noqa: E402  (same predicate both gates use)

# --------------------------------------------------------------------------------------------
# constants

SOCK_PROBE = "shepherd-m3-probe"    # P1, P2's teardown witness, P4
SOCK_OUTER = "shepherd-m3-outer"    # P3: the throwaway pane the second client attaches FROM
SOCK_INNER = "shepherd-m3-inner"    # P3: the server holding the TUI it attaches TO
PERMITTED = permitted_sockets(SOCK_PROBE, SOCK_OUTER, SOCK_INNER)

MODEL = "claude-haiku-4-5"
PATHV = "/root/.local/bin:/usr/local/bin:/usr/bin:/bin"
CLEAN_ENV = ["env", "-i", "HOME=/root", f"PATH={PATHV}", "TERM=xterm-256color", "LANG=C.UTF-8"]
CAPTURE_HOOK = os.path.join(
    REPO, "docs", "probes", "2026-09-14-schemas", "tmux-tui", "capture_hook.sh"
)
HOOK_EVENTS = [
    "PreToolUse", "PostToolUse", "PostToolUseFailure", "Notification", "UserPromptSubmit",
    "SessionStart", "SessionEnd", "Stop", "StopFailure", "PermissionRequest", "PermissionDenied",
]
TMUX_TIMEOUT = 30.0
CLAUDE_P_TIMEOUT = 240.0


def stamp() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def tmux_version() -> str:
    """Defect (i) fixed: the exact `VERSION_ARGV` form, checked by the guard like every other."""
    argv = list(VERSION_ARGV)
    check_tmux_argv(argv, permitted=PERMITTED)
    return subprocess.run(argv, capture_output=True, text=True, timeout=TMUX_TIMEOUT).stdout.strip()


def claude_version() -> str:
    return subprocess.run(
        ["claude", "--version"], capture_output=True, text=True, timeout=60
    ).stdout.strip()


def _tail_from_binary(argv: list[str]) -> list[str]:
    """`argv` from the tmux binary onward, so an `env -i` prefix cannot hide it (T8-2)."""
    for index, word in enumerate(argv):
        if _is_binary(word):
            return list(argv[index:])
    return []


# --------------------------------------------------------------------------------------------
# run folder


class Run:
    def __init__(self, name: str):
        self.name = name
        self.dir = os.path.join(HERE, f"{name}-{stamp()}")
        os.makedirs(self.dir)
        self.steplog = open(os.path.join(self.dir, "steps.log"), "a")
        self.claude_ver = claude_version()
        self.tmux_ver = tmux_version()
        self.results: dict = {}
        self.save(
            "versions.txt",
            f"probe: {name}\n"
            f"claude --version: {self.claude_ver}\n"
            f"tmux -V: {self.tmux_ver}\n"
            f"python: {sys.version.split()[0]}\n"
            f"uname: {os.uname().sysname} {os.uname().release}\n"
            f"model: {MODEL}\n"
            f"run: {os.path.basename(self.dir)}\n",
        )

    def log(self, msg: str) -> None:
        line = f"{datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='milliseconds')} {msg}"
        print(line, flush=True)
        self.steplog.write(line + "\n")
        self.steplog.flush()

    def path(self, name: str) -> str:
        return os.path.join(self.dir, name)

    def save(self, name: str, text: str, mode: str = "w") -> str:
        p = self.path(name)
        with open(p, mode) as f:
            f.write(text)
        return p

    def finish(self, sockets: tuple[str, ...]) -> None:
        self.save("results.json", json.dumps(self.results, indent=1, default=str) + "\n")
        lines = []
        for sock in sockets:
            r = tm(sock, "ls", run=self)
            err = r.stderr.strip()
            verdict = "no server running" if r.returncode != 0 else "SERVER STILL UP"
            lines.append(
                f"after kill-server: tmux -L {sock} ls rc={r.returncode} err={err!r} -> {verdict}"
            )
        self.save("teardown.txt", "\n".join(lines) + "\n")
        self.log("teardown: " + " | ".join(lines))


# --------------------------------------------------------------------------------------------
# tmux, every argv through the product's guard


def tm(sock: str, *args: str, env_clean: bool = False, run: Run | None = None,
       timeout: float = TMUX_TIMEOUT) -> subprocess.CompletedProcess:
    argv = tmux_argv(sock, *args)
    cmd = (CLEAN_ENV if env_clean else []) + argv
    # Both gates, exactly as `local.py` runs them: the whole argv, and the argv from the binary
    # onward so the `env -i` prefix cannot hide it.
    check_tmux_argv(cmd, permitted=PERMITTED)
    check_tmux_argv(_tail_from_binary(cmd), permitted=PERMITTED)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if run is not None:
        run.log(
            f"$ tmux -L {sock} {' '.join(args)} -> rc={r.returncode} "
            f"out={r.stdout.strip()[:200]!r} err={r.stderr.strip()[:200]!r}"
        )
    return r


def kill_socket(sock: str, run: Run) -> None:
    """K6-a's one relaxation, on a throwaway socket the guard itself re-checks."""
    tm(sock, "kill-server", run=run)


# --------------------------------------------------------------------------------------------
# hooks


def write_settings(path: str, hook_log: str, ver: str) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    hooks = {
        ev: [{"hooks": [{"type": "command",
                         "command": f"SHP_CLAUDE_VERSION='{ver}' {CAPTURE_HOOK} {ev} {hook_log}",
                         "timeout": 10}]}]
        for ev in HOOK_EVENTS
    }
    with open(path, "w") as f:
        json.dump({"enabledPlugins": {"cc10x@cc10x": False},
                   "remoteControlAtStartup": False,
                   "hooks": hooks}, f, indent=1)
    return path


def hooks(logp: str) -> list[dict]:
    if not os.path.exists(logp):
        return []
    out = []
    for line in open(logp):
        try:
            out.append(json.loads(line))
        except Exception:
            out.append({"_event": "UNPARSEABLE", "payload": {}, "_raw": line})
    return out


def ev(name: str, **kw):
    def pred(h):
        if h.get("_event") != name:
            return False
        return all(h.get("payload", {}).get(k) == v for k, v in kw.items())
    return pred


def wait_event(logp: str, pred, timeout: float, after: int = 0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        hs = hooks(logp)
        for i, h in enumerate(hs[after:], start=after):
            if pred(h):
                return i, h
        time.sleep(0.5)
    return None, None


def event_names(logp: str, after: int) -> list[str]:
    return [h["_event"] for h in hooks(logp)[after:]]


# --------------------------------------------------------------------------------------------
# a TUI in a pane


INPUT_MARK = "❯"  # the TUI's input-box chevron


def input_box(screen: str) -> list[str]:
    """The input-box lines only. The submitted prompt echo scrolls above and is not the box."""
    return [ln.rstrip() for ln in screen.splitlines() if INPUT_MARK in ln]


class Tui:
    def __init__(self, run: Run, sock: str, sid: str, cwd: str, settings: str,
                 debug: str, x: int = 160, y: int = 45):
        self.run, self.sock = run, sock
        self.name = session_name(sid)
        self.t = target(self.name)
        argv = ["claude", "--model", MODEL, "--settings", settings, "--debug-file", debug]
        r = tm(sock, "new-session", "-d", "-s", self.name, "-x", str(x), "-y", str(y),
               "-c", cwd, *argv, env_clean=True, run=run)
        run.save(f"{self.name}-spawn-cmd.txt",
                 f"env -i ... tmux -L {sock} new-session -d -s {self.name} -x {x} -y {y} "
                 f"-c {cwd} {' '.join(argv)}\nrc={r.returncode}\nstderr={r.stderr.strip()}\n")
        tm(sock, "set-option", "-w", "-t", self.t, "remain-on-exit", "on", run=run)
        time.sleep(0.5)
        self.pane_pid = int(self.fmt("#{pane_pid}") or 0)

    def fmt(self, f: str) -> str:
        return tm(self.sock, "display-message", "-p", "-t", self.t, f).stdout.strip()

    def screen(self, ansi: bool = False) -> str:
        a = ["capture-pane", "-p"] + (["-e"] if ansi else []) + ["-t", self.t]
        return tm(self.sock, *a).stdout

    def snap(self, base: str) -> str:
        """Plain + `-e` (ANSI) + a printable cat -v rendering of the ANSI bytes."""
        plain = self.screen()
        self.run.save(f"{base}.txt", plain)
        raw = self.screen(ansi=True)
        self.run.save(f"{base}.ansi.txt", raw)
        v = subprocess.run(["cat", "-v"], input=raw.encode(), capture_output=True,
                           timeout=30).stdout.decode()
        self.run.save(f"{base}.ansi.cat-v.txt", v)
        return plain

    def keys(self, *k: str) -> None:
        tm(self.sock, "send-keys", "-t", self.t, *k, run=self.run)

    def hexkeys(self, *hexbytes: str) -> None:
        tm(self.sock, "send-keys", "-t", self.t, "-H", *hexbytes, run=self.run)

    def text(self, s: str) -> None:
        tm(self.sock, "send-keys", "-t", self.t, "-l", s, run=self.run)

    def submit(self, s: str, pause: float = 0.6) -> None:
        self.text(s)
        time.sleep(pause)
        self.keys("Enter")

    def wait_screen(self, needle: str, timeout: float):
        t0 = time.time()
        while time.time() - t0 < timeout:
            s = self.screen()
            if needle in s:
                return s
            time.sleep(0.5)
        return None

    def trust(self, timeout: float = 60.0) -> bool:
        """Accept the workspace-trust dialog.

        The selected option is the one on the `❯` line, and the **default is `No, exit`**. The
        first run of this probe sent `Down` about a second after the dialog text appeared, the
        TUI had not yet bound the key, `Enter` took the default and the pane exited (status 1).
        So the selection is *read back* until it really is on `Yes, I trust this folder`, and
        `Enter` is only pressed once it is.
        """
        s = self.wait_screen("trust this folder", timeout)
        if s is None:
            self.run.log(f"{self.name}: no trust dialog within {timeout}s")
            return False
        self.run.save(f"00-{self.name}-trust-dialog.txt", s)
        for attempt in range(8):
            time.sleep(1.5)
            self.keys("Down")
            time.sleep(1.0)
            selected = " ".join(input_box(self.screen()))
            self.run.log(f"{self.name}: trust selection after Down #{attempt + 1}: {selected!r}")
            if "trust this folder" in selected:
                break
        else:
            self.run.log(f"{self.name}: could not move the trust selection off the default")
            return False
        self.keys("Enter")
        self.run.log(f"{self.name}: trust dialog accepted")
        return True

    def assert_alive(self, where: str) -> None:
        if self.fmt("#{pane_dead}") == "1":
            self.snap(f"ABORT-{where}-dead-pane")
            raise RuntimeError(f"{self.name}: pane is dead at {where}; refusing to record garbage")


def mktmp(tag: str) -> str:
    d = tempfile.mkdtemp(prefix=f"shp-m3-{tag}-", dir="/tmp")
    os.makedirs(os.path.join(d, "work"), exist_ok=True)
    return os.path.join(d, "work")


def precheck(run: Run, *socks: str) -> None:
    for sock in socks:
        r = tm(sock, "ls", run=run)
        run.save(f"socket-precheck-{sock}.txt",
                 f"tmux -L {sock} ls -> rc={r.returncode} out={r.stdout!r} err={r.stderr.strip()!r}\n")
        if r.returncode == 0:
            run.log(f"{sock} already has sessions; refusing to run")
            sys.exit(2)


# ============================================================================================
# P1 — C-a C-k, C-w x N, and C-u against the post-Esc restored prompt


def probe_p1() -> None:
    run = Run("p1-keys")
    precheck(run, SOCK_PROBE)
    work = mktmp("p1")
    hl = run.path("hooks.jsonl")
    settings = write_settings(run.path("settings.json"), hl, run.claude_ver)
    run.save("tmpdirs.txt", f"cwd={work}\nsettings={settings}\n")
    res = run.results
    try:
        t = Tui(run, SOCK_PROBE, "p1", work, settings, run.path("debug.log"))
        t.trust()
        i, ss = wait_event(hl, ev("SessionStart"), 120)
        res["session_start_seen"] = ss is not None
        res["session_id"] = ss["payload"].get("session_id") if ss else None
        t.assert_alive("after-trust")
        time.sleep(4)
        t.snap("01-idle-prompt")

        # ---- A. C-a C-k -----------------------------------------------------------------
        run.log("A: C-a C-k against typed text")
        t.text("ALPHA BRAVO CHARLIE")
        time.sleep(1.0)
        before = t.snap("02a-before-ctrl-a-ctrl-k")
        res["a_input_before"] = input_box(before)
        t.keys("C-a")
        time.sleep(0.6)
        t.snap("02b-after-ctrl-a")
        t.keys("C-k")
        time.sleep(1.0)
        after = t.snap("02c-after-ctrl-a-ctrl-k")
        res["a_input_after"] = input_box(after)
        res["a_ctrl_a_ctrl_k_clears_input"] = "ALPHA" not in " ".join(input_box(after))
        t.keys("C-u")
        time.sleep(0.8)
        t.snap("02d-reset-with-ctrl-u")

        # ---- B. C-w x N -----------------------------------------------------------------
        run.log("B: C-w x3 against three words")
        t.text("WORDONE WORDTWO WORDTHREE")
        time.sleep(1.0)
        before = t.snap("03a-before-ctrl-w")
        res["b_input_before"] = input_box(before)
        res["b_after_each_ctrl_w"] = []
        for n in (1, 2, 3):
            t.keys("C-w")
            time.sleep(0.8)
            s = t.snap(f"03b-after-ctrl-w-x{n}")
            res["b_after_each_ctrl_w"].append({"presses": n, "input_box": input_box(s)})
        res["b_ctrl_w_deletes_word_backward"] = (
            "WORDTHREE" not in " ".join(res["b_after_each_ctrl_w"][0]["input_box"])
            and "WORDONE" in " ".join(res["b_after_each_ctrl_w"][0]["input_box"])
        )
        res["b_three_presses_clear_three_words"] = (
            "WORDONE" not in " ".join(res["b_after_each_ctrl_w"][2]["input_box"])
        )
        t.keys("C-u")
        time.sleep(0.8)
        t.snap("03c-reset-with-ctrl-u")

        # ---- C. C-u against the post-Esc RESTORED prompt ---------------------------------
        run.log("C: Esc during streaming, then C-u against the restored prompt")
        n0 = len(hooks(hl))
        marker = "ESC-RESTORE-MARKER"
        # Revision: the first run used "count from 1 to 120" and haiku finished it inside the
        # 4 s settle, so `Stop` had already fired and the Escape landed at an *idle* prompt —
        # which is the case `data-schemas.md` already covers, not the one P1 asks about. The
        # turn is now long enough to still be in flight, and the probe *reads back* that it is:
        # `esc_pressed_mid_flight` is what makes the rest of step C meaningful, and when it is
        # false the answer is recorded as unknown rather than as a mechanism.
        t.submit(f"{marker} write a detailed 900-word essay on the history of terminal "
                 f"multiplexers, in full prose, no lists.")
        wait_event(hl, ev("UserPromptSubmit"), 60, after=n0)
        t0 = time.time()
        while time.time() - t0 < 45:
            s = t.screen()
            if "interrupt" in s and not any(h["_event"] == "Stop" for h in hooks(hl)[n0:]):
                break
            time.sleep(0.3)
        streaming = t.snap("04a-streaming-before-esc")
        res["c_streaming_input_box"] = input_box(streaming)
        res["c_stop_before_esc"] = any(h["_event"] == "Stop" for h in hooks(hl)[n0:])
        res["c_esc_pressed_mid_flight"] = not res["c_stop_before_esc"]
        res["c_streaming_hint_on_screen"] = "interrupt" in streaming
        t.keys("Escape")
        time.sleep(2.5)
        restored = t.snap("04b-after-esc-restored")
        res["c_input_box_after_esc"] = input_box(restored)
        res["c_esc_restores_prompt_into_input_box"] = marker in " ".join(input_box(restored))
        t.keys("C-u")
        time.sleep(1.5)
        cleared = t.snap("04c-after-ctrl-u-on-restored")
        res["c_input_box_after_ctrl_u"] = input_box(cleared)
        # `unknown` is a first-class value here: C-u can only be said to clear a *restored*
        # prompt if there was one on screen to clear.
        if not res["c_esc_restores_prompt_into_input_box"]:
            res["c_ctrl_u_clears_restored_prompt"] = "unknown: no restored prompt to clear"
        else:
            res["c_ctrl_u_clears_restored_prompt"] = marker not in " ".join(input_box(cleared))
        res["c_pane_dead_after"] = t.fmt("#{pane_dead}")
        # a second, independent read of the pane — DP10's post-C-u re-read guard, exercised
        time.sleep(1.0)
        reread = t.snap("04d-reread-after-ctrl-u")
        res["c_reread_input_box"] = input_box(reread)
        res["c_reread_agrees"] = (input_box(reread) == input_box(cleared))
        run.save("hook-event-sequence.txt", "\n".join(event_names(hl, 0)) + "\n")
    finally:
        kill_socket(SOCK_PROBE, run)
        run.finish((SOCK_PROBE,))
        shutil.rmtree(os.path.dirname(work), ignore_errors=True)


# ============================================================================================
# P2 — --fork-session + --session-id, --no-session-persistence, and the result object


def _p2_env() -> dict:
    return {"HOME": "/root", "PATH": PATHV, "TERM": "dumb", "LANG": "C.UTF-8"}


def project_dir(cwd: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]", "-", cwd)
    return os.path.join("/root/.claude/projects", slug)


def listing(d: str) -> list[str]:
    return sorted(os.listdir(d)) if os.path.isdir(d) else []


def p2_call(run: Run, tag: str, work: str, args: list[str], prompt: str) -> dict:
    argv = ["claude", "-p", "--model", MODEL, "--output-format", "json", *args, prompt]
    run.log(f"{tag}: {' '.join(argv)}")
    run.save(f"{tag}.argv.txt", " ".join(argv) + "\n")
    try:
        r = subprocess.run(argv, cwd=work, env=_p2_env(), capture_output=True, text=True,
                           timeout=CLAUDE_P_TIMEOUT)
        rc, out, err = r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        rc, out, err = None, "", f"<timeout after {CLAUDE_P_TIMEOUT}s>"
    run.save(f"{tag}.stdout.json", out)
    run.save(f"{tag}.stderr.txt", err)
    parsed = None
    try:
        parsed = json.loads(out)
    except Exception:
        pass
    run.log(f"{tag}: rc={rc} stdout_bytes={len(out)} stderr={err.strip()[:200]!r}")
    return {"rc": rc, "parsed": parsed, "stderr": err.strip()[:600]}


def probe_p2() -> None:
    run = Run("p2-fork")
    work = mktmp("p2")
    hl = run.path("hooks.jsonl")
    settings = write_settings(run.path("settings.json"), hl, run.claude_ver)
    run.save("tmpdirs.txt", f"cwd={work}\nsettings={settings}\nproject_dir={project_dir(work)}\n")
    res = run.results
    res["engine_version"] = run.claude_ver
    helptext = subprocess.run(["claude", "--help"], capture_output=True, text=True,
                              env=_p2_env(), timeout=120).stdout
    run.save("00-claude-help.txt", helptext)
    res["help_mentions"] = {
        flag: (flag in helptext)
        for flag in ("--fork-session", "--session-id", "--no-session-persistence", "--resume")
    }
    pdir = project_dir(work)
    try:
        u1, u2, u3, u4 = (str(uuid.uuid4()) for _ in range(4))
        res["uuids"] = {"base": u1, "fork_with_session_id": u2,
                        "fork_nsp_with_session_id": u3, "fork_nsp_no_session_id": u4}

        base = p2_call(run, "01-base", work,
                       ["--settings", settings, "--session-id", u1],
                       "Remember the codeword PINEAPPLE-M3. Reply with only the word OK.")
        res["base"] = {"rc": base["rc"],
                       "result_keys": sorted(base["parsed"].keys()) if base["parsed"] else None,
                       "session_id": (base["parsed"] or {}).get("session_id"),
                       "session_id_equals_requested": (base["parsed"] or {}).get("session_id") == u1}
        run.save("01-project-listing-after-base.txt", "\n".join(listing(pdir)) + "\n")

        # ---- A. --resume <id> --fork-session --session-id <uuid> -------------------------
        before_a = listing(pdir)
        a = p2_call(run, "02-fork-with-session-id", work,
                    ["--settings", settings, "--resume", u1, "--fork-session", "--session-id", u2],
                    "What is the codeword? Reply with only the codeword.")
        after_a = listing(pdir)
        res["fork_with_session_id"] = {
            "rc": a["rc"],
            "accepted": a["rc"] == 0,
            "stderr": a["stderr"],
            "result_session_id": (a["parsed"] or {}).get("session_id"),
            "result_session_id_equals_requested": (a["parsed"] or {}).get("session_id") == u2,
            "result_text": (a["parsed"] or {}).get("result"),
            "result_keys": sorted(a["parsed"].keys()) if a["parsed"] else None,
            "new_files": sorted(set(after_a) - set(before_a)),
        }
        run.save("02-project-listing.txt",
                 f"before={before_a}\nafter={after_a}\nnew={sorted(set(after_a) - set(before_a))}\n")

        # ---- B. the same, plus --no-session-persistence ----------------------------------
        before_b = listing(pdir)
        b = p2_call(run, "03-fork-nsp-with-session-id", work,
                    ["--settings", settings, "--resume", u1, "--fork-session",
                     "--session-id", u3, "--no-session-persistence"],
                    "What is the codeword? Reply with only the codeword.")
        time.sleep(2)
        after_b = listing(pdir)
        res["fork_nsp_with_session_id"] = {
            "rc": b["rc"],
            "accepted": b["rc"] == 0,
            "stderr": b["stderr"],
            "result_session_id": (b["parsed"] or {}).get("session_id"),
            "result_text": (b["parsed"] or {}).get("result"),
            "new_files": sorted(set(after_b) - set(before_b)),
            "transcript_left": bool(set(after_b) - set(before_b)),
        }
        run.save("03-project-listing.txt",
                 f"before={before_b}\nafter={after_b}\nnew={sorted(set(after_b) - set(before_b))}\n")

        # ---- C. control: --no-session-persistence without --session-id -------------------
        before_c = listing(pdir)
        c = p2_call(run, "04-fork-nsp-no-session-id", work,
                    ["--settings", settings, "--resume", u1, "--fork-session",
                     "--no-session-persistence"],
                    "What is the codeword? Reply with only the codeword.")
        time.sleep(2)
        after_c = listing(pdir)
        res["fork_nsp_no_session_id"] = {
            "rc": c["rc"],
            "stderr": c["stderr"],
            "result_session_id": (c["parsed"] or {}).get("session_id"),
            "new_files": sorted(set(after_c) - set(before_c)),
            "transcript_left": bool(set(after_c) - set(before_c)),
        }
        run.save("04-project-listing.txt",
                 f"before={before_c}\nafter={after_c}\nnew={sorted(set(after_c) - set(before_c))}\n")

        # ---- the result-object field table ------------------------------------------------
        sample = a["parsed"] or base["parsed"] or {}
        res["result_object_fields"] = {
            k: {"type": type(v).__name__,
                "example": (v if not isinstance(v, (dict, list)) else f"<{type(v).__name__}>")}
            for k, v in sorted(sample.items())
        }
        run.save("05-result-object-shape.json",
                 json.dumps(res["result_object_fields"], indent=1, default=str) + "\n")
        run.save("hook-event-sequence.txt", "\n".join(event_names(hl, 0)) + "\n")
        run.save("06-final-project-listing.txt", "\n".join(listing(pdir)) + "\n")
    finally:
        run.finish((SOCK_PROBE,))  # P2 starts no tmux server; the witness is recorded anyway
        shutil.rmtree(os.path.dirname(work), ignore_errors=True)


# ============================================================================================
# P3 — a browser-equivalent writer and a second attached client typing at once


def probe_p3() -> None:
    run = Run("p3-concurrent")
    precheck(run, SOCK_INNER, SOCK_OUTER)
    work = mktmp("p3")
    hl = run.path("hooks.jsonl")
    settings = write_settings(run.path("settings.json"), hl, run.claude_ver)
    run.save("tmpdirs.txt", f"cwd={work}\nsettings={settings}\n")
    res = run.results
    try:
        t = Tui(run, SOCK_INNER, "p3", work, settings, run.path("debug.log"))
        t.trust()
        i, ss = wait_event(hl, ev("SessionStart"), 120)
        res["session_start_seen"] = ss is not None
        t.assert_alive("after-trust")
        time.sleep(4)
        t.snap("01-inner-idle")

        # the second client: an attach run from an OUTER throwaway pane, with $TMUX unset, so
        # the client is not on the socket it attaches to.
        outer = session_name("outer")
        attach_cmd = f"env -u TMUX tmux -L {SOCK_INNER} attach -t {t.t}"
        r = tm(SOCK_OUTER, "new-session", "-d", "-s", outer, "-x", "160", "-y", "45",
               "sh", "-c", attach_cmd, env_clean=True, run=run)
        run.save("02-attach-cmd.txt", f"{attach_cmd}\nrc={r.returncode}\nerr={r.stderr.strip()}\n")
        time.sleep(3)
        ot = target(outer)
        outer_view = tm(SOCK_OUTER, "capture-pane", "-p", "-t", ot).stdout
        run.save("03-outer-client-view.txt", outer_view)
        clients = tm(SOCK_INNER, "list-clients", "-F",
                     "#{client_tty} #{client_width}x#{client_height} flags=#{client_flags} "
                     "session=#{client_session}", run=run).stdout
        run.save("04-inner-list-clients.txt", clients)
        res["second_client_attached"] = bool(clients.strip())
        res["second_client_sees_tui"] = "Claude" in outer_view or INPUT_MARK in outer_view

        def writer_type(s: str) -> None:
            """The browser-equivalent writer: Runner.write's `send-keys -H <hex>` on the inner."""
            tm(SOCK_INNER, "send-keys", "-t", t.t, "-H", *[f"{b:02x}" for b in s.encode()])

        def client_type(s: str) -> None:
            """The human at `tmux attach`: bytes into the OUTER pane, i.e. the client's stdin."""
            tm(SOCK_OUTER, "send-keys", "-t", ot, "-l", s)

        # ---- round 1: sequential control --------------------------------------------------
        run.log("P3 round 1: sequential control")
        writer_type("A" * 20)
        time.sleep(1.2)
        client_type("B" * 20)
        time.sleep(2.0)
        s1 = t.snap("05-round1-sequential")
        box1 = " ".join(input_box(s1))
        res["round1_sequential"] = {"input_box": input_box(s1),
                                    "a_count": box1.count("A"), "b_count": box1.count("B"),
                                    "runs": _runs(box1)}
        t.keys("C-u")
        time.sleep(1.0)
        t.snap("06-round1-reset")

        # ---- round 2: concurrent ----------------------------------------------------------
        run.log("P3 round 2: writer and second client typing at the same time")
        errors: list[str] = []
        barrier = threading.Barrier(2)

        def burst(fn, ch):
            try:
                barrier.wait(timeout=10)
                for _ in range(10):
                    fn(ch * 4)
                    time.sleep(0.05)
            except Exception as exc:  # recorded, never swallowed
                errors.append(f"{ch}: {exc!r}")

        th = [threading.Thread(target=burst, args=(writer_type, "A")),
              threading.Thread(target=burst, args=(client_type, "B"))]
        for x in th:
            x.start()
        for x in th:
            x.join(timeout=120)
        time.sleep(2.5)
        s2 = t.snap("07-round2-concurrent")
        box2 = " ".join(input_box(s2))
        runs2 = _runs(box2)
        res["round2_concurrent"] = {
            "input_box": input_box(s2),
            "a_count": box2.count("A"), "b_count": box2.count("B"),
            "a_sent": 40, "b_sent": 40,
            "no_bytes_lost": box2.count("A") == 40 and box2.count("B") == 40,
            "runs": runs2,
            "interleaved": len(runs2) > 2,
            "thread_errors": errors,
        }
        t.keys("C-u")
        time.sleep(1.0)
        t.snap("08-round2-reset")

        # ---- round 3: writer submits while the client types --------------------------------
        run.log("P3 round 3: the writer submits a prompt while the client is typing")
        n0 = len(hooks(hl))
        errors3: list[str] = []
        barrier3 = threading.Barrier(2)

        def writer_submit():
            try:
                barrier3.wait(timeout=10)
                writer_type("Reply with only the word CONCURRENT")
                time.sleep(0.3)
                tm(SOCK_INNER, "send-keys", "-t", t.t, "Enter")
            except Exception as exc:
                errors3.append(f"writer: {exc!r}")

        def client_noise():
            try:
                barrier3.wait(timeout=10)
                for _ in range(8):
                    client_type("Z")
                    time.sleep(0.04)
            except Exception as exc:
                errors3.append(f"client: {exc!r}")

        th = [threading.Thread(target=writer_submit), threading.Thread(target=client_noise)]
        for x in th:
            x.start()
        for x in th:
            x.join(timeout=120)
        _, ups = wait_event(hl, ev("UserPromptSubmit"), 45, after=n0)
        time.sleep(2)
        s3 = t.snap("09-round3-submitted")
        res["round3_submit_under_typing"] = {
            "user_prompt_submit_seen": ups is not None,
            "submitted_prompt": (ups or {}).get("payload", {}).get("prompt"),
            "client_noise_in_submitted_prompt": "Z" in ((ups or {}).get("payload", {}).get("prompt") or ""),
            "input_box_after": input_box(s3),
            "thread_errors": errors3,
        }
        outer_view2 = tm(SOCK_OUTER, "capture-pane", "-p", "-t", ot).stdout
        run.save("10-outer-client-view-final.txt", outer_view2)
        res["second_client_view_tracks_inner"] = "CONCURRENT" in outer_view2
        run.save("hook-event-sequence.txt", "\n".join(event_names(hl, 0)) + "\n")
    finally:
        kill_socket(SOCK_OUTER, run)
        kill_socket(SOCK_INNER, run)
        run.finish((SOCK_OUTER, SOCK_INNER))
        shutil.rmtree(os.path.dirname(work), ignore_errors=True)


def _runs(text: str) -> list[list]:
    """Run-length encode the A/B/Z characters, so interleaving is visible as a count."""
    out: list[list] = []
    for ch in text:
        if ch not in "ABZ":
            continue
        if out and out[-1][0] == ch:
            out[-1][1] += 1
        else:
            out.append([ch, 1])
    return out


# ============================================================================================
# P4 — permission-dialog key semantics for 1 / 2 / 3 / Esc / Tab


#: Tab first (expected non-destructive, and it is dismissed with Esc afterwards), then Esc, then
#: the digits. `2` is LAST on purpose: every captured wording of option 2 is a "don't ask again"
#: form, so pressing it earlier could suppress the dialogs the later rounds need.
P4_KEYS: list[tuple[str, list[str]]] = [
    ("Tab", ["Tab"]),
    ("Escape", ["Escape"]),
    ("1", ["-H", "31"]),
    ("3", ["-H", "33"]),
    ("2", ["-H", "32"]),
]


def probe_p4() -> None:
    run = Run("p4-permission")
    precheck(run, SOCK_PROBE)
    work = mktmp("p4")
    hl = run.path("hooks.jsonl")
    settings = write_settings(run.path("settings.json"), hl, run.claude_ver)
    run.save("tmpdirs.txt", f"cwd={work}\nsettings={settings}\n")
    res = run.results
    res["rounds"] = []
    try:
        t = Tui(run, SOCK_PROBE, "p4", work, settings, run.path("debug.log"))
        t.trust()
        wait_event(hl, ev("SessionStart"), 120)
        t.assert_alive("after-trust")
        time.sleep(4)
        t.snap("01-idle-prompt")

        for idx, (label, keyargs) in enumerate(P4_KEYS, start=2):
            fname = f"perm-{label.lower()}.txt"
            run.log(f"P4 round {label}: asking for a tool, then pressing {label}")
            n0 = len(hooks(hl))
            t.submit(f"Use the Bash tool to run exactly this command: touch {fname}")
            i, pr = wait_event(hl, ev("PermissionRequest"), 90, after=n0)
            time.sleep(2.0)
            before = t.snap(f"{idx:02d}a-{label.lower()}-dialog")
            row: dict = {
                "key": label,
                "send_keys_argv": f"send-keys -t {t.t} " + " ".join(keyargs),
                "permission_request_hook": pr is not None,
                "tool_name": (pr or {}).get("payload", {}).get("tool_name"),
                "dialog_lines": [ln.rstrip() for ln in before.splitlines() if ln.strip()][-14:],
                "dialog_seen": "Do you want" in before or "1." in before,
            }
            if pr is None and not row["dialog_seen"]:
                row["outcome"] = "unknown: no permission dialog appeared for this round"
                res["rounds"].append(row)
                t.keys("C-u")
                time.sleep(1.0)
                continue
            tm(SOCK_PROBE, "send-keys", "-t", t.t, *keyargs, run=run)
            time.sleep(3.5)
            after = t.snap(f"{idx:02d}b-{label.lower()}-after")
            row["screen_after_lines"] = [ln.rstrip() for ln in after.splitlines() if ln.strip()][-14:]
            row["dialog_still_up"] = "Do you want" in after
            row["hooks_after_key"] = event_names(hl, n0)
            # settle: let the turn finish if the key ran or refused the tool
            wait_event(hl, ev("Stop"), 60, after=n0)
            time.sleep(2.0)
            settled = t.snap(f"{idx:02d}c-{label.lower()}-settled")
            row["screen_settled_lines"] = [ln.rstrip() for ln in settled.splitlines() if ln.strip()][-14:]
            row["hooks_total"] = event_names(hl, n0)
            row["tool_ran"] = os.path.exists(os.path.join(work, fname))
            row["file"] = fname
            res["rounds"].append(row)
            run.save(f"{idx:02d}d-{label.lower()}-row.json", json.dumps(row, indent=1) + "\n")
            # leave the pane clean for the next round
            if row["dialog_still_up"]:
                t.keys("Escape")
                time.sleep(1.5)
            t.keys("Escape")
            time.sleep(0.8)
            t.keys("C-u")
            time.sleep(1.2)
            t.snap(f"{idx:02d}e-{label.lower()}-reset")

        res["cwd_listing"] = sorted(os.listdir(work))
        run.save("99-cwd-listing.txt", "\n".join(res["cwd_listing"]) + "\n")
        run.save("hook-event-sequence.txt", "\n".join(event_names(hl, 0)) + "\n")
    finally:
        kill_socket(SOCK_PROBE, run)
        run.finish((SOCK_PROBE,))
        shutil.rmtree(os.path.dirname(work), ignore_errors=True)


# ============================================================================================

PROBES = {"p1": probe_p1, "p2": probe_p2, "p3": probe_p3, "p4": probe_p4}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="p1,p2,p3,p4",
                    help="comma-separated subset of p1,p2,p3,p4")
    args = ap.parse_args()
    for key in [k.strip() for k in args.only.split(",") if k.strip()]:
        if key not in PROBES:
            raise SystemExit(f"unknown probe {key!r}; choose from {sorted(PROBES)}")
        PROBES[key]()


if __name__ == "__main__":
    main()
