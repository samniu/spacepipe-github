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
from subprocess import Popen, PIPE, STDOUT
from typing import Dict, Optional
from urllib.parse import parse_qs, urlparse
from wsgiref.simple_server import make_server

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_OUT = Path.home() / "Downloads" / "spaces"
LOG_DIR = SCRIPT_DIR / "web_logs"
LOG_DIR.mkdir(exist_ok=True)


def now_iso() -> str:
    return dt.datetime.now().replace(microsecond=0).isoformat()


class Job:
    def __init__(self, space_url: str, browser: str, out_root: Path):
        self.id = uuid.uuid4().hex[:10]
        self.space_url = space_url
        self.browser = browser
        self.out_root = out_root
        self.status = "queued"
        self.error: Optional[str] = None
        self.started_at: Optional[str] = None
        self.finished_at: Optional[str] = None
        self.target_dir: Optional[str] = None
        self.log_path = LOG_DIR / f"{self.id}.log"
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        self.status = "running"
        self.started_at = now_iso()
        cmd = [
            "bash",
            str(SCRIPT_DIR / "run_space_pipeline.sh"),
            self.space_url,
            self.browser,
            str(self.out_root),
        ]
        try:
            with self.log_path.open("w", encoding="utf-8") as logf:
                logf.write(f"[{self.started_at}] CMD: {' '.join(cmd)}\n")
                proc = Popen(cmd, cwd=str(SCRIPT_DIR), stdout=PIPE, stderr=STDOUT, text=True)
                assert proc.stdout is not None
                for line in proc.stdout:
                    logf.write(line)
                    logf.flush()
                    if "See:" in line:
                        self.target_dir = line.split("See:", 1)[-1].strip()
                proc.wait()
                self.finished_at = now_iso()
                if proc.returncode == 0:
                    self.status = "done"
                else:
                    self.status = "error"
                    self.error = f"exit {proc.returncode}"
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
        f"input,button{{font-size:14px;padding:6px;}}"
        f"table{{border-collapse:collapse;width:100%;margin-top:16px;}}"
        f"th,td{{border:1px solid #ccc;padding:6px;text-align:left;}}"
        f"th{{background:#f5f5f5;}}"
        f".status-running{{color:#d9822b;}}"
        f".status-done{{color:#107a3c;}}"
        f".status-error{{color:#c23030;}}"
        f"</style></head><body>{body}</body></html>"
    ).encode("utf-8")


def render_index(msg: str = "") -> bytes:
    rows = []
    for job in sorted(JOBS.values(), key=lambda j: j.started_at or "", reverse=True):
        status_class = (
            "status-done"
            if job.status == "done"
            else "status-running"
            if job.status == "running"
            else "status-error"
            if job.status == "error"
            else ""
        )
        log_link = f"<a href='/log?id={job.id}' target='_blank'>log</a>"
        target = html.escape(job.target_dir) if job.target_dir else "-"
        status_text = html.escape(job.status)
        if job.error:
            status_text += f" — {html.escape(job.error)}"
        rows.append(
            "<tr>"
            f"<td>{job.id}</td>"
            f"<td>{html.escape(job.space_url)}</td>"
            f"<td>{html.escape(job.browser)}</td>"
            f"<td>{job.started_at or '-'}</td>"
            f"<td class='{status_class}'>{status_text}</td>"
            f"<td>{target}</td>"
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
        "<div style='margin-top:12px;'><button type='submit'>Start</button></div>"
        "</form>"
        "<h2>Jobs</h2>"
        "<table><tr><th>ID</th><th>URL</th><th>Browser</th><th>Started</th>"
        "<th>Status</th><th>Target Dir</th><th>Log</th></tr>"
        + ("\n".join(rows) if rows else "<tr><td colspan='7'>No jobs yet.</td></tr>")
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
        if not space_url:
            start_response("400 Bad Request", [("Content-Type", "text/plain")])
            return [b"space_url required"]

        job = Job(space_url=space_url, browser=browser, out_root=Path(out_root))
        JOBS[job.id] = job
        start_response("303 See Other", [("Location", "/?msg=started")])
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
