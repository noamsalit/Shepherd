# P0 — baseline (fix/qa6-rulings @ 4209fc7)

Measured 2026-09-27 in the main checkout. Equals `docs/plans/qa6-bugfix-blockers/P0-baseline.md`
plus the known host-timing flaky s7 test (it fires on base too).

## QR_BASELINE_DEFAULT_FAILS
`.venv/bin/pytest -p no:randomly --ignore=tests/qa5` → 5 failed, 2311 passed, 11 skipped, 345 deselected, 3 errors (488 s)
- FAILED tests/e2e/test_live_lane_typechecks.py::test_every_module_the_default_run_deselects_still_type_checks
- FAILED tests/e2e/test_live_lane_typechecks.py::test_the_live_net_covers_the_m4_modules
- FAILED tests/qa/test_s7_shutdown_in_flight.py::test_clause_20_holds_on_every_run_and_the_branch_is_recorded (known flaky)
- FAILED tests/test_core_master.py::test_the_sdk_floor_is_the_version_this_host_measured
- FAILED tests/test_packaging.py::test_the_vendor_file_ships_in_a_built_wheel
- ERROR ×3 tests/boundaries/test_collected_node_ids.py (qa5 collection)

## QR_BASELINE_BOUNDARY_FAILS
`pytest -p no:randomly tests/boundaries` → 102 passed, 3 errors (the same 3 ERRORs)

## mypy --strict src
2 errors: linux.py:104 SO_PEERCRED, detect.py:29 unreachable (131 files)

## qa6 comparison set
`qa6-20260924T124009Z` (full), `qa6-20260927T061932Z` (wave 6), `qa6-20260927T062958Z` (waves 1+8)

## QR_HOST_BEFORE
```
f99112b6db8b5adb5014792c84e75cac806ec12ecb73a2dee3a1ef95a7f1c52b  /Users/noamsalit/.claude/settings.json
/Users/noamsalit/.local/share/claude/versions/2.1.283
total 0
drwx------@   5 noamsalit  wheel   160 Sep 27 09:34 .
drwxrwxrwt  191 root       wheel  6112 Sep 27 16:32 ..
srw-rw----@   1 noamsalit  wheel     0 Sep 20 18:35 shepherd-m3-live
srw-rw----@   1 noamsalit  wheel     0 Sep 20 16:55 shepherd-m3-probe
srw-rw----@   1 noamsalit  wheel     0 Sep 20 18:37 shepherd-m3-rename
COMMAND   PID      USER   FD   TYPE             DEVICE SIZE/OFF NODE NAME
Python  48395 noamsalit    3u  IPv4 0x5cabbf20a551abe4      0t0  TCP 127.0.0.1:8787 (LISTEN)
```
