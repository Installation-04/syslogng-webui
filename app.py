#!/usr/bin/env python3
"""
Minimal web UI for browsing syslog-ng output, split by sending host.
No external dependencies - pure Python standard library.
"""
import gzip
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

LOG_ROOT = os.environ.get("LOG_ROOT", "/var/log/syslogng")
PORT = int(os.environ.get("PORT", "8082"))
MAX_LINES = 2000

PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>syslogng-webui</title>
<style>
  :root { color-scheme: dark; }
  body { margin:0; font-family: ui-monospace, Menlo, Consolas, monospace; background:#111418; color:#d7dde3; }
  header { padding:10px 16px; background:#181c22; border-bottom:1px solid #2a2f37; display:flex; gap:10px; align-items:center; flex-wrap:wrap; }
  header h1 { font-size:14px; font-weight:600; margin:0; color:#8ecae6; letter-spacing:.02em; }
  select, input, button { background:#1e232a; color:#d7dde3; border:1px solid #2a2f37; border-radius:6px; padding:6px 10px; font-family:inherit; font-size:13px; }
  button { cursor:pointer; }
  button:hover { background:#262c34; }
  #search, #exclude { flex:1; min-width:140px; }
  #linecount { color:#8a93a0; font-size:12px; margin-left:auto; }
  main { padding:0; }
  #log { white-space:pre-wrap; word-break:break-all; padding:14px 16px; font-size:12.5px; line-height:1.5; }
  .l:hover { background:#1a1f26; }
  mark { background:#3a3210; color:#ffd166; border-radius:2px; }
  label { font-size:12px; color:#8a93a0; display:flex; align-items:center; gap:5px; }
  #status { font-size:12px; color:#5fb87a; }
  .row2 { width:100%; display:flex; gap:10px; align-items:center; flex-wrap:wrap; margin-top:8px; }
</style>
</head>
<body>
<header>
  <h1>syslogng-webui</h1>
  <select id="host"></select>
  <select id="file"></select>
  <select id="fetchLines" title="how many lines to fetch from the file">
    <option value="500">last 500</option>
    <option value="1000">last 1000</option>
    <option value="2000" selected>last 2000</option>
    <option value="5000">last 5000</option>
  </select>
  <label><input type="checkbox" id="auto" checked> auto-refresh</label>
  <button id="refresh">Refresh</button>
  <span id="status"></span>
  <div class="row2">
    <input id="search" placeholder="include filter...">
    <input id="exclude" placeholder="exclude filter...">
    <label><input type="checkbox" id="regex"> regex</label>
    <label><input type="checkbox" id="casesens"> case-sensitive</label>
    <select id="sortOrder">
      <option value="asc" selected>oldest first</option>
      <option value="desc">newest first</option>
    </select>
    <span id="linecount"></span>
  </div>
</header>
<main><div id="log">Loading...</div></main>
<script>
const hostSel = document.getElementById('host');
const fileSel = document.getElementById('file');
const fetchLinesSel = document.getElementById('fetchLines');
const search = document.getElementById('search');
const exclude = document.getElementById('exclude');
const regexEl = document.getElementById('regex');
const caseEl = document.getElementById('casesens');
const sortEl = document.getElementById('sortOrder');
const logEl = document.getElementById('log');
const linecountEl = document.getElementById('linecount');
const statusEl = document.getElementById('status');
const autoEl = document.getElementById('auto');
let timer = null;
let lastLines = [];

async function loadHosts() {
  const r = await fetch('/api/hosts');
  const hosts = await r.json();
  hostSel.innerHTML = hosts.map(h => `<option value="${h}">${h}</option>`).join('');
  if (hosts.length) await loadFiles();
}

async function loadFiles() {
  const host = hostSel.value;
  const r = await fetch('/api/files?host=' + encodeURIComponent(host));
  const files = await r.json();
  fileSel.innerHTML = files.map(f => `<option value="${f}">${f}</option>`).join('');
  await loadContent();
}

async function loadContent() {
  const host = hostSel.value, file = fileSel.value;
  if (!host || !file) return;
  statusEl.textContent = 'loading...';
  try {
    const n = fetchLinesSel.value;
    const r = await fetch(`/api/content?host=${encodeURIComponent(host)}&file=${encodeURIComponent(file)}&lines=${n}`);
    const data = await r.json();
    lastLines = data.lines;
    render();
    statusEl.textContent = 'updated ' + new Date().toLocaleTimeString();
  } catch (e) {
    statusEl.textContent = 'error loading log';
  }
}

function escapeHtml(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;');
}

function matches(line, pattern, isRegex, caseSensitive) {
  if (!pattern) return true;
  try {
    if (isRegex) {
      const re = new RegExp(pattern, caseSensitive ? '' : 'i');
      return re.test(line);
    }
    return caseSensitive ? line.includes(pattern) : line.toLowerCase().includes(pattern.toLowerCase());
  } catch (e) {
    return true; // bad regex - don't filter anything out
  }
}

function highlight(line, pattern, isRegex, caseSensitive) {
  if (!pattern) return escapeHtml(line);
  try {
    const re = isRegex
      ? new RegExp('(' + pattern + ')', caseSensitive ? 'g' : 'gi')
      : new RegExp('(' + pattern.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')', caseSensitive ? 'g' : 'gi');
    return escapeHtml(line).replace(re, '<mark>$1</mark>');
  } catch (e) {
    return escapeHtml(line);
  }
}

function render() {
  const inc = search.value.trim();
  const exc = exclude.value.trim();
  const isRegex = regexEl.checked;
  const caseSensitive = caseEl.checked;
  const order = sortEl.value;

  let filtered = lastLines.filter(l =>
    matches(l, inc, isRegex, caseSensitive) && (!exc || !matches(l, exc, isRegex, caseSensitive))
  );

  if (order === 'desc') filtered = filtered.slice().reverse();

  logEl.innerHTML = filtered.map(l =>
    '<div class="l">' + highlight(l, inc, isRegex, caseSensitive) + '</div>'
  ).join('') || '<span style="color:#8a93a0">(no matching lines)</span>';

  linecountEl.textContent = filtered.length + ' / ' + lastLines.length + ' lines shown';
  if (order === 'asc') logEl.scrollTop = logEl.scrollHeight;
  else logEl.scrollTop = 0;
}

hostSel.addEventListener('change', loadFiles);
fileSel.addEventListener('change', loadContent);
fetchLinesSel.addEventListener('change', loadContent);
search.addEventListener('input', render);
exclude.addEventListener('input', render);
regexEl.addEventListener('change', render);
caseEl.addEventListener('change', render);
sortEl.addEventListener('change', render);
document.getElementById('refresh').addEventListener('click', loadContent);
autoEl.addEventListener('change', setupAuto);

function setupAuto() {
  if (timer) clearInterval(timer);
  if (autoEl.checked) timer = setInterval(loadContent, 5000);
}

loadHosts();
setupAuto();
</script>
</body>
</html>
"""


def safe_join(base, *parts):
    path = os.path.normpath(os.path.join(base, *parts))
    if not path.startswith(os.path.normpath(base)):
        raise ValueError("path traversal blocked")
    return path


def read_tail(path, max_lines=MAX_LINES):
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt", errors="replace") as f:
        lines = f.readlines()
    return [l.rstrip("\n") for l in lines[-max_lines:]]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # keep stdout quiet

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)

        if parsed.path == "/":
            body = PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/api/hosts":
            try:
                hosts = sorted(
                    d for d in os.listdir(LOG_ROOT)
                    if os.path.isdir(os.path.join(LOG_ROOT, d))
                )
            except FileNotFoundError:
                hosts = []
            self._json(hosts)
            return

        if parsed.path == "/api/files":
            host = qs.get("host", [""])[0]
            try:
                hostdir = safe_join(LOG_ROOT, host)
                files = sorted(
                    f for f in os.listdir(hostdir)
                    if f.endswith(".log") or f.endswith(".gz")
                )[::-1]
            except (FileNotFoundError, ValueError):
                files = []
            self._json(files)
            return

        if parsed.path == "/api/content":
            host = qs.get("host", [""])[0]
            file = qs.get("file", [""])[0]
            requested = qs.get("lines", [str(MAX_LINES)])[0]
            try:
                n = min(max(int(requested), 1), 10000)
            except ValueError:
                n = MAX_LINES
            try:
                path = safe_join(LOG_ROOT, host, file)
                lines = read_tail(path, max_lines=n)
            except (FileNotFoundError, ValueError, OSError):
                lines = ["(could not read file)"]
            self._json({"lines": lines, "max_lines": n})
            return

        self._json({"error": "not found"}, code=404)


if __name__ == "__main__":
    print(f"Serving {LOG_ROOT} on port {PORT}")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
