"""
Local web dashboard: type a task, press Run, then watch every step's screenshot and JEV's decision.

    python dashboard.py      # opens http://127.0.0.1:8000
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import jev_agent

PORT = 8000
PAGE = Path(__file__).with_name("dashboard.html")
RUN_ID = re.compile(r"^\d{8}-\d{6}$")
IMAGE = re.compile(r"^\d{2}-[A-Z_]+\.jpg$")
TRASH_DIR = jev_agent.RUNS_DIR / ".trash"
FOLDERS = {"runs": jev_agent.RUNS_DIR, "trash": TRASH_DIR}
active = {"thread": None, "id": None, "stop": None}


def is_running(run_id=None):
    alive = active["thread"] is not None and active["thread"].is_alive()
    return alive and (run_id is None or run_id == active["id"])


def list_runs(folder):
    runs = []
    for d in sorted(folder.glob("*/report.json"), reverse=True):
        try:
            r = json.loads(d.read_text())
        except (OSError, ValueError):
            continue
        runs.append({"id": d.parent.name, "task": r["task"], "status": r["status"],
                     "steps": len(r["steps"]), "started": r["started"], "warning": bool(r.get("warning")),
                     "cost_usd": r.get("cost_usd", r.get("input_tokens", 0) / 1e6 * jev_agent.PRICE_PER_MILLION_INPUT_TOKENS)})
    return runs


def move(ids, source, target):
    """Move runs between runs/ and the trash. Returns how many moved."""
    target.mkdir(parents=True, exist_ok=True)
    moved = 0
    for run_id in ids:
        if RUN_ID.match(str(run_id)) and (source / run_id).is_dir() and not is_running(run_id):
            shutil.rmtree(target / run_id, ignore_errors=True)
            (source / run_id).rename(target / run_id)
            moved += 1
    return moved


def delete_forever(ids):
    """Permanently delete runs. Only works on runs already in the trash."""
    deleted = 0
    for run_id in ids:
        if RUN_ID.match(str(run_id)) and (TRASH_DIR / run_id).is_dir():
            shutil.rmtree(TRASH_DIR / run_id)
            deleted += 1
    return deleted


CHROMIUM_BROWSERS = jev_agent.CHROMIUM_BROWSERS
FIND_TAB_CHROMIUM = """
tell application "{app}"
    repeat with w in windows
        set i to 0
        repeat with t in tabs of w
            set i to i + 1
            if URL of t starts with "{url}" then
                set active tab index of w to i
                set index of w to 1
                activate
                return "found"
            end if
        end repeat
    end repeat
end tell
"""
FIND_TAB_SAFARI = """
tell application "Safari"
    repeat with w in windows
        repeat with t in tabs of w
            if URL of t starts with "{url}" then
                set current tab of w to t
                set index of w to 1
                activate
                return "found"
            end if
        end repeat
    end repeat
end tell
"""


def show_dashboard():
    """Bring the System One Computer Use tab back to the front (macOS), or open it in a new tab."""
    url = f"http://127.0.0.1:{PORT}"
    if sys.platform == "darwin":
        for app in CHROMIUM_BROWSERS + ["Safari"]:
            # Only ask browsers that are running; asking a closed one would launch it.
            if subprocess.run(["pgrep", "-xq", app]).returncode != 0:
                continue
            script = (FIND_TAB_SAFARI if app == "Safari" else FIND_TAB_CHROMIUM).format(app=app, url=url)
            try:
                result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=5)
            except subprocess.TimeoutExpired:
                continue
            if result.stdout.strip() == "found":
                return
    webbrowser.open(url)


def run_then_show_dashboard(*args, **kwargs):
    jev_agent.run_task(*args, **kwargs)
    show_dashboard()


def start(task, dry_run, close_tabs=True):
    if is_running():
        raise ValueError("A task is already running. Stop it first.")
    if not task.strip():
        raise ValueError("Enter a task.")
    run_dir = jev_agent.new_run_dir()
    stop = threading.Event()
    thread = threading.Thread(target=run_then_show_dashboard, args=(task, run_dir, stop),
                              kwargs={"dry_run": dry_run, "close_opened_tabs": close_tabs}, daemon=True)
    active.update(thread=thread, id=run_dir.name, stop=stop)
    thread.start()
    return run_dir.name


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def from_this_dashboard(self, post=False):
        """
        Only the dashboard page itself may use this server. Otherwise any website open in your browser
        could quietly start a task that controls your computer, or delete your runs:
        - Host must be this computer (blocks DNS-rebinding tricks)
        - POSTs must come from the dashboard's own origin and send JSON, which browsers won't let
          another site do without permission we never give (no CORS headers here)
        """
        local = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}
        if self.headers.get("Host") not in local:
            return False
        if post:
            origin = self.headers.get("Origin")
            if origin is not None and origin not in {f"http://{h}" for h in local}:
                return False
            if not (self.headers.get("Content-Type") or "").startswith("application/json"):
                return False
        return True

    def send(self, body, content_type="application/json", status=200):
        if not isinstance(body, bytes):
            body = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self.from_this_dashboard():
            return self.send({"error": "Forbidden"}, status=403)
        parts = self.path.split("?")[0].strip("/").split("/")
        if parts == [""]:
            return self.send(PAGE.read_bytes(), "text/html; charset=utf-8")
        # /api/runs and /api/trash list runs; /api/<folder>/<id> is one report; /<folder>/<id>/<image> an image.
        if len(parts) == 2 and parts[0] == "api" and parts[1] in FOLDERS:
            return self.send({"runs": list_runs(FOLDERS[parts[1]]), "trash_count": len(list_runs(TRASH_DIR)),
                              "active": active["id"] if is_running() else None})
        if len(parts) == 3 and parts[0] == "api" and parts[1] in FOLDERS and RUN_ID.match(parts[2]):
            report = FOLDERS[parts[1]] / parts[2] / "report.json"
            if report.exists():
                return self.send(report.read_bytes())
        if len(parts) == 3 and parts[0] in FOLDERS and RUN_ID.match(parts[1]) and IMAGE.match(parts[2]):
            image = FOLDERS[parts[0]] / parts[1] / parts[2]
            if image.exists():
                return self.send(image.read_bytes(), "image/jpeg")
        self.send({"error": "Not found"}, status=404)

    def do_POST(self):
        if not self.from_this_dashboard(post=True):
            return self.send({"error": "Forbidden"}, status=403)
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        if self.path == "/api/run":
            try:
                return self.send({"id": start(body.get("task", ""), bool(body.get("dry_run")),
                                              body.get("close_tabs", True) is not False)})
            except ValueError as exc:
                return self.send({"error": str(exc)}, status=400)
        if self.path == "/api/stop":
            if active["stop"]:
                active["stop"].set()
            return self.send({"ok": True})
        ids = body.get("ids") or []
        if self.path == "/api/trash":
            return self.send({"moved": move(ids, jev_agent.RUNS_DIR, TRASH_DIR)})
        if self.path == "/api/restore":
            return self.send({"moved": move(ids, TRASH_DIR, jev_agent.RUNS_DIR)})
        if self.path == "/api/delete":
            return self.send({"deleted": delete_forever(ids)})
        self.send({"error": "Not found"}, status=404)


if __name__ == "__main__":
    jev_agent.RUNS_DIR.mkdir(exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)  # this computer only
    print(f"Dashboard: http://127.0.0.1:{PORT}   (Ctrl+C to quit)")
    print(jev_agent.check_tab_access())
    webbrowser.open(f"http://127.0.0.1:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
