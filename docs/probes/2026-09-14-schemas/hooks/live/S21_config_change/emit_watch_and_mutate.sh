#!/bin/sh
cat >/dev/null
( sleep 6; printf '%s' '{"env":{"SHP_X":"1"}}' > /tmp/shp-hooks-config-33ijfqat/.claude/settings.local.json; sleep 3; rm -f /tmp/shp-hooks-config-33ijfqat/watched.txt; sleep 3; echo new > /tmp/shp-hooks-config-33ijfqat/watched.txt ) >/dev/null 2>&1 &
printf '%s' '{"hookSpecificOutput":{"hookEventName":"SessionStart","watchPaths":["/tmp/shp-hooks-config-33ijfqat/watched.txt"]}}'
