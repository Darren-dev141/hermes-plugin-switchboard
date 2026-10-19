# hermes-plugin-switchboard

Switchboard's task road as native Hermes tools. Switchboard already has two
faces over its engine — a CLI (`bin/switchboard.js`) and an MCP server
(`bin/switchboard-mcp.js`) in the kit. This plugin is the third face, for
Hermes: the same five operations, the same HTTP paths, the same store.

The plugin is a pure HTTP client of a running Switchboard engine. It never
opens the store itself, so everything it does lands in the one store the
engine, the web page, the CLI, and the MCP face all read.

## Tools

| Tool | Engine call | Notes |
|---|---|---|
| `switchboard_tasks_create` | `POST /api/tasks` | Submit work. Work-key idempotent (below). |
| `switchboard_tasks_list` | `GET /api/tasks` | id, workKey, status, text, retries, createdAt per task. |
| `switchboard_tasks_message` | `POST /api/tasks/<ref>/messages` | Coordination note on a task thread; changes neither the run nor its gates. |
| `switchboard_tasks_complete` | `POST /api/tasks/<ref>/complete` | Finalize **through the done gate** (below). |
| `switchboard_tasks_log` | `GET /api/tasks/<id>/log` | Full record: task, steps, model calls, approval cards, results, logs, messages. |

`ref` is a task id or a work key; the engine resolves both.

## The road's laws, kept

- **Work keys make submission idempotent.** Pass a stable `workKey` (or let
  the engine derive one from text/repo/check): resubmitting the same
  assignment returns the existing task with `deduped: true` — no duplicate
  run, no second approval card. An errored task resubmits as a retry on the
  same record (`retried: true`). A denied task stays denied unless
  `retry: true` is passed.
- **Completion goes through the done gate.** `switchboard_tasks_complete`
  runs the same finalize path as a finished run — probe, the task's check in
  its worktree, commit. A task that is still running, has unfinished steps,
  fails its check, or was denied is refused. The refusal is returned
  **verbatim** as the tool result (`{ok: false, error, status, task}`) —
  never softened, never retried around.
- **Single-flight.** The engine runs one run per task; a conflicting call
  gets the engine's 409, surfaced as-is.
- **Approvals are the engine's.** Creating a task enters the engine's
  approval flow exactly as a CLI submission does. This plugin adds no
  approval surface of its own and no way around one.

## Install

```sh
hermes plugins install Darren-dev141/hermes-plugin-switchboard
hermes plugins enable hermes-plugin-switchboard
```

Or manually: copy this directory to `~/.hermes/plugins/hermes-plugin-switchboard`
and run `hermes plugins enable hermes-plugin-switchboard`.

Requires Hermes >= 0.21.5 (manifest v2 / plugin API 1, same floor as the
ecosystem's current plugins). No Python dependencies — standard library only.

## Configuration

The engine's base URL resolves in this order:

1. `SWITCHBOARD_URL` environment variable
2. The plugin setting `url` (`plugins.entries.hermes-plugin-switchboard.settings.url`
   in `config.yaml`, or the Desktop Settings → Plugins form)
3. `http://127.0.0.1:8787` (the kit's `npm start` address)

Message sender defaults to the `SWITCHBOARD_AGENT` environment variable, or
`hermes` — per-call `from` overrides it.

If the engine is down, every tool fails soft with a clear error naming the
URL it tried (`cannot reach Switchboard at …`) instead of raising.

## Parity with the MCP face

Same endpoints, same success payloads, same engine-error shape, same
two-step log lookup (resolve id-or-workKey via the task list, then read the
log — because the log path is id-addressed). Deliberate differences:

- Tool names use underscores (`switchboard_tasks_create`) per Hermes tool
  naming; MCP uses `tasks-create`.
- `switchboard_tasks_list` surfaces the engine's error body when the list
  call fails; the MCP face reduces that case to `ok: false` with no error
  text.
- Message sender defaults to `hermes` (the MCP face defaults to `agent`).

## Tests

```sh
python3 tests/test_tools.py
```

Offline: the handlers run against a stub implementing the engine's HTTP
contract — create, work-key dedupe, message, done-gate refusal surfaced
verbatim, log lookup, and the engine-down error. 9 checks.

## License

MIT © Darren Foote
