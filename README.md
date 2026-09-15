# syslogng-webui

A tiny, all-in-one syslog receiver with a built-in web UI for browsing the logs.

Runs `syslog-ng` to receive UDP/TCP syslog on port 514, writes one log file
per sending host per day, and serves a lightweight web viewer (no database,
no external dependencies) to browse, filter, and search those files from a
browser. Built for a Raspberry Pi, but runs anywhere Docker does (amd64 and
arm64).

## Quick start

```bash
docker run -d \
  --name syslogng-webui \
  -p 514:514/udp \
  -p 514:514/tcp \
  -p 8082:8082 \
  -v ./logs:/var/log/syslogng \
  -e TZ=America/Toronto \
  ghcr.io/Installation-04/syslogng-webui:latest
```

Or with the included `docker-compose.yml`:

```bash
docker compose up -d
```

Then open `http://<host-ip>:8082`.

Point any device's remote syslog setting at this host's IP, port 514/UDP
(or TCP) — network gear, Omada controllers, firewalls, anything that speaks
standard syslog.

## Web UI features

- Browse by sending host, then by date
- Include / exclude text filters, with optional regex and case-sensitive matching
- Sort oldest-first or newest-first
- Adjustable fetch depth (last 500 / 1000 / 2000 / 5000 lines)
- Auto-refresh every 5 seconds
- Match highlighting

## Configuration

| Variable   | Default             | Description                                  |
|------------|----------------------|-----------------------------------------------|
| `LOG_ROOT` | `/var/log/syslogng`  | Where log files are written and read from     |
| `PORT`     | `8082`                | Web UI port                                   |
| `TZ`       | `UTC`                 | Container timezone (affects log timestamps)   |

Log files land at `$LOG_ROOT/<sending-host-ip>/<YYYY-MM-DD>.log`.

## Storage management

This image doesn't cap total disk usage on its own. For log rotation and
size limits, run `logrotate` on the host against the mounted volume, or use
a small cron script to prune oldest files past a size threshold. See the
`examples/` folder for a sample logrotate config and a total-size-cap script.

## Building locally

```bash
docker build -t syslogng-webui .
```

## License

MIT — see [LICENSE](LICENSE).
