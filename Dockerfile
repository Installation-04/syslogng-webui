FROM alpine:3.20

RUN apk add --no-cache syslog-ng python3 bash tzdata su-exec \
    && addgroup -S webui \
    && adduser -S -G webui -H webui

COPY app.py /app/app.py
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENV LOG_ROOT=/var/log/syslogng
ENV PORT=8333
ENV TZ=UTC

EXPOSE 514/udp 514/tcp 6514/tcp 8333
VOLUME ["/var/log/syslogng"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD nc -z 127.0.0.1 "${PORT}" || exit 1

ENTRYPOINT ["/entrypoint.sh"]
