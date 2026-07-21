#!/bin/bash
# Periodic fleet-metrics push — run by launchd (com.homelab.bugfix-metrics) every
# 2 min so the Grafana "Bug-fix Fleet" funnel stays live. Queries GitHub for the
# flow: label counts and pushes them to VictoriaMetrics.
export PATH=/usr/local/bin:$PATH
cd "$(dirname "$0")" || exit 1
exec node --env-file=.env dist/main.js metrics >> /tmp/bugfix-metrics.log 2>&1
