"""Tool handlers — the code that runs when the LLM calls each tool.

A pure HTTP client of the running Switchboard engine, exactly like the kit's
CLI (bin/switchboard.js) and MCP face (bin/switchboard-mcp.js): same paths,
same payloads, same store. Creating a task goes through the engine's start
path (work keys, single-flight, the approval gate); completing one goes
through the engine's done gate. This plugin is a surface on those rules, not
a way around them, and it never opens a second store handle.

Engine errors are returned verbatim — the engine's own `error` string and HTTP
status, including done-gate refusals and single-flight 409s. Nothing here
retries, rewrites, or softens them.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_URL = "http://127.0.0.1:8787"
TIMEOUT = 600  # matches the CLI/MCP faces: completion runs the done gate

_config_url = ""


def set_config_url(url: str) -> None:
    """Called by register() with the plugin's `url` setting (may be empty)."""
    global _config_url
    _config_url = (url or "").strip()


def base_url() -> str:
    """SWITCHBOARD_URL env wins, then the plugin setting, then the default."""
    env = (os.environ.get("SWITCHBOARD_URL") or "").strip()
    return (env or _config_url or DEFAULT_URL).rstrip("/")


class _EngineError(Exception):
    """The engine answered with an error payload; carry it verbatim."""

    def __init__(self, status: int, payload: dict):
        super().__init__(payload.get("error") or "engine error")
        self.status = status
        self.payload = payload


def _request(method: str, pathname: str, body: dict | None = None) -> tuple[int, dict]:
    """One JSON-over-HTTP call to the engine. Raises _EngineError for engine
    error payloads; returns (status, json) otherwise. Connection and protocol
    failures raise plain exceptions with the CLI/MCP wording."""
    base = base_url()
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        base + pathname,
        data=data,
        headers={"content-type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            status, raw = resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:  # engine answered with an error status
        status, raw = e.code, e.read().decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        reason = getattr(e, "reason", e)
        raise RuntimeError(f"cannot reach Switchboard at {base}: {reason}") from e
    try:
        payload = json.loads(raw)
    except ValueError:
        raise RuntimeError(f"server did not return JSON (status {status})") from None
    if isinstance(payload, dict) and payload.get("error"):
        out = {"ok": False, "error": payload["error"], "status": status}
        if payload.get("task"):
            out["task"] = payload["task"]
        raise _EngineError(status, out)
    return status, payload


def _run(fn) -> str:
    """Handler wrapper: always returns a JSON string, never raises."""
    try:
        return json.dumps(fn())
    except _EngineError as e:
        return json.dumps(e.payload)
    except Exception as e:  # unreachable engine, bad reply, bad args
        return json.dumps({"ok": False, "error": str(e)})


def tasks_create(args: dict, **kwargs) -> str:
    """Submit work to the engine; duplicate workKeys return the existing task
    with deduped: true instead of starting a second run."""

    def go():
        text = (args.get("text") or "").strip()
        if not text:
            return {"ok": False, "error": "No task text provided"}
        body: dict = {"text": text}
        if args.get("workKey"):
            body["workKey"] = str(args["workKey"])
        if args.get("repo"):
            body["repo"] = str(args["repo"])
        if args.get("check"):
            body["check"] = str(args["check"])
        if args.get("retry"):
            body["retry"] = True
        status, payload = _request("POST", "/api/tasks", body)
        return {
            "ok": True,
            "status": status,
            "task": payload.get("task"),
            "deduped": bool(payload.get("deduped")),
            "retried": bool(payload.get("retried")),
        }

    return _run(go)


def tasks_list(args: dict, **kwargs) -> str:
    """List every task in the engine's store (same projection as CLI/MCP)."""

    def go():
        status, payload = _request("GET", "/api/tasks")
        tasks = [
            {
                "id": t.get("id"),
                "workKey": t.get("workKey"),
                "status": t.get("status"),
                "text": t.get("text"),
                "retries": t.get("retries") or 0,
                "createdAt": t.get("createdAt"),
            }
            for t in (payload.get("tasks") or [])
        ]
        return {"ok": status == 200, "tasks": tasks}

    return _run(go)


def tasks_message(args: dict, **kwargs) -> str:
    """Append a coordination message to a task's thread (id or work key)."""

    def go():
        ref = (args.get("ref") or "").strip()
        text = (args.get("text") or "").strip()
        if not ref or not text:
            return {"ok": False, "error": "Need ref and text"}
        sender = args.get("from") or os.environ.get("SWITCHBOARD_AGENT") or "hermes"
        status, payload = _request(
            "POST",
            "/api/tasks/" + urllib.parse.quote(ref, safe="") + "/messages",
            {"text": text, "from": sender},
        )
        return {"ok": True, "status": status, "message": payload.get("message"), "task": payload.get("task")}

    return _run(go)


def tasks_complete(args: dict, **kwargs) -> str:
    """Finalize a task through the engine's done gate. Refusals (task still
    running, steps unfinished, check failing, task denied) come back verbatim
    as {ok: false, error, status, task}."""

    def go():
        ref = (args.get("ref") or "").strip()
        if not ref:
            return {"ok": False, "error": "No task ref provided"}
        status, payload = _request(
            "POST",
            "/api/tasks/" + urllib.parse.quote(ref, safe="") + "/complete",
            {"summary": args.get("summary") or ""},
        )
        return {"ok": True, "status": status, "task": payload.get("task"), "already": bool(payload.get("already"))}

    return _run(go)


def tasks_log(args: dict, **kwargs) -> str:
    """Read one task's full record by id or work key (resolve via list, then
    the engine's log path — the same two-step the MCP face uses)."""

    def go():
        ref = (args.get("ref") or "").strip()
        if not ref:
            return {"ok": False, "error": "No task ref provided"}
        _status, listing = _request("GET", "/api/tasks")
        task = next(
            (t for t in (listing.get("tasks") or []) if t.get("id") == ref or t.get("workKey") == ref),
            None,
        )
        if not task:
            return {"ok": False, "error": "task not found", "status": 404}
        _status, payload = _request("GET", "/api/tasks/" + urllib.parse.quote(str(task["id"]), safe="") + "/log")
        return {"ok": True, **payload}

    return _run(go)
