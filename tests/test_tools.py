"""Offline tests for the plugin's tool handlers.

Runs the handlers against a stub HTTP server that implements the Switchboard
engine's contract the way app/server.js + app/engine.js do: work-key dedupe on
create, done-gate refusal on completing an unfinished task (409 with the
engine's error string), single-flight wording preserved. No Hermes and no real
engine needed:

    python3 tests/test_tools.py
"""

import importlib.util
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("sb_tools", ROOT / "tools.py")
tools = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tools)

TASKS = {}


class StubEngine(BaseHTTPRequestHandler):
    """Minimal stand-in for the engine's /api/tasks surface."""

    def log_message(self, *a):  # keep the test output clean
        pass

    def _send(self, status, payload):
        raw = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _body(self):
        n = int(self.headers.get("content-length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        if self.path == "/api/tasks":
            self._send(200, {"tasks": list(TASKS.values())})
            return
        if self.path.startswith("/api/tasks/") and self.path.endswith("/log"):
            tid = self.path.split("/")[3]
            if tid in TASKS:
                self._send(200, {"task": TASKS[tid], "steps": [], "messages": TASKS[tid].get("messages", [])})
            else:
                self._send(404, {"error": "task not found"})
            return
        self._send(404, {"error": "not found"})

    def _find(self, ref):
        """Mirror engine.js findTask: by id, else by workKey."""
        return TASKS.get(ref) or next((t for t in TASKS.values() if t.get("workKey") == ref), None)

    def do_POST(self):
        body = self._body()
        if self.path == "/api/tasks":
            key = body.get("workKey")
            for t in TASKS.values():
                if key and t.get("workKey") == key and t["status"] in ("planning", "running", "awaiting", "done"):
                    self._send(200, {"task": t, "deduped": True})
                    return
            task = {
                "id": f"task-{len(TASKS) + 1}",
                "workKey": key,
                "status": "awaiting",
                "text": body.get("text"),
                "retries": 0,
                "createdAt": "2026-10-19T00:00:00.000Z",
                "messages": [],
            }
            TASKS[task["id"]] = task
            self._send(201, {"task": task})
            return
        parts = self.path.split("/")
        task = self._find(parts[3]) if len(parts) == 5 else None
        if task is not None:
            if parts[4] == "messages":
                msg = {"text": body.get("text"), "from": body.get("from")}
                task.setdefault("messages", []).append(msg)
                self._send(200, {"message": msg, "task": task})
                return
            if parts[4] == "complete":
                # the done gate: an awaiting task's steps are unfinished
                self._send(409, {"error": "task is not ready to complete: status is awaiting", "task": task})
                return
        self._send(404, {"error": "task not found"})


def call(result: str) -> dict:
    return json.loads(result)


def main() -> int:
    server = HTTPServer(("127.0.0.1", 0), StubEngine)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    os.environ["SWITCHBOARD_URL"] = f"http://127.0.0.1:{port}"

    failures = []

    def check(name, cond, detail=""):
        print(("PASS " if cond else "FAIL ") + name + ("" if cond else f" — {detail}"))
        if not cond:
            failures.append(name)

    created = call(tools.tasks_create({"text": "proof task", "workKey": "wk-test-1"}))
    check("create ok", created.get("ok") is True and created["task"]["id"] == "task-1", str(created))
    check("create not deduped", created.get("deduped") is False, str(created))

    dupe = call(tools.tasks_create({"text": "proof task", "workKey": "wk-test-1"}))
    check("duplicate create deduped", dupe.get("ok") is True and dupe.get("deduped") is True
          and dupe["task"]["id"] == "task-1", str(dupe))

    listed = call(tools.tasks_list({}))
    check("list shows exactly one task", listed.get("ok") is True and len(listed["tasks"]) == 1
          and listed["tasks"][0]["workKey"] == "wk-test-1", str(listed))

    msg = call(tools.tasks_message({"ref": "wk-test-1", "text": "note from the test"}))
    check("message ok", msg.get("ok") is True and msg["message"]["text"] == "note from the test"
          and msg["message"]["from"] == "hermes", str(msg))

    refused = call(tools.tasks_complete({"ref": "wk-test-1", "summary": "trying early"}))
    check("complete refused verbatim", refused.get("ok") is False and refused.get("status") == 409
          and refused.get("error") == "task is not ready to complete: status is awaiting", str(refused))

    log = call(tools.tasks_log({"ref": "wk-test-1"}))
    check("log by workKey", log.get("ok") is True and log["task"]["id"] == "task-1"
          and len(log.get("messages", [])) == 1, str(log))

    missing = call(tools.tasks_log({"ref": "wk-nope"}))
    check("log missing task", missing.get("ok") is False and missing.get("status") == 404
          and missing.get("error") == "task not found", str(missing))

    os.environ["SWITCHBOARD_URL"] = "http://127.0.0.1:1"  # nothing listens there
    down = call(tools.tasks_list({}))
    check("engine down fails soft", down.get("ok") is False
          and down.get("error", "").startswith("cannot reach Switchboard at http://127.0.0.1:1"), str(down))

    server.shutdown()
    print(f"\n{9 - len(failures)}/9 passed" if not failures else f"\nFAILED: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
