#!/usr/bin/env python3
"""
Minimal web UI for browsing syslog-ng output, split by sending host.
No external dependencies - pure Python standard library.
"""
import base64
import gzip
import hmac
import json
import os
import re
import shutil
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

LOG_ROOT = os.environ.get("LOG_ROOT", "/var/log/syslogng")
PORT = int(os.environ.get("PORT", "8082"))
MAX_LINES = 2000
SEARCH_LIMIT_DEFAULT = 500
SEARCH_LIMIT_MAX = 2000

AUTH_TOKEN = os.environ.get("AUTH_TOKEN", "")
AUTH_USER = os.environ.get("AUTH_USER", "admin")

PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>syslogng-webui</title>
<style>
  :root {
    --bg:#f5f6f8; --bg-alt:#eceef1; --bg-hover:#e4e7eb; --border:#d7dbe0; --text:#1c2127; --text-dim:#6b7480;
    --accent:#1c7ed6; --accent-dim:#2f6690; --ok:#2f9e44; --warn:#e8590c; --mark-bg:#fff3bf; --mark-fg:#7d5a00;
    color-scheme: light;
  }
  :root[data-theme="dark"] {
    --bg:#111418; --bg-alt:#181c22; --bg-hover:#1a1f26; --border:#2a2f37; --text:#d7dde3; --text-dim:#8a93a0;
    --accent:#8ecae6; --accent-dim:#5fa8d3; --ok:#5fb87a; --warn:#ff8787; --mark-bg:#3a3210; --mark-fg:#ffd166;
    color-scheme: dark;
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      --bg:#111418; --bg-alt:#181c22; --bg-hover:#1a1f26; --border:#2a2f37; --text:#d7dde3; --text-dim:#8a93a0;
      --accent:#8ecae6; --accent-dim:#5fa8d3; --ok:#5fb87a; --warn:#ff8787; --mark-bg:#3a3210; --mark-fg:#ffd166;
      color-scheme: dark;
    }
  }
  body { margin:0; font-family: ui-monospace, Menlo, Consolas, monospace; background:var(--bg); color:var(--text); }
  header { padding:10px 16px; background:var(--bg-alt); border-bottom:1px solid var(--border); display:flex; gap:10px; align-items:center; flex-wrap:wrap; }
  header h1 { font-size:14px; font-weight:600; margin:0; color:var(--accent); letter-spacing:.02em; }
  select, input, button { background:var(--bg); color:var(--text); border:1px solid var(--border); border-radius:6px; padding:6px 10px; font-family:inherit; font-size:13px; }
  button { cursor:pointer; }
  button:hover { background:var(--bg-hover); }
  a.btn { text-decoration:none; display:inline-block; }
  #search, #exclude, #searchQuery { flex:1; min-width:140px; }
  #linecount { color:var(--text-dim); font-size:12px; margin-left:auto; }
  main { padding:0; }
  #log, #searchResults { white-space:pre-wrap; word-break:break-all; padding:14px 16px; font-size:12.5px; line-height:1.5; }
  .l:hover { background:var(--bg-hover); }
  .l .meta { color:var(--accent-dim); }
  .l .dupcount { color:var(--text-dim); font-size:11px; }
  mark { background:var(--mark-bg); color:var(--mark-fg); border-radius:2px; }
  label { font-size:12px; color:var(--text-dim); display:flex; align-items:center; gap:5px; }
  #status { font-size:12px; color:var(--ok); }
  .row2 { width:100%; display:flex; gap:10px; align-items:center; flex-wrap:wrap; margin-top:8px; }
  nav.tabs { padding:0 16px; background:var(--bg-alt); border-bottom:1px solid var(--border); display:flex; gap:4px; }
  nav.tabs button { background:transparent; border:none; border-radius:0; padding:10px 14px; color:var(--text-dim); border-bottom:2px solid transparent; }
  nav.tabs button.active { color:var(--accent); border-bottom-color:var(--accent); }
  section.panel { display:none; }
  section.panel.active { display:block; }
  table { width:100%; border-collapse:collapse; font-size:12.5px; }
  th, td { text-align:left; padding:8px 16px; border-bottom:1px solid var(--border); }
  th { color:var(--text-dim); font-weight:600; }
  #stats { padding:0; }
  .badge { display:inline-block; padding:1px 7px; border-radius:10px; font-size:11px; font-weight:600; }
  .badge-dead { background:var(--warn); color:#1c1200; }
  tr.dead td { color:var(--warn); }
  #themeToggle { font-size:14px; padding:6px 9px; }
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
  <label><input type="checkbox" id="live"> live tail</label>
  <button id="refresh">Refresh</button>
  <a id="download" class="btn" href="#"><button type="button">Download</button></a>
  <button id="copyLink" title="copy a permalink to this view">Copy link</button>
  <button id="themeToggle" title="toggle light/dark theme">🌓</button>
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
    <select id="presetSelect"><option value="">presets...</option></select>
    <button id="savePreset" title="save current filters as a preset">Save preset</button>
    <button id="deletePreset" title="delete selected preset">Delete preset</button>
    <span id="linecount"></span>
  </div>
</header>
<nav class="tabs">
  <button data-tab="logs" class="active">Logs</button>
  <button data-tab="search">Search</button>
  <button data-tab="stats">Stats</button>
</nav>
<main>
  <section id="tab-logs" class="panel active"><div id="log">Loading...</div></section>
  <section id="tab-search" class="panel">
    <div class="row2" style="padding:10px 16px 0;">
      <select id="searchHost"><option value="*">All hosts</option></select>
      <input id="searchQuery" placeholder="search all logs...">
      <label><input type="checkbox" id="searchRegex"> regex</label>
      <label><input type="checkbox" id="searchCase"> case-sensitive</label>
      <button id="doSearch">Search</button>
    </div>
    <div id="searchResults"></div>
  </section>
  <section id="tab-stats" class="panel">
    <div class="row2" style="padding:10px 16px 0;">
      <label>consider a host dead after
        <input id="deadMinutes" type="number" min="1" value="15" style="width:60px;">
        minutes of silence
      </label>
    </div>
    <div id="stats">Loading...</div>
  </section>
</main>
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
const liveEl = document.getElementById('live');
const downloadEl = document.getElementById('download');
const presetSelect = document.getElementById('presetSelect');
const deadMinutesEl = document.getElementById('deadMinutes');
let timer = null;
let evtSource = null;
let lastLines = [];
let hostLastSeen = {}; // host -> unix seconds, populated from /api/stats

const SETTINGS_KEY = 'syslogng-webui-settings';
const PRESETS_KEY = 'syslogng-webui-presets';

// ---- theme ----
function currentEffectiveTheme() {
  const explicit = document.documentElement.getAttribute('data-theme');
  if (explicit) return explicit;
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}
function applyTheme(theme) {
  if (theme === 'light' || theme === 'dark') {
    document.documentElement.setAttribute('data-theme', theme);
  } else {
    document.documentElement.removeAttribute('data-theme');
  }
}
document.getElementById('themeToggle').addEventListener('click', () => {
  const next = currentEffectiveTheme() === 'dark' ? 'light' : 'dark';
  applyTheme(next);
  saveSettings();
});

// ---- settings (filters, sort, theme) ----
function loadSettings() {
  try {
    const s = JSON.parse(localStorage.getItem(SETTINGS_KEY) || '{}');
    if (s.fetchLines) fetchLinesSel.value = s.fetchLines;
    if (s.search) search.value = s.search;
    if (s.exclude) exclude.value = s.exclude;
    if (s.regex) regexEl.checked = true;
    if (s.casesens) caseEl.checked = true;
    if (s.sortOrder) sortEl.value = s.sortOrder;
    if (s.auto === false) autoEl.checked = false;
    if (s.theme) applyTheme(s.theme);
    if (s.deadMinutes) deadMinutesEl.value = s.deadMinutes;
  } catch (e) { /* ignore corrupt/missing settings */ }
}
function saveSettings() {
  try {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify({
      fetchLines: fetchLinesSel.value, search: search.value, exclude: exclude.value,
      regex: regexEl.checked, casesens: caseEl.checked, sortOrder: sortEl.value, auto: autoEl.checked,
      theme: document.documentElement.getAttribute('data-theme') || '', deadMinutes: deadMinutesEl.value
    }));
  } catch (e) { /* storage unavailable (private mode, quota) - non-fatal */ }
}

// ---- saved filter presets ----
function loadPresets() {
  try { return JSON.parse(localStorage.getItem(PRESETS_KEY) || '{}'); }
  catch (e) { return {}; }
}
function savePresets(presets) {
  try { localStorage.setItem(PRESETS_KEY, JSON.stringify(presets)); }
  catch (e) { /* storage unavailable - non-fatal */ }
}
function refreshPresetOptions(selected) {
  const presets = loadPresets();
  const names = Object.keys(presets).sort();
  presetSelect.innerHTML = '<option value="">presets...</option>' +
    names.map(n => `<option value="${escapeHtml(n)}">${escapeHtml(n)}</option>`).join('');
  if (selected && presets[selected]) presetSelect.value = selected;
}
presetSelect.addEventListener('change', () => {
  const presets = loadPresets();
  const p = presets[presetSelect.value];
  if (!p) return;
  search.value = p.search || '';
  exclude.value = p.exclude || '';
  regexEl.checked = !!p.regex;
  caseEl.checked = !!p.casesens;
  sortEl.value = p.sortOrder || 'asc';
  render();
  saveSettings();
  updatePermalink();
});
document.getElementById('savePreset').addEventListener('click', () => {
  const name = window.prompt('Preset name:');
  if (!name) return;
  const presets = loadPresets();
  presets[name] = {
    search: search.value, exclude: exclude.value,
    regex: regexEl.checked, casesens: caseEl.checked, sortOrder: sortEl.value
  };
  savePresets(presets);
  refreshPresetOptions(name);
});
document.getElementById('deletePreset').addEventListener('click', () => {
  const name = presetSelect.value;
  if (!name) return;
  const presets = loadPresets();
  delete presets[name];
  savePresets(presets);
  refreshPresetOptions();
});

// ---- permalink ----
function updatePermalink() {
  const params = new URLSearchParams();
  if (hostSel.value) params.set('host', hostSel.value);
  if (fileSel.value) params.set('file', fileSel.value);
  if (search.value) params.set('q', search.value);
  if (exclude.value) params.set('exclude', exclude.value);
  if (regexEl.checked) params.set('regex', '1');
  if (caseEl.checked) params.set('case', '1');
  if (sortEl.value !== 'asc') params.set('sort', sortEl.value);
  if (fetchLinesSel.value !== '2000') params.set('lines', fetchLinesSel.value);
  const activeTab = document.querySelector('nav.tabs button.active');
  if (activeTab && activeTab.dataset.tab !== 'logs') params.set('tab', activeTab.dataset.tab);
  const qs = params.toString();
  const url = qs ? `${location.pathname}?${qs}` : location.pathname;
  history.replaceState(null, '', url);
}
document.getElementById('copyLink').addEventListener('click', async () => {
  updatePermalink();
  try {
    await navigator.clipboard.writeText(location.href);
    statusEl.textContent = 'link copied';
  } catch (e) {
    window.prompt('Copy this link:', location.href);
  }
});
function paramsFromUrl() {
  return new URLSearchParams(location.search);
}

async function loadHosts() {
  const previousHost = hostSel.value;
  const r = await fetch('/api/hosts');
  const hosts = await r.json();
  await refreshHostLastSeen();
  const deadAfterSec = (parseFloat(deadMinutesEl.value) || 15) * 60;
  const nowSec = Date.now() / 1000;
  const decorate = h => {
    const last = hostLastSeen[h];
    const dead = last && (nowSec - last) > deadAfterSec;
    return `<option value="${h}">${dead ? '⚠ ' : ''}${h}</option>`;
  };
  hostSel.innerHTML = hosts.map(decorate).join('');
  const searchHostSel = document.getElementById('searchHost');
  searchHostSel.innerHTML = '<option value="*">All hosts</option>' + hosts.map(decorate).join('');
  const urlHost = paramsFromUrl().get('host');
  if (previousHost && hosts.includes(previousHost)) hostSel.value = previousHost;
  else if (urlHost && hosts.includes(urlHost)) hostSel.value = urlHost;
  if (hosts.length) await loadFiles();
}

async function loadFiles() {
  const host = hostSel.value;
  const previousFile = fileSel.value;
  const r = await fetch('/api/files?host=' + encodeURIComponent(host));
  const files = await r.json();
  fileSel.innerHTML = files.map(f => `<option value="${f}">${f}</option>`).join('');
  const urlFile = paramsFromUrl().get('file');
  if (previousFile && files.includes(previousFile)) fileSel.value = previousFile;
  else if (urlFile && files.includes(urlFile)) fileSel.value = urlFile;
  await loadContent();
}

function updateDownloadLink() {
  const host = hostSel.value, file = fileSel.value;
  downloadEl.href = (host && file)
    ? `/api/download?host=${encodeURIComponent(host)}&file=${encodeURIComponent(file)}`
    : '#';
}

async function loadContent() {
  const host = hostSel.value, file = fileSel.value;
  updateDownloadLink();
  updatePermalink();
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

async function refreshHostLastSeen() {
  try {
    const r = await fetch('/api/stats');
    const rows = await r.json();
    hostLastSeen = {};
    rows.forEach(row => { hostLastSeen[row.host] = row.last_seen; });
  } catch (e) { /* stats unavailable - dead-host badges just won't show */ }
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
  updatePermalink();
}

hostSel.addEventListener('change', () => { loadFiles(); setupLive(); });
fileSel.addEventListener('change', () => { loadContent(); setupLive(); });
fetchLinesSel.addEventListener('change', () => { loadContent(); saveSettings(); });
search.addEventListener('input', () => { render(); saveSettings(); });
exclude.addEventListener('input', () => { render(); saveSettings(); });
regexEl.addEventListener('change', () => { render(); saveSettings(); });
caseEl.addEventListener('change', () => { render(); saveSettings(); });
sortEl.addEventListener('change', () => { render(); saveSettings(); });
document.getElementById('refresh').addEventListener('click', loadContent);
autoEl.addEventListener('change', () => { setupAuto(); saveSettings(); });
liveEl.addEventListener('change', setupLive);
deadMinutesEl.addEventListener('change', () => { saveSettings(); loadHosts(); if (document.getElementById('tab-stats').classList.contains('active')) loadStats(); });

function setupAuto() {
  if (timer) clearInterval(timer);
  if (autoEl.checked && !liveEl.checked) timer = setInterval(loadContent, 5000);
}

function setupLive() {
  if (evtSource) { evtSource.close(); evtSource = null; }
  if (timer) clearInterval(timer);
  if (!liveEl.checked) { setupAuto(); return; }
  const host = hostSel.value, file = fileSel.value;
  if (!host || !file) return;
  evtSource = new EventSource(`/api/stream?host=${encodeURIComponent(host)}&file=${encodeURIComponent(file)}`);
  evtSource.onmessage = (ev) => {
    lastLines.push(ev.data);
    const cap = parseInt(fetchLinesSel.value, 10) || MAX_LINES;
    if (lastLines.length > cap) lastLines = lastLines.slice(-cap);
    render();
    statusEl.textContent = 'live @ ' + new Date().toLocaleTimeString();
  };
  evtSource.onerror = () => { statusEl.textContent = 'live tail disconnected, retrying...'; };
}

// tabs
function activateTab(name) {
  document.querySelectorAll('nav.tabs button').forEach(b => b.classList.toggle('active', b.dataset.tab === name));
  document.querySelectorAll('section.panel').forEach(p => p.classList.toggle('active', p.id === 'tab-' + name));
  if (name === 'stats') loadStats();
  updatePermalink();
}
document.querySelectorAll('nav.tabs button').forEach(btn => {
  btn.addEventListener('click', () => activateTab(btn.dataset.tab));
});

async function loadStats() {
  const statsEl = document.getElementById('stats');
  statsEl.textContent = 'Loading...';
  try {
    const r = await fetch('/api/stats');
    const rows = await r.json();
    hostLastSeen = {};
    rows.forEach(row => { hostLastSeen[row.host] = row.last_seen; });
    if (!rows.length) { statsEl.innerHTML = '<div style="padding:14px 16px;color:var(--text-dim)">No hosts yet</div>'; return; }
    const fmtSize = b => b > 1024*1024*1024 ? (b/1024/1024/1024).toFixed(2)+' GB'
      : b > 1024*1024 ? (b/1024/1024).toFixed(1)+' MB' : (b/1024).toFixed(1)+' KB';
    const fmtTime = t => t ? new Date(t*1000).toLocaleString() : '-';
    const deadAfterSec = (parseFloat(deadMinutesEl.value) || 15) * 60;
    const nowSec = Date.now() / 1000;
    statsEl.innerHTML = '<table><thead><tr><th>Host</th><th>Status</th><th>Files</th><th>Total size</th><th>Last seen</th></tr></thead><tbody>' +
      rows.map(r => {
        const dead = r.last_seen && (nowSec - r.last_seen) > deadAfterSec;
        return `<tr class="${dead ? 'dead' : ''}"><td>${escapeHtml(r.host)}</td>` +
          `<td>${dead ? '<span class="badge badge-dead">dead</span>' : '<span class="badge" style="background:var(--ok);color:#04240f">alive</span>'}</td>` +
          `<td>${r.files}</td><td>${fmtSize(r.size_bytes)}</td><td>${fmtTime(r.last_seen)}</td></tr>`;
      }).join('') +
      '</tbody></table>';
  } catch (e) {
    statsEl.textContent = 'error loading stats';
  }
}

document.getElementById('doSearch').addEventListener('click', doSearch);
document.getElementById('searchQuery').addEventListener('keydown', (e) => { if (e.key === 'Enter') doSearch(); });

async function doSearch() {
  const resultsEl = document.getElementById('searchResults');
  const host = document.getElementById('searchHost').value;
  const q = document.getElementById('searchQuery').value.trim();
  const isRegex = document.getElementById('searchRegex').checked;
  const caseSensitive = document.getElementById('searchCase').checked;
  resultsEl.textContent = 'Searching...';
  try {
    const params = new URLSearchParams({ host, q, regex: isRegex ? '1' : '0', case: caseSensitive ? '1' : '0' });
    const r = await fetch('/api/search?' + params.toString());
    const data = await r.json();
    if (data.error) { resultsEl.textContent = 'Error: ' + data.error; return; }
    if (!data.results.length) { resultsEl.innerHTML = '<span style="color:var(--text-dim)">(no matches)</span>'; return; }
    resultsEl.innerHTML = data.results.map(m =>
      '<div class="l"><span class="meta">[' + escapeHtml(m.host) + '/' + escapeHtml(m.file) + ']</span> ' +
      highlight(m.line, q, isRegex, caseSensitive) + '</div>'
    ).join('') + (data.truncated ? '<div style="color:var(--text-dim);margin-top:8px">(results truncated, refine your search)</div>' : '');
  } catch (e) {
    resultsEl.textContent = 'error searching';
  }
}

function applyUrlOverrides() {
  const p = paramsFromUrl();
  if (p.has('q')) search.value = p.get('q');
  if (p.has('exclude')) exclude.value = p.get('exclude');
  if (p.get('regex') === '1') regexEl.checked = true;
  if (p.get('case') === '1') caseEl.checked = true;
  if (p.has('sort')) sortEl.value = p.get('sort');
  if (p.has('lines')) fetchLinesSel.value = p.get('lines');
  return p.get('tab');
}

const MAX_LINES = 5000;
loadSettings();
refreshPresetOptions();
const urlTab = applyUrlOverrides();
loadHosts().then(() => {
  updateDownloadLink();
  setupAuto();
  if (urlTab && urlTab !== 'logs') activateTab(urlTab);
  else updatePermalink();
});
</script>
</body>
</html>
"""


def safe_join(base, *parts):
    base = os.path.normpath(base)
    path = os.path.normpath(os.path.join(base, *parts))
    if path != base and not path.startswith(base + os.sep):
        raise ValueError("path traversal blocked")
    return path


def read_tail(path, max_lines=MAX_LINES):
    if path.endswith(".gz"):
        with gzip.open(path, "rt", errors="replace") as f:
            lines = f.readlines()
        return [l.rstrip("\n") for l in lines[-max_lines:]]

    # Efficient tail for plain files: read backwards in chunks instead of
    # loading the whole (potentially very large, unrotated) file into memory.
    chunk_size = 65536
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        remaining = f.tell()
        blocks = []
        newline_count = 0
        while remaining > 0 and newline_count <= max_lines:
            read_size = min(chunk_size, remaining)
            remaining -= read_size
            f.seek(remaining)
            chunk = f.read(read_size)
            newline_count += chunk.count(b"\n")
            blocks.append(chunk)
        data = b"".join(reversed(blocks))
    text = data.decode("utf-8", errors="replace")
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines[-max_lines:]


def iter_hosts():
    try:
        return sorted(
            d for d in os.listdir(LOG_ROOT)
            if os.path.isdir(os.path.join(LOG_ROOT, d))
        )
    except FileNotFoundError:
        return []


def iter_files(host):
    try:
        hostdir = safe_join(LOG_ROOT, host)
        return sorted(
            f for f in os.listdir(hostdir)
            if f.endswith(".log") or f.endswith(".gz")
        )[::-1]
    except (FileNotFoundError, ValueError, NotADirectoryError):
        return []


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

    def _check_auth(self):
        if not AUTH_TOKEN:
            return True
        header = self.headers.get("Authorization", "")
        if not header.startswith("Basic "):
            return False
        try:
            decoded = base64.b64decode(header[6:]).decode("utf-8", errors="replace")
            user, _, pwd = decoded.partition(":")
        except Exception:
            return False
        return hmac.compare_digest(user, AUTH_USER) and hmac.compare_digest(pwd, AUTH_TOKEN)

    def _require_auth(self):
        body = b"Authentication required"
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="syslogng-webui"')
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self._check_auth():
            self._require_auth()
            return

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
            self._json(iter_hosts())
            return

        if parsed.path == "/api/files":
            host = qs.get("host", [""])[0]
            self._json(iter_files(host))
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

        if parsed.path == "/api/download":
            self._handle_download(qs)
            return

        if parsed.path == "/api/stream":
            self._handle_stream(qs)
            return

        if parsed.path == "/api/search":
            self._handle_search(qs)
            return

        if parsed.path == "/api/stats":
            self._handle_stats()
            return

        self._json({"error": "not found"}, code=404)

    def _handle_download(self, qs):
        host = qs.get("host", [""])[0]
        file = qs.get("file", [""])[0]
        try:
            path = safe_join(LOG_ROOT, host, file)
            if not os.path.isfile(path):
                raise FileNotFoundError
        except (FileNotFoundError, ValueError):
            self._json({"error": "not found"}, code=404)
            return
        size = os.path.getsize(path)
        safe_name = re.sub(r'[\r\n"/\\]', "_", f"{host}_{file}")
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Disposition", f'attachment; filename="{safe_name}"')
        self.send_header("Content-Length", str(size))
        self.end_headers()
        with open(path, "rb") as f:
            shutil.copyfileobj(f, self.wfile)

    def _handle_stream(self, qs):
        host = qs.get("host", [""])[0]
        file = qs.get("file", [""])[0]
        try:
            path = safe_join(LOG_ROOT, host, file)
        except ValueError:
            self.send_response(404)
            self.end_headers()
            return
        if not os.path.isfile(path) or path.endswith(".gz"):
            self.send_response(404)
            self.end_headers()
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        try:
            with open(path, "rb") as f:
                f.seek(0, os.SEEK_END)
                pos = f.tell()
                last_ping = time.monotonic()
                deadline = time.monotonic() + 3600  # cap connection lifetime; client auto-reconnects
                while time.monotonic() < deadline:
                    size = os.path.getsize(path)
                    if size < pos:
                        pos = 0  # file truncated or rotated
                    if size > pos:
                        f.seek(pos)
                        chunk = f.read(size - pos)
                        pos = f.tell()
                        text = chunk.decode("utf-8", errors="replace")
                        for line in text.splitlines():
                            self.wfile.write(f"data: {line}\n\n".encode())
                        self.wfile.flush()
                        last_ping = time.monotonic()
                    elif time.monotonic() - last_ping > 15:
                        self.wfile.write(b": ping\n\n")
                        self.wfile.flush()
                        last_ping = time.monotonic()
                    time.sleep(1)
        except (BrokenPipeError, ConnectionResetError, OSError):
            return

    def _handle_search(self, qs):
        q = qs.get("q", [""])[0]
        host_filter = qs.get("host", ["*"])[0]
        is_regex = qs.get("regex", ["0"])[0] == "1"
        case_sensitive = qs.get("case", ["0"])[0] == "1"
        try:
            limit = min(max(int(qs.get("limit", [str(SEARCH_LIMIT_DEFAULT)])[0]), 1), SEARCH_LIMIT_MAX)
        except ValueError:
            limit = SEARCH_LIMIT_DEFAULT

        pattern = None
        needle = None
        if q:
            if is_regex:
                try:
                    pattern = re.compile(q, 0 if case_sensitive else re.IGNORECASE)
                except re.error as e:
                    self._json({"error": f"invalid regex: {e}"}, code=400)
                    return
            else:
                needle = q if case_sensitive else q.lower()

        hosts = [host_filter] if host_filter != "*" else iter_hosts()
        results = []
        truncated = False
        for host in hosts:
            if len(results) >= limit:
                truncated = True
                break
            for fname in iter_files(host):
                if len(results) >= limit:
                    truncated = True
                    break
                try:
                    path = safe_join(LOG_ROOT, host, fname)
                except ValueError:
                    continue
                opener = gzip.open if fname.endswith(".gz") else open
                try:
                    with opener(path, "rt", errors="replace") as f:
                        for line in f:
                            line = line.rstrip("\n")
                            if not q:
                                ok = True
                            elif is_regex:
                                ok = bool(pattern.search(line))
                            else:
                                ok = (needle in line) if case_sensitive else (needle in line.lower())
                            if ok:
                                results.append({"host": host, "file": fname, "line": line})
                                if len(results) >= limit:
                                    truncated = True
                                    break
                except OSError:
                    continue

        self._json({"results": results, "truncated": truncated})

    def _handle_stats(self):
        stats = []
        for host in iter_hosts():
            hostdir = os.path.join(LOG_ROOT, host)
            total_size = 0
            file_count = 0
            last_modified = 0
            try:
                entries = os.listdir(hostdir)
            except OSError:
                entries = []
            for fname in entries:
                if not (fname.endswith(".log") or fname.endswith(".gz")):
                    continue
                try:
                    st = os.stat(os.path.join(hostdir, fname))
                except OSError:
                    continue
                total_size += st.st_size
                file_count += 1
                last_modified = max(last_modified, st.st_mtime)
            stats.append({
                "host": host,
                "files": file_count,
                "size_bytes": total_size,
                "last_seen": last_modified,
            })
        stats.sort(key=lambda s: s["last_seen"], reverse=True)
        self._json(stats)


if __name__ == "__main__":
    print(f"Serving {LOG_ROOT} on port {PORT}")
    if AUTH_TOKEN:
        print("Authentication enabled (AUTH_TOKEN set)")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
