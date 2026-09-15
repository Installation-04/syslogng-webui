#!/bin/bash
set -e

mkdir -p "$LOG_ROOT"
chown root:webui "$LOG_ROOT" 2>/dev/null || true
chmod 0750 "$LOG_ROOT" 2>/dev/null || true

generate_syslog_conf() {
  local conf="/etc/syslog-ng/syslog-ng.conf"
  {
    echo '@version: 4.6'
    echo '@include "scl.conf"'
    echo
    echo 'source s_net {'
    echo '    udp(ip("0.0.0.0") port(514));'
    echo '    tcp(ip("0.0.0.0") port(514));'
    if [ -n "$TLS_CERT_FILE" ] && [ -n "$TLS_KEY_FILE" ]; then
      echo -n '    tcp(ip("0.0.0.0") port('"${TLS_PORT:-6514}"') tls(key-file("'"$TLS_KEY_FILE"'") cert-file("'"$TLS_CERT_FILE"'")'
      if [ -n "$TLS_CA_FILE" ]; then
        echo -n ' ca-file("'"$TLS_CA_FILE"'") peer-verify(optional-untrusted)'
      fi
      echo '));'
    fi
    echo '};'
    echo

    if [ -n "$ALLOWED_SOURCES" ]; then
      echo 'filter f_allowed {'
      first=1
      IFS=',' read -ra NETS <<< "$ALLOWED_SOURCES"
      for raw in "${NETS[@]}"; do
        net="$(echo "$raw" | xargs)"
        [ -z "$net" ] && continue
        if [ "$first" -eq 1 ]; then
          echo -n '    netmask("'"$net"'")'
          first=0
        else
          echo -n ' or netmask("'"$net"'")'
        fi
      done
      echo ';'
      echo '};'
      echo
    fi

    echo 'destination d_omada {'
    echo '    file("'"$LOG_ROOT"'/${HOST}/${YEAR}-${MONTH}-${DAY}.log"'
    echo '        create-dirs(yes)'
    echo '        owner("root") group("webui") perm(0640)'
    echo '        dir-owner("root") dir-group("webui") dir-perm(0750)'
    echo '        template("$ISODATE $HOST $MSGHDR$MSG\n")'
    echo '    );'
    echo '};'
    echo

    echo 'log {'
    echo '    source(s_net);'
    if [ -n "$ALLOWED_SOURCES" ]; then
      echo '    filter(f_allowed);'
    fi
    echo '    destination(d_omada);'
    echo '};'
  } > "$conf"
}

enforce_retention() {
  if [ -n "$MAX_LOG_DAYS" ]; then
    find "$LOG_ROOT" -type f \( -name "*.log" -o -name "*.gz" \) -mtime "+${MAX_LOG_DAYS}" -print -delete 2>/dev/null \
      | while read -r f; do echo "[syslogng-webui] retention: removed $f (older than ${MAX_LOG_DAYS}d)"; done
  fi
  if [ -n "$MAX_TOTAL_SIZE_GB" ]; then
    max_kb=$((MAX_TOTAL_SIZE_GB * 1024 * 1024))
    current_kb=$(du -s "$LOG_ROOT" 2>/dev/null | cut -f1)
    if [ -n "$current_kb" ] && [ "$current_kb" -gt "$max_kb" ]; then
      find "$LOG_ROOT" -type f \( -name "*.log" -o -name "*.gz" \) -printf '%T@ %p\n' 2>/dev/null \
        | sort -n | while read -r _ file; do
            current_kb=$(du -s "$LOG_ROOT" 2>/dev/null | cut -f1)
            [ -n "$current_kb" ] && [ "$current_kb" -le "$max_kb" ] && break
            echo "[syslogng-webui] retention: removing $file (over ${MAX_TOTAL_SIZE_GB}GB cap)"
            rm -f "$file"
          done
    fi
  fi
}

retention_loop() {
  while true; do
    sleep "${RETENTION_INTERVAL_SEC:-3600}"
    enforce_retention
  done
}

generate_syslog_conf

echo "[syslogng-webui] starting syslog-ng (listening on 514/udp + 514/tcp${TLS_CERT_FILE:+, TLS on ${TLS_PORT:-6514}/tcp})"
syslog-ng -F --no-caps -f /etc/syslog-ng/syslog-ng.conf &
SYSLOG_PID=$!

RETENTION_PID=""
if [ -n "$MAX_LOG_DAYS" ] || [ -n "$MAX_TOTAL_SIZE_GB" ]; then
  echo "[syslogng-webui] retention enabled (days=${MAX_LOG_DAYS:-none} size_cap_gb=${MAX_TOTAL_SIZE_GB:-none})"
  retention_loop &
  RETENTION_PID=$!
fi

echo "[syslogng-webui] starting web UI on port ${PORT}"
su-exec webui python3 /app/app.py &
WEB_PID=$!

trap 'echo "[syslogng-webui] shutting down"; kill -TERM $SYSLOG_PID $WEB_PID $RETENTION_PID 2>/dev/null' TERM INT

# exit the container if either core process dies
wait -n $SYSLOG_PID $WEB_PID
kill $SYSLOG_PID $WEB_PID $RETENTION_PID 2>/dev/null
wait
