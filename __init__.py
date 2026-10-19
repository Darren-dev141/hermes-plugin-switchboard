"""hermes-plugin-switchboard: Switchboard's task road as native Hermes tools.

Registers five tools over the Switchboard engine's HTTP API — the same paths
the kit's CLI and MCP face use, against the same store:

  * switchboard_tasks_create    submit work (work-key idempotent)
  * switchboard_tasks_list      list the store
  * switchboard_tasks_message   append a coordination note to a task thread
  * switchboard_tasks_complete  finalize through the engine's done gate
  * switchboard_tasks_log       read a task's full record

Configuration: SWITCHBOARD_URL env var, else the plugin's `url` setting
(plugins.entries.hermes-plugin-switchboard.settings.url), else
http://127.0.0.1:8787.
"""

from __future__ import annotations

import logging

from . import schemas, tools

logger = logging.getLogger(__name__)

_TOOLS = (
    ("switchboard_tasks_create", schemas.TASKS_CREATE, tools.tasks_create),
    ("switchboard_tasks_list", schemas.TASKS_LIST, tools.tasks_list),
    ("switchboard_tasks_message", schemas.TASKS_MESSAGE, tools.tasks_message),
    ("switchboard_tasks_complete", schemas.TASKS_COMPLETE, tools.tasks_complete),
    ("switchboard_tasks_log", schemas.TASKS_LOG, tools.tasks_log),
)


def register(ctx) -> None:
    """Wire schemas to handlers. Called once at Hermes startup."""
    try:
        tools.set_config_url(ctx.get_config("url", default="") or "")
    except Exception:  # config is an override, never a load blocker
        logger.debug("switchboard plugin: url setting unreadable; using env/default", exc_info=True)
    for name, schema, handler in _TOOLS:
        ctx.register_tool(name=name, toolset="switchboard", schema=schema, handler=handler)
