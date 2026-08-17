#!/bin/zsh
# Ensure the 'main' workbench session exists with all project windows (detached).
# Idempotent: exits 0 immediately if the session already exists.
# Run by ~/bin/wb, and by the LaunchAgent ~/Library/LaunchAgents/com.chipi.workbench.plist
# (which fires on 'claude' session start / SSH login — NOT at boot; see that
# file's comment for why, and what a true at-boot job would require).
TM=/usr/local/bin/tmux
S=main
$TM has-session -t $S 2>/dev/null && exit 0
$TM new-session -d -s $S -n abyss -c ~/projects/abyss
$TM new-window  -t $S -n podcast-eval    -c ~/projects/podcast-scraper-eval-data
$TM new-window  -t $S -n podcast-private -c ~/projects/podcast_scraper-private
$TM new-window  -t $S -n feed-ingest     -c ~/projects/podcast_scraper
$TM new-window  -t $S -n player          -c ~/projects/podcast-player/web/learning-player
$TM new-window  -t $S -n orrery          -c ~/projects/orrery
$TM select-window -t $S:1
