#!/usr/bin/env python3
"""Pane program for the gap-fill key-delivery probe (2026-09-14).
Puts its tty in raw mode, optionally enables bracketed paste (like the Claude Code TUI does),
and appends every read() chunk as hex + repr to a JSONL file, so we see exactly which bytes
tmux delivered to the pane. Also logs SIGWINCH sizes. Usage: keydump.py <out.jsonl> [--bracketed]"""
import json, os, select, signal, sys, termios, time, tty, fcntl, struct
out = open(sys.argv[1], "a", buffering=1)
fd = sys.stdin.fileno()
def size():
    r, c, _, _ = struct.unpack("HHHH", fcntl.ioctl(fd, termios.TIOCGWINSZ, b"\0" * 8))
    return f"{c}x{r}"
def rec(**kw):
    kw["t"] = round(time.time(), 3); out.write(json.dumps(kw) + "\n")
signal.signal(signal.SIGWINCH, lambda *a: rec(sigwinch=size()))
tty.setraw(fd)
if "--bracketed" in sys.argv:
    os.write(1, b"\x1b[?2004h")
rec(start=True, size=size(), bracketed="--bracketed" in sys.argv, isig=False)
os.write(1, b"keydump ready\r\n")
while True:
    try:
        r, _, _ = select.select([fd], [], [], 1.0)
    except InterruptedError:
        continue
    if r:
        b = os.read(fd, 4096)
        if not b:
            break
        rec(hex=b.hex(), repr=repr(b))
        os.write(1, (b.hex() + "\r\n").encode())
