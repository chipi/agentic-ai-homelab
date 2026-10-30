#!/bin/zsh
# Ensure the 'main' workbench session exists with all project windows (detached).
# Idempotent: exits 0 immediately if the session already exists.
# Run by ~/bin/wb, and by the LaunchAgent ~/Library/LaunchAgents/com.chipi.workbench.plist
# (which fires on 'claude' session start / SSH login — NOT at boot; see that
# file's comment for why, and what a true at-boot job would require).
TM=/usr/local/bin/tmux; [ -x "$TM" ] || TM="$(command -v tmux)"   # Mac path first, else PATH
S=main
$TM has-session -t $S 2>/dev/null && exit 0
# Close Listening first: the public split checkout, the private repos mounted in it at apps/<name>
# (their make test needs that mount), infra, and the private eval data.
$TM new-session -d -s $S -n cl-public -c ~/projects/podcast-player
$TM new-window  -t $S -n cl-common       -c ~/projects/podcast-player/apps/common
$TM new-window  -t $S -n cl-player       -c ~/projects/podcast-player/apps/player
$TM new-window  -t $S -n cl-studio       -c ~/projects/podcast-player/apps/studio
$TM new-window  -t $S -n infra           -c ~/projects/infra
$TM new-window  -t $S -n podcast-eval    -c ~/projects/podcast-scraper-eval-data
$TM new-window  -t $S -n abyss           -c ~/projects/abyss
$TM new-window  -t $S -n feed-ingest     -c ~/projects/podcast_scraper
$TM new-window  -t $S -n orrery          -c ~/projects/orrery
$TM select-window -t $S:1
