#!/usr/bin/env python3
"""
Minimal web UI to run the X Space audio pipeline.
Dependencies: standard library only.

Usage:
  python3 webapp.py --host 127.0.0.1 --port 8000
Then open http://127.0.0.1:8000
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import threading
import uuid
from pathlib import Path
from subprocess import PIPE, STDOUT, Popen, TimeoutExpired
from typing import Dict, Optional
from urllib.parse import parse_qs
from wsgiref.simple_server import make_server

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_OUT = Path.home() / "Downloads" / "spaces"
LOG_DIR = SCRIPT_DIR / "web_logs"
LOG_DIR.mkdir(exist_ok=True)


def now_iso() -> str:
    return dt.datetime.now().replace(microsecond=0).isoformat()


class Job:
    def __init__(
        self,
        space_url: str,
        browser: str,
        out_root: Path,
        quick_mode: bool = False,
        quick_minutes: str = "2",
    ):
        self.id = uuid.uuid4().hex[:10]
        self.space_url = space_url
        self.browser = browser
        self.out_root = out_root
        self.quick_mode = quick_mode
        self.quick_minutes = quick_minutes
        self.status = "queued"
        self.error: Optional[str] = None
        self.started_at: Optional[str] = None
        self.finished_at: Optional[str] = None
        self.target_dir: Optional[str] = None
        self.log_path = LOG_DIR / f"{self.id}.log"
        self.proc: Optional[Popen] = None
        self.cancel_requested = False
        threading.Thread(target=self._run, daemon=True).start()

    def cancel(self):
        self.cancel_requested = True
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=5)
            except TimeoutExpired:
                self.proc.kill()
            self.status = "canceled"
            self.finished_at = now_iso()
            self.error = "canceled by user"

    def _run(self):
        self.status = "running"
        self.started_at = now_iso()
        cmd = [
            "bash",
            str(SCRIPT_DIR / "run_space_pipeline.sh"),
            self.space_url,
            self.browser,
            str(self.out_root),
            "1" if self.quick_mode else "0",
            str(self.quick_minutes),
        ]
        try:
            with self.log_path.open("w", encoding="utf-8") as logf:
                logf.write(f"[{self.started_at}] CMD: {' '.join(cmd)}\n")
                self.proc = Popen(cmd, cwd=str(SCRIPT_DIR), stdout=PIPE, stderr=STDOUT, text=True)
                assert self.proc.stdout is not None
                for line in self.proc.stdout:
                    logf.write(line)
                    logf.flush()
                    if "See:" in line:
                        self.target_dir = line.split("See:", 1)[-1].strip()
                    if self.cancel_requested:
                        break
                self.proc.wait()
                self.finished_at = now_iso()
                if self.cancel_requested:
                    self.status = "canceled"
                    self.error = "canceled by user"
                elif self.proc.returncode == 0:
                    self.status = "done"
                else:
                    self.status = "error"
                    self.error = f"exit {self.proc.returncode}"
        except Exception as exc:  # noqa: BLE001
            self.finished_at = now_iso()
            self.status = "error"
            self.error = f"{exc.__class__.__name__}: {exc}"
            with self.log_path.open("a", encoding="utf-8") as logf:
                logf.write(f"\n[ERROR] {exc}\n")


JOBS: Dict[str, Job] = {}


def html_page(body: str) -> bytes:
    return (
        f"<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>Space Pipeline</title>"
        f"<style>"
        f"body{{font-family:Menlo,monospace;margin:24px;}}"
        f"input,button,select{{font-size:14px;padding:6px;}}"
        f"table{{border-collapse:collapse;width:100%;margin-top:16px;}}"
        f"th,td{{border:1px solid #ccc;padding:6px;text-align:left;}}"
        f"th{{background:#f5f5f5;}}"
        f".status-running{{color:#d9822b;}}"
        f".status-done{{color:#107a3c;}}"
        f".status-error{{color:#c23030;}}"
        f".status-canceled{{color:#8a8a8a;}}"
        f".actions form{{display:inline; margin-right:4px;}}"
        f".preview{{background:#f7f7f7;padding:8px;border:1px solid #ddd;max-height:200px;overflow:auto;}}"
        f"</style>"
        f"<script>"
        f"let timer=null;"
        f"function setAutoRefresh(on){{"
        f"  const box=document.getElementById('auto');"
        f"  if(on===undefined) on=box.checked;"
        f"  if(on){{ timer=setInterval(()=>location.reload(),5000); }} else if(timer){{ clearInterval(timer); }}"
        f"}}"
        f"window.onload=()=>{{ const box=document.getElementById('auto'); if(box) setAutoRefresh(box.checked); }};"
        f"</script>"
        f"</head><body>{body}</body></html>"
    ).encode("utf-8")


def render_index(msg: str = "") -> bytes:
    def load_text(path: Path, limit: int = 1200) -> str:
        if not path.exists():
            return ""
        txt = path.read_text(encoding="utf-8", errors="replace")
        return txt[:limit] + ("..." if len(txt) > limit else "")

    def outputs_cell(job: Job) -> str:
        if not job.target_dir:
            return "-"
        base = Path(job.target_dir)
        links = []
        if base.exists():
            links.append(f"<a href='{base.as_uri()}' target='_blank'>dir</a>")
        for rel, label in [
            ("transcripts/transcript.txt", "txt"),
            ("transcripts/transcript.srt", "srt"),
            ("transcripts/transcript.md", "md"),
            ("summaries/summary.md", "summary"),
        ]:
            p = base / rel
            if p.exists():
                links.append(f"<a href='{p.as_uri()}' target='_blank'>{label}</a>")
        return " | ".join(links) if links else html.escape(job.target_dir)

    def preview_cell(job: Job) -> str:
        if not job.target_dir:
            return "-"
        base = Path(job.target_dir)
        summary = load_text(base / "summaries" / "summary.md", limit=800)
        transcript = load_text(base / "transcripts" / "transcript.txt", limit=800)
        parts = []
        if summary:
            parts.append("<div><strong>Summary</strong><div class='preview'>" + html.escape(summary) + "</div></div>")
        if transcript:
            parts.append("<div style='margin-top:6px;'><strong>Transcript</strong><div class='preview'>" + html.escape(transcript) + "</div></div>")
        return "".join(parts) if parts else "-"

    def outputs_cell(job: Job) -> str:
        if not job.target_dir:
            return "-"
        base = Path(job.target_dir)
        links = []
        if base.exists():
            links.append(f"<a href='{base.as_uri()}' target='_blank'>dir</a>")
        for rel, label in [
            ("transcripts/transcript.txt", "txt"),
            ("transcripts/transcript.srt", "srt"),
            ("transcripts/transcript.md", "md"),
            ("summaries/summary.md", "summary"),
        ]:
            p = base / rel
            if p.exists():
                links.append(f"<a href='{p.as_uri()}' target='_blank'>{label}</a>")
        return " | ".join(links) if links else html.escape(job.target_dir)

    rows = []
    for job in sorted(JOBS.values(), key=lambda j: j.started_at or "", reverse=True):
        status_class = (
            "status-done"
            if job.status == "done"
            else "status-running"
            if job.status == "running"
            else "status-error"
            if job.status == "error"
            else "status-canceled"
            if job.status == "canceled"
            else ""
        )
        log_link = f"<a href='/log?id={job.id}' target='_blank'>log</a>"
        target = html.escape(job.target_dir) if job.target_dir else "-"
        status_text = html.escape(job.status)
        if job.error:
            status_text += f" — {html.escape(job.error)}"
        actions = []
        if job.status in {"queued", "running"}:
            actions.append(
                f"<form method='POST' action='/cancel'>"
                f"<input type='hidden' name='id' value='{job.id}'>"
                f"<button type='submit'>Cancel</button>"
                f"</form>"
            )
        if job.status in {"error", "done", "canceled"}:
            actions.append(
                f"<form method='POST' action='/retry'>"
                f"<input type='hidden' name='id' value='{job.id}'>"
                f"<button type='submit'>Retry</button>"
                f"</form>"
            )
        rows.append(
            "<tr>"
            f"<td>{job.id}</td>"
            f"<td>{html.escape(job.space_url)}</td>"
            f"<td>{html.escape(job.browser)}</td>"
            f"<td>{'quick' if job.quick_mode else 'full'}</td>"
            f"<td>{job.started_at or '-'}</td>"
            f"<td class='{status_class}'>{status_text}</td>"
            f"<td>{target}</td>"
            f"<td>{outputs_cell(job)}</td>"
            f"<td>{preview_cell(job)}</td>"
            f"<td class='actions'>{''.join(actions) or '-'}</td>"
            f"<td>{log_link}</td>"
            "</tr>"
        )

    body = (
        ("<p style='color:#107a3c;'>%s</p>" % html.escape(msg)) if msg else ""
    )
    body += (
        "<h2>Run pipeline</h2>"
        "<form method='POST' action='/run'>"
        "<div><label>Space URL: <input name='space_url' size='80' required></label></div>"
        "<div style='margin-top:8px;'>"
        "<label>Browser (cookies): <input name='browser' value='chrome'></label>"
        "</div>"
        "<div style='margin-top:8px;'>"
        f"<label>Out root: <input name='out_root' value='{html.escape(str(DEFAULT_OUT))}' size='60'></label>"
        "</div>"
        "<div style='margin-top:8px;'>"
        "<label><input type='checkbox' name='quick' value='1'> Quick mode (front minutes only)</label>"
        "<label style='margin-left:12px;'>Minutes: <input name='quick_minutes' value='2' size='4'></label>"
        "</div>"
        "<div style='margin-top:12px;'><button type='submit'>Start</button></div>"
        "</form>"
        "<div style='margin-top:12px;'>"
        "<button onclick='location.reload()'>Refresh</button>"
        "<label style='margin-left:12px;'><input type='checkbox' id='auto' checked onchange='setAutoRefresh(this.checked)'> Auto 5s</label>"
        "</div>"
        "<h2>Jobs</h2>"
        "<table><tr><th>ID</th><th>URL</th><th>Browser</th><th>Mode</th><th>Started</th>"
        "<th>Status</th><th>Target Dir</th><th>Outputs</th><th>Preview</th><th>Actions</th><th>Log</th></tr>"
        + ("\n".join(rows) if rows else "<tr><td colspan='11'>No jobs yet.</td></tr>")
        + "</table>"
    )
    return html_page(body)


def render_log(job_id: str) -> bytes:
    job = JOBS.get(job_id)
    if not job:
        return html_page(f"<p>Job {html.escape(job_id)} not found.</p>")
    if not job.log_path.exists():
        return html_page(f"<p>Log not ready for job {html.escape(job_id)}.</p>")
    content = job.log_path.read_text(encoding="utf-8", errors="replace")
    body = (
        f"<p><a href='/'>Back</a></p>"
        f"<h3>Job {html.escape(job_id)} — {html.escape(job.status)}</h3>"
        "<pre style='background:#f7f7f7;padding:12px;border:1px solid #ddd;white-space:pre-wrap;'>"
        f"{html.escape(content)}</pre>"
    )
    return html_page(body)


def application(environ, start_response):
    method = environ.get("REQUEST_METHOD", "GET")
    path = environ.get("PATH_INFO", "/")
    length = int(environ.get("CONTENT_LENGTH", "0") or 0)
    query = parse_qs(environ.get("QUERY_STRING", ""))

    if method == "GET" and path == "/":
        resp = render_index()
        start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
        return [resp]

    if method == "POST" and path == "/run":
        data = environ["wsgi.input"].read(length).decode()
        form = parse_qs(data)
        space_url = form.get("space_url", [""])[0].strip()
        browser = form.get("browser", ["chrome"])[0].strip() or "chrome"
        out_root = form.get("out_root", [str(DEFAULT_OUT)])[0].strip() or str(DEFAULT_OUT)
        quick = form.get("quick", ["0"])[0].strip() or "0"
        quick_minutes = form.get("quick_minutes", ["2"])[0].strip() or "2"
        if not space_url:
            start_response("400 Bad Request", [("Content-Type", "text/plain")])
            return [b"space_url required"]

        job = Job(
            space_url=space_url,
            browser=browser,
            out_root=Path(out_root),
            quick_mode=quick == "1",
            quick_minutes=quick_minutes,
        )
        JOBS[job.id] = job
        start_response("303 See Other", [("Location", "/?msg=started")])
        return [b""]

    if method == "POST" and path == "/cancel":
        data = environ["wsgi.input"].read(length).decode()
        form = parse_qs(data)
        job_id = form.get("id", [""])[0]
        job = JOBS.get(job_id)
        if not job:
            start_response("404 Not Found", [("Content-Type", "text/plain")])
            return [b"job not found"]
        job.cancel()
        start_response("303 See Other", [("Location", "/?msg=canceled")])
        return [b""]

    if method == "POST" and path == "/retry":
        data = environ["wsgi.input"].read(length).decode()
        form = parse_qs(data)
        job_id = form.get("id", [""])[0]
        old = JOBS.get(job_id)
        if not old:
            start_response("404 Not Found", [("Content-Type", "text/plain")])
            return [b"job not found"]
        new_job = Job(space_url=old.space_url, browser=old.browser, out_root=old.out_root)
        JOBS[new_job.id] = new_job
        start_response("303 See Other", [("Location", "/?msg=retried")])
        return [b""]

    if method == "GET" and path == "/log":
        job_id = (query.get("id") or [""])[0]
        resp = render_log(job_id)
        start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
        return [resp]

    start_response("404 Not Found", [("Content-Type", "text/plain")])
    return [b"not found"]


def main():
    ap = argparse.ArgumentParser(description="Simple web UI for X Space pipeline")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    print(f"[info] serving on http://{args.host}:{args.port}")
    print(f"[info] outputs root default: {DEFAULT_OUT}")
    with make_server(args.host, args.port, application) as httpd:
        httpd.serve_forever()


if __name__ == "__main__":
    main()
