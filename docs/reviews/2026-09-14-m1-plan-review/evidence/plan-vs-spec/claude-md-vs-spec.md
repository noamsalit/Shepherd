# CLAUDE.md vs spec (2026-09-14)
- CLAUDE.md L28-29: "The user's live sessions run on the `shepherd` socket (`tmux -L shepherd ls`). Leave them alone."
- spec §9 L984 (uncommitted edit): "Each `owned` session is a tmux session named `shepherd_<session_id>`, on a **dedicated socket** (`tmux -L shepherd`)."
- spec §9 L990: "`tmux -L shepherd attach -t shepherd_<id>`"
- probe docs/probes/2026-09-13-tmux-tui-spike.md constraint 3: socket name must be configuration.
- plan DV-21: config key tmux_socket default "shepherd" (only non-default profiles barred from it).
- reading tmux-shepherd-socket-reading.txt: socket `shepherd` currently holds 3 sessions; this review's own $TMUX is /tmp/tmux-0/shepherd.
Agreements: no bare kill-server (CLAUDE.md rule 1 / spec L2182-2185); throwaway socket for spikes (rule 2 / L2163, L2182); -L on every call even inside tmux (rule 3 / L2186-2189); no ':' in names (rule 4 / L2191-2197).
