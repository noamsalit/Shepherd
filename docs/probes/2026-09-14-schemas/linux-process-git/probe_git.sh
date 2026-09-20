#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# RENAMED 2026-09-20. The throwaway branch and worktree this script creates under
# `mktemp -d` used to carry a former employer's project prefix; it now uses
# `PROJ-`, at the owner's instruction. The rename was applied here AND to the
# capture in `captures/git.txt`, so the two still agree: re-running this script
# reproduces that capture. No logic changed.
# ─────────────────────────────────────────────────────────────────────────────
# Shepherd linux-process-git probe: git outputs used by workspace/repo discovery and cwd -> repo binding (D22).
#
# Re-run: bash docs/probes/2026-09-14-schemas/linux-process-git/probe_git.sh
#
# Read-only commands on /root/Shepherd and /root/src/cc10x-qa. Everything mutating happens in throwaway
# clones under a mktemp -d directory in /tmp: a main clone, a linked worktree (branch + detached + locked +
# prunable), a bare repo, a no-remote repo, a nested repo, a symlinked path, ssh/https/scp-like/insteadOf/
# credential-bearing remote URLs, and a repo owned by another uid (safe.directory).
# Every command is printed as "$ <cmd>" followed by its stdout+stderr and "[rc=N]".
set -u
E="$(cd "$(dirname "$0")" && pwd)"; C="$E/captures"; mkdir -p "$C"
O="$C/git.txt"
exec > "$O" 2>&1
echo "claude_version: $(claude --version)"; echo "date_utc: $(date -u +%FT%TZ)"; git --version
T="$(mktemp -d /tmp/shp-lpg-git.XXXXXX)"; echo "tmpdir: $T"
export GIT_CONFIG_NOSYSTEM=1 GIT_AUTHOR_NAME=probe GIT_AUTHOR_EMAIL=p@example.invalid GIT_COMMITTER_NAME=probe GIT_COMMITTER_EMAIL=p@example.invalid
run() { echo "\$ $*"; ( "$@" ); echo "[rc=$?]"; }
runin() { local d=$1; shift; echo "\$ (cd $d) $*"; ( cd "$d" && "$@" ); echo "[rc=$?]"; }

echo; echo "######## A. read-only: real repos"
for R in /root/Shepherd /root/src/cc10x-qa; do
  run git -C "$R" rev-parse --show-toplevel --git-common-dir --git-dir --is-bare-repository --is-inside-work-tree
  run git -C "$R" rev-parse --path-format=absolute --git-common-dir --git-dir
  run git -C "$R" remote
  run git -C "$R" remote get-url origin
  run git -C "$R" worktree list --porcelain
  run git -C "$R" symbolic-ref -q --short HEAD
done
run git -C /root/Shepherd/docs/specs rev-parse --show-toplevel --show-prefix --git-common-dir

echo; echo "######## B. throwaway main repo + clone with remotes in several URL forms"
mkdir -p "$T/origin-src" && git -C "$T/origin-src" init -q -b main && echo a > "$T/origin-src/f" && git -C "$T/origin-src" add f && git -C "$T/origin-src" commit -qm init
run git clone -q "$T/origin-src" "$T/main"
run git -C "$T/main" remote get-url origin
run git -C "$T/main" remote add gh-ssh git@github.com:example-org/example-repo.git
run git -C "$T/main" remote add gh-sshurl ssh://git@github.com/example-org/example-repo.git
run git -C "$T/main" remote add gh-https https://github.com/example-org/example-repo.git
run git -C "$T/main" remote add gl-https-noext https://gitlab.com/example-org/sub-group/example-repo
run git -C "$T/main" remote add with-cred https://oauth2:FAKE_TOKEN_NOT_REAL@gitlab.com/example-org/example-repo.git
run git -C "$T/main" remote add rewritten gh:example-org/example-repo.git
run git -C "$T/main" config url."git@github.com:".insteadOf gh:
for r in origin gh-ssh gh-sshurl gh-https gl-https-noext with-cred rewritten; do
  run git -C "$T/main" remote get-url "$r"
done
echo "(config value vs get-url for the insteadOf remote)"
run git -C "$T/main" config --get remote.rewritten.url
run git -C "$T/main" remote get-url --push gh-https
run git -C "$T/main" remote -v
run git -C "$T/main" remote get-url does-not-exist

echo; echo "######## C. rev-parse from main tree root, a subdir, and inside .git"
mkdir -p "$T/main/src/pkg"
runin "$T/main" git rev-parse --show-toplevel --git-common-dir --git-dir
runin "$T/main/src/pkg" git rev-parse --show-toplevel --show-prefix --git-common-dir --git-dir
runin "$T/main/src/pkg" git rev-parse --path-format=absolute --git-common-dir --git-dir
runin "$T/main/.git" git rev-parse --show-toplevel
runin "$T/main/.git" git rev-parse --is-inside-git-dir --git-dir

echo; echo "######## D. linked worktrees: branch, detached, locked, prunable"
run git -C "$T/main" worktree add -q -b feat/PROJ-1 "$T/main-wt/PROJ-1"
run git -C "$T/main" worktree add -q --detach "$T/main-wt/detached"
run git -C "$T/main" worktree add -q -b feat/locked "$T/main-wt/locked"
run git -C "$T/main" worktree lock --reason "probe lock reason" "$T/main-wt/locked"
run git -C "$T/main" worktree add -q -b feat/gone "$T/main-wt/gone"
rm -rf "$T/main-wt/gone"
echo "\$ cat $T/main-wt/PROJ-1/.git"; cat "$T/main-wt/PROJ-1/.git"; echo "[file type: $(stat -c %F "$T/main-wt/PROJ-1/.git")]"
echo "\$ ls $T/main/.git/worktrees"; ls "$T/main/.git/worktrees"
for f in gitdir commondir HEAD; do echo "\$ cat .git/worktrees/PROJ-1/$f"; cat "$T/main/.git/worktrees/PROJ-1/$f"; done
echo "\$ cat .git/worktrees/locked/locked"; cat "$T/main/.git/worktrees/locked/locked"; echo
run git -C "$T/main" worktree list --porcelain
echo "(-z output with NUL shown as \\0)"; git -C "$T/main" worktree list --porcelain -z | sed 's/\x0/\\0\n/g' | head -8
run git -C "$T/main" worktree list
mkdir -p "$T/main-wt/PROJ-1/src"
runin "$T/main-wt/PROJ-1/src" git rev-parse --show-toplevel --git-common-dir --git-dir
runin "$T/main-wt/PROJ-1/src" git rev-parse --path-format=absolute --show-toplevel --git-common-dir --git-dir
run git -C "$T/main-wt/PROJ-1" worktree list --porcelain
runin "$T/main-wt/detached" git symbolic-ref -q --short HEAD
runin "$T/main-wt/detached" git rev-parse --abbrev-ref HEAD

echo; echo "######## E. detached HEAD in the MAIN tree"
run git -C "$T/main" checkout -q --detach
run git -C "$T/main" worktree list --porcelain
run git -C "$T/main" rev-parse --abbrev-ref HEAD
run git -C "$T/main" checkout -q main

echo; echo "######## F. bare repo, and a worktree of a bare repo"
run git clone -q --bare "$T/origin-src" "$T/bare.git"
run git -C "$T/bare.git" rev-parse --show-toplevel
run git -C "$T/bare.git" rev-parse --is-bare-repository --git-common-dir --git-dir
run git -C "$T/bare.git" remote get-url origin
run git -C "$T/bare.git" worktree list --porcelain
run git -C "$T/bare.git" worktree add -q "$T/bare-wt/main2" -b main2
run git -C "$T/bare.git" worktree list --porcelain
runin "$T/bare-wt/main2" git rev-parse --show-toplevel --path-format=absolute --git-common-dir

echo; echo "######## G. no remote, no commits"
mkdir -p "$T/noremote" && git -C "$T/noremote" init -q -b main
run git -C "$T/noremote" remote
run git -C "$T/noremote" remote get-url origin
run git -C "$T/noremote" rev-parse --show-toplevel
run git -C "$T/noremote" rev-parse HEAD
run git -C "$T/noremote" worktree list --porcelain

echo; echo "######## H. not a repo"
mkdir -p "$T/plain/dir"
run git -C "$T/plain/dir" rev-parse --show-toplevel
echo "\$ GIT_CEILING_DIRECTORIES=$T git -C $T/plain/dir rev-parse --show-toplevel"; GIT_CEILING_DIRECTORIES="$T" git -C "$T/plain/dir" rev-parse --show-toplevel; echo "[rc=$?]"

echo; echo "######## I. nested repo inside a repo (innermost wins?) and a submodule"
mkdir -p "$T/main/vendor/inner" && git -C "$T/main/vendor/inner" init -q -b main
mkdir -p "$T/main/vendor/inner/deep"
runin "$T/main/vendor/inner/deep" git rev-parse --show-toplevel --show-superproject-working-tree
run git -C "$T/main" status --porcelain
run git -C "$T/main" -c protocol.file.allow=always submodule add -q "$T/origin-src" mods/sub
run cat "$T/main/mods/sub/.git"
runin "$T/main/mods/sub" git rev-parse --show-toplevel --show-superproject-working-tree --path-format=absolute --git-common-dir

echo; echo "######## J. symlinked path"
ln -s "$T/main" "$T/link-to-main"
runin "$T/link-to-main/src" git rev-parse --show-toplevel --show-cdup
echo "\$ realpath $T/link-to-main/src"; realpath "$T/link-to-main/src"

echo; echo "######## K. repo owned by another uid (safe.directory)"
run git clone -q "$T/origin-src" "$T/foreign"
chown -R nobody:nogroup "$T/foreign"
run git -C "$T/foreign" rev-parse --show-toplevel
run git -C "$T/foreign" remote get-url origin
run git -c safe.directory="$T/foreign" -C "$T/foreign" rev-parse --show-toplevel

echo; echo "######## L. worktree remove / prune"
run git -C "$T/main" worktree prune --dry-run -v
run git -C "$T/main" worktree remove "$T/main-wt/detached"
run git -C "$T/main" worktree remove "$T/main-wt/locked"
run git -C "$T/main" worktree list --porcelain

rm -rf "$T"
echo "cleaned: $T"; echo "done: $(date -u +%FT%TZ)"
