"""Tool schemas — what the LLM sees. Descriptions mirror the Switchboard MCP
face (bin/switchboard-mcp.js in the kit) so every face states the road's laws
the same way."""

TASKS_CREATE = {
    "name": "switchboard_tasks_create",
    "description": (
        "Submit work to the Switchboard engine. A caller-supplied workKey (or one derived "
        "from text/repo/check) makes submission idempotent: resubmitting the same assignment "
        "returns the existing task instead of starting a duplicate run or a second approval "
        "card — the result then carries deduped: true. An errored task resubmits as a retry "
        "on the same record (retried: true); a denied task stays denied unless retry is true."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "The work to submit: a self-contained brief for the engine's captain/worker run.",
            },
            "workKey": {
                "type": "string",
                "description": "Optional stable key for this assignment (<= 256 chars). Reuse it to resubmit or retry the same assignment without duplicating it.",
            },
            "repo": {
                "type": "string",
                "description": "Optional repository path the work runs in.",
            },
            "check": {
                "type": "string",
                "description": "Optional done-gate check command run in the task's worktree at completion.",
            },
            "retry": {
                "type": "boolean",
                "description": "Optional. Resubmit a denied task as a retry on the same record.",
            },
        },
        "required": ["text"],
    },
}

TASKS_LIST = {
    "name": "switchboard_tasks_list",
    "description": "List every task in the Switchboard engine's store with its id, work key, status, and retry count.",
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}

TASKS_MESSAGE = {
    "name": "switchboard_tasks_message",
    "description": (
        "Append a message to a Switchboard task's thread. The task is addressed by id or work key. "
        "Messages are coordination notes; they do not change the task's run or its gates."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "ref": {
                "type": "string",
                "description": "Task id or work key.",
            },
            "text": {
                "type": "string",
                "description": "The message to append.",
            },
            "from": {
                "type": "string",
                "description": "Optional sender name recorded on the message (defaults to SWITCHBOARD_AGENT or 'hermes').",
            },
        },
        "required": ["ref", "text"],
    },
}

TASKS_COMPLETE = {
    "name": "switchboard_tasks_complete",
    "description": (
        "Finalize a Switchboard task by id or work key, through the engine's done gate exactly as a "
        "finished run does (probe, the task's check in its worktree, commit). A task whose steps are "
        "unfinished, whose check fails, or that the engine is still running is REFUSED — the refusal is "
        "returned verbatim as the result, not softened. A denied task cannot be completed. Completing an "
        "already-done task is an idempotent no-op (already: true)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "ref": {
                "type": "string",
                "description": "Task id or work key.",
            },
            "summary": {
                "type": "string",
                "description": "Optional completion summary recorded on the task.",
            },
        },
        "required": ["ref"],
    },
}

TASKS_LOG = {
    "name": "switchboard_tasks_log",
    "description": (
        "Read one Switchboard task's full record — the task, its steps, model calls, approval cards, "
        "results, logs, and messages — by task id or work key. This is the same read path the web page "
        "and the CLI's engine view use."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "ref": {
                "type": "string",
                "description": "Task id or work key.",
            },
        },
        "required": ["ref"],
    },
}
