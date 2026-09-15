#!/bin/bash
set -e

mkdir -p "$LOG_ROOT"

echo "[syslogng-webui] starting syslog-ng (listening on 514/udp + 514/tcp)"
syslog-ng -F --no-caps -f /etc/syslog-ng/syslog-ng.conf &
SYSLOG_PID=$!

echo "[syslogng-webui] starting web UI on port ${PORT}"
python3 /app/app.py &
WEB_PID=$!

trap 'echo "[syslogng-webui] shutting down"; kill -TERM $SYSLOG_PID $WEB_PID 2>/dev/null' TERM INT

# exit the container if either process dies
wait -n $SYSLOG_PID $WEB_PID
kill $SYSLOG_PID $WEB_PID 2>/dev/null
wait
