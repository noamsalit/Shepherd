#!/bin/sh
# $1=tag $2=seconds
cat >/dev/null
echo "$1 start $(date -u +%H:%M:%S.%3N) pid=$$" >> /root/Shepherd/docs/probes/2026-09-14-schemas/hooks/live/R02_timeout_sync/timing.txt
sleep $2
echo "$1 end $(date -u +%H:%M:%S.%3N)" >> /root/Shepherd/docs/probes/2026-09-14-schemas/hooks/live/R02_timeout_sync/timing.txt
exit 0
