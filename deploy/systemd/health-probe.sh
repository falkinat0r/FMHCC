#!/bin/sh
# HCC Health-Probe — systemd ExecStartPost (R1-Deploy-Review).
#
# Installation: durch scripts/deploy-lxc.sh auf
#   /usr/local/lib/hcc/health-probe.sh (0755)
#
# Funktion: wartet bis zu 30 s darauf, dass die API auf
# http://127.0.0.1:8000/api/v1/health/live mit HTTP 200 antwortet.
# Exit 0 = gesund, 1 = nicht gesund => systemd meldet den Start
# als fehlgeschlagen (keine stille 'gestartet, aber tot'-Konstellation).

set -u

PROBE=/opt/hcc/current/backend/.venv/bin/python
URL='http://127.0.0.1:8000/api/v1/health/live'

i=1
while [ "$i" -le 30 ]; do
    if "$PROBE" -c "
import sys, urllib.request
try:
    r = urllib.request.urlopen('$URL', timeout=2)
    sys.exit(0 if r.status == 200 else 1)
except Exception:
    sys.exit(1)
"
    then
        exit 0
    fi
    i=$((i + 1))
    sleep 1
done

echo "hcc-api: Health-Probe nach 30 s fehlgeschlagen ($URL)" >&2
exit 1
