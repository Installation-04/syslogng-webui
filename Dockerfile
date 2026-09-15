FROM alpine:3.20

RUN apk add --no-cache syslog-ng python3 bash tzdata

COPY app.py /app/app.py
COPY syslog-ng.conf /etc/syslog-ng/syslog-ng.conf
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENV LOG_ROOT=/var/log/syslogng
ENV PORT=8082
ENV TZ=UTC

EXPOSE 514/udp 514/tcp 8082
VOLUME ["/var/log/syslogng"]

ENTRYPOINT ["/entrypoint.sh"]
