#!/bin/sh
cat >/dev/null
echo 'SHP_BLOCKED_BY_HOOK exit 2' >&2
exit 2
