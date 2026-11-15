"""Generates docs/PROTOCOL.md from the live EVENTS table so docs cannot drift from code."""
from rx_agent.events import EVENTS

print("""# RX wire protocol

Transport: WebSocket at `/ws` (JSON text frames). Browsers send an `Origin` header and are rejected unless it is
the server's own origin. The **first** message must authenticate:

```json
{"type": "auth", "token": "<token printed by rx serve>"}
```

## Client → server

| type | fields | notes |
|---|---|---|
| `auth` | `token` | must be first; 10 s timeout |
| `run` | `task`, `workspace?`, `mode?`, `session_id?` | one run at a time per connection; `mode` is clamped to the server's `--max-mode` |
| `cancel` | – | cancels the current run; running commands are killed |
| `approval_response` | `id`, `approved`, `remember?`, `message?` | answers an `approval_required` event |
| `undo` | `workspace?`, `snapshot_id?` | restore point (default: latest) |
| `sessions` / `snapshots` | `workspace?` | list saved sessions / restore points |
| `ping` | – | answered with `pong` |

## Server → client (control)

| type | meaning |
|---|---|
| `ready` | auth OK. `{version, max_mode, modes[], roots[], model, limits{max_run_tokens, max_run_seconds}}` |
| `run_finished` | always sent when a run ends (completed, cancelled, error). `{result}` |
| `undo_result`, `sessions`, `snapshots`, `pong` | replies |
| `error` | `{code, message}`; codes: `unauthorized`, `bad_request`, `busy`, `unknown_approval`, `internal` |

## Server → client (agent events)

Every event also carries `seq` (monotonic) and `ts` (unix seconds).

| type | payload |
|---|---|""")
for name, doc in EVENTS.items():
    print(f"| `{name}` | {doc} |")
print("""
## Result object (`run_finished.result`, `task_completed.result`)

`status` (`completed | cancelled | error | stuck | gave_up | iteration_limit | budget_exceeded`), `final_response`, `iterations`,
`usage`, `files_modified[]`, `files_read[]`, `tools_executed`, `verification {ran, passed, dirty_since_last_pass,
commands[]}`, `snapshot_id`, `session_id`, `duration`, `approval_wait` (seconds spent waiting for the human), `error`.

## HTTP

`GET /health` (open) · `GET /ui` (web UI) · `GET /v1/info`, `GET /v1/sessions`, `POST /v1/run` (Bearer token).
`POST /v1/run` is non-interactive: anything that would need approval is denied, so use `plan` or `auto_edit`.
""")
