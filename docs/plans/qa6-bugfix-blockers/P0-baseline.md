# P0 — baseline (tree 5fec176 = be9db6f + qa6 re-qa-build round 4; src/ == main)

Note: the first baseline at be9db6f showed 4 extra boundary failures caused by tests/qa6;
fixed in 5fec176 (tests/qa6 only). This baseline is taken after that fix.

1. `.venv/bin/pytest -p no:randomly` — interrupted: 3 qa5 collection errors (render_check import). Expected.
2. `.venv/bin/pytest -p no:randomly --ignore=tests/qa5` — 
   BASELINE_DEFAULT_FAILS:
   - FAILED tests/e2e/test_live_lane_typechecks.py::test_every_module_the_default_run_deselects_still_type_checks
   - FAILED tests/e2e/test_live_lane_typechecks.py::test_the_live_net_covers_the_m4_modules
   - FAILED tests/test_core_master.py::test_the_sdk_floor_is_the_version_this_host_measured
   - FAILED tests/test_packaging.py::test_the_vendor_file_ships_in_a_built_wheel
   - ERROR tests/boundaries/test_collected_node_ids.py::test_a_stale_exemption_is_caught
   - ERROR tests/boundaries/test_collected_node_ids.py::test_every_node_id_frozen_at_step_0b_still_collects
   - ERROR tests/boundaries/test_collected_node_ids.py::test_a_second_deletion_is_caught
3. `.venv/bin/pytest -p no:randomly tests/boundaries` — 
   BASELINE_BOUNDARY_FAILS:
   - ERROR tests/boundaries/test_collected_node_ids.py::test_a_stale_exemption_is_caught
   - ERROR tests/boundaries/test_collected_node_ids.py::test_every_node_id_frozen_at_step_0b_still_collects
   - ERROR tests/boundaries/test_collected_node_ids.py::test_a_second_deletion_is_caught
4. `.venv/bin/mypy --strict src` — 2 errors (BC-PF1, darwin only; identical on main):
   - src/shepherd/host/linux.py:104 Module has no attribute "SO_PEERCRED" [attr-defined]
   - src/shepherd/host/detect.py:29 Statement is unreachable [unreachable]
   Phases' "mypy clean" = no error beyond these two.
5. qa6 comparison set: .cc10x/qa/wf-20260923T182839Z-9adb11fc/runs/qa6-20260924T040750Z/records/
