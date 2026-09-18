#!/bin/sh
{
echo "inside pane: TMUX=$TMUX"
echo "--- bare 'tmux display-message -p #{socket_path}|#{session_name}' (no -L):"
tmux display-message -p '#{socket_path}|#{session_name}'
echo "--- bare 'tmux list-sessions -F #{session_name}' (no -L):"
tmux list-sessions -F '#{session_name}'
echo "--- 'tmux -L shp-gap-name-b list-sessions' (explicit -L):"
tmux -L shp-gap-name-b list-sessions -F '#{socket_path}|#{session_name}'
} > "$1" 2>&1
