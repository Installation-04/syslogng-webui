# syslogng-webui

A tiny, all-in-one syslog receiver with a built-in web UI for browsing the logs.

Runs `syslog-ng` to receive UDP/TCP syslog on port 514, writes one log file
per sending host per day, and serves a lightweight web viewer (no database,
no external dependencies) to browse, filter, search, and live-tail those
files from a browser. Built for a Raspberry Pi, but runs anywhere Docker does
(amd64 and arm64).

## Quick start

**One-line install** (Linux, amd64 or arm64 — installs and starts the container):

```bash
curl -fsSL https://raw.githubusercontent.com/Installation-04/syslogng-webui/main/scripts/install.sh | bash
```

It's configurable via environment variables (`PORT`, `LOG_DIR`, `TZ`, `IMAGE_TAG`,
`CONTAINER_NAME`) — see the comments at the top of
[`scripts/install.sh`](scripts/install.sh) for details. Re-run with `FORCE=1` to
replace an existing install (your log data is untouched).

**Or manually:**

```bash
docker run -d \
  --name syslogng-webui \
  -p 514:514/udp \
  -p 514:514/tcp \
  -p 8333:8333 \
  -v ./logs:/var/log/syslogng \
  -e TZ=America/Toronto \
  ghcr.io/Installation-04/syslogng-webui:latest
```

Or with the included `docker-compose.yml`:

```bash
docker compose up -d
```

Then open `http://<host-ip>:8333`.

Point any device's remote syslog setting at this host's IP, port 514/UDP
(or TCP) — network gear, Omada controllers, firewalls, anything that speaks
standard syslog.

## Web UI features

- Browse by sending host, then by date
- Include / exclude text filters, with optional regex and case-sensitive matching
- Sort oldest-first or newest-first
- Adjustable fetch depth (last 500 / 1000 / 2000 / 5000 lines)
- Auto-refresh every 5 seconds, or true **live tail** (server-sent events)
- Match highlighting
- **Download** the currently viewed log file
- **Search** across all hosts/files at once, not just the one currently open
- **Stats** tab: per-host file count, total size on disk, and last-seen time, with a
  **dead-host badge** for any host that's gone quiet longer than a configurable threshold
- Light/dark **theme toggle** (defaults to your system preference)
- **Saved filter presets** — save/apply/delete named include/exclude/regex/sort combos
- **Permalinks** — the URL always reflects the current host/file/filters/tab, and a
  "Copy link" button puts a shareable link on your clipboard
- Your filter/sort/theme preferences persist across reloads (stored in the browser)

## Configuration

| Variable              | Default              | Description                                                        |
|------------------------|----------------------|----------------------------------------------------------------------|
| `LOG_ROOT`             | `/var/log/syslogng`  | Where log files are written and read from                          |
| `PORT`                 | `8333`                | Web UI port                                                         |
| `TZ`                   | `UTC`                 | Container timezone (affects log timestamps)                        |
| `AUTH_USER`            | `admin`               | Basic Auth username for the web UI (only enforced if `AUTH_TOKEN` set) |
| `AUTH_TOKEN`           | *(unset)*             | If set, the web UI requires HTTP Basic Auth with this password      |
| `MAX_LOG_DAYS`         | *(unset)*             | Delete log files older than N days (checked hourly)                 |
| `MAX_TOTAL_SIZE_GB`    | *(unset)*             | Delete oldest log files once `LOG_ROOT` exceeds this size (checked hourly) |
| `RETENTION_INTERVAL_SEC` | `3600`               | How often retention is enforced, in seconds                         |
| `TLS_CERT_FILE`        | *(unset)*             | Path (inside the container) to a TLS cert to enable TLS syslog input |
| `TLS_KEY_FILE`         | *(unset)*             | Path to the matching TLS private key                                |
| `TLS_CA_FILE`          | *(unset)*             | Optional CA bundle to verify client certs against                   |
| `TLS_PORT`             | `6514`                | Port for TLS syslog input (only listens if cert/key are set)        |
| `ALLOWED_SOURCES`      | *(unset)*             | Comma-separated CIDR list; if set, only these sources may send logs |

Log files land at `$LOG_ROOT/<sending-host-ip>/<YYYY-MM-DD>.log`.

### Securing the web UI

By default the web UI has no authentication — anyone who can reach the port
can read every host's logs. Set `AUTH_USER`/`AUTH_TOKEN` to require an HTTP
Basic Auth login, e.g.:

```bash
docker run ... -e AUTH_USER=admin -e AUTH_TOKEN=change-me ...
```

### TLS syslog input

To accept syslog over TLS (in addition to plain UDP/TCP 514), mount a cert
and key and set `TLS_CERT_FILE`/`TLS_KEY_FILE` (and expose `TLS_PORT`,
default `6514/tcp`):

```bash
docker run ... \
  -v ./certs:/certs:ro \
  -e TLS_CERT_FILE=/certs/server.crt \
  -e TLS_KEY_FILE=/certs/server.key \
  -p 6514:6514/tcp \
  ...
```

### Restricting who can send logs

Set `ALLOWED_SOURCES` to a comma-separated list of CIDRs to reject syslog
from anything else, e.g. `ALLOWED_SOURCES=192.168.1.0/24`.

## Storage management

Log volume is unbounded by default. Set `MAX_LOG_DAYS` and/or
`MAX_TOTAL_SIZE_GB` (see above) to have the container prune old files on its
own — no extra setup required. If you'd rather manage retention from the
host instead, see the `examples/` folder for a standalone `logrotate` config
and a total-size-cap script you can run via cron against the mounted volume.

## Releases

Every push to `main` automatically tags the next patch version (`vX.Y.Z`),
creates a GitHub Release with auto-generated notes, and builds/publishes a
matching multi-arch image to `ghcr.io/installation-04/syslogng-webui` (plus
`:latest`). To land a change without cutting a release (e.g. docs-only),
include `[skip release]` in the commit message.

## Building locally

```bash
docker build -t syslogng-webui .
```

## License

MIT — see [LICENSE](LICENSE).
