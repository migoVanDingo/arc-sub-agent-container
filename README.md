# arc-sub-agent-container

An out-of-tree **arc sub-agent** that acts as a container-orchestration expert.
Hand it a goal in plain terms — "run redis and a python web app that talks to
it, expose the web app on 8080" — and it selects images, wires a shared
network, publishes ports, deploys the containers, **health-checks every one of
them**, and returns a structured JSON report. It never says "healthy" without a
passing check.

It drives the [`container-orchestration-service`](https://github.com/migoVanDingo/container-orchestration-service)
(`cos`) over MCP: `container_run`, `container_ensure`, `container_exec`,
`container_logs`, `container_stop`, `container_rm`, `container_list`,
`container_reap`, and `network_create` / `network_list` / `network_remove`.
Local file/curl work goes through core `bash_exec` + `ls`.

The parent session sees one tool: `subagent_container_expert`.

## Requirements — install these first

This sub-agent references the `cos` tools **by name**; it does not ship them.
The runner raises a clear `ToolError` at dispatch if they're missing. So:

1. **Run the cos MCP server** (from the container-orchestration-service repo):

   ```bash
   cos serve --port 8770
   ```

2. **Register it with arc using an empty tool prefix** so the tool names match
   what this spec expects (`container_run`, not `container_container_run`):

   ```bash
   arc mcp add container --transport http --url http://127.0.0.1:8770/mcp --tool-prefix ""
   ```

3. **Install this sub-agent** into the same environment as arc:

   ```bash
   pip install -e /path/to/arc-sub-agent-container
   ```

   arc discovers it on next start; enable it via `arc subagents`.

## Enforcing delegation (optional but recommended)

The parent session holds the `container_*` / `network_*` tools too (arc
intersects a sub-agent's tools with the parent registry), so by default the main
agent *can* orchestrate directly and skip this sub-agent's deploy-then-verify
discipline. Unlike a capability-locked sub-agent (e.g. a Vertex video analyst,
where only the child can do the work), nothing is fenced off here — so if you
want the guarantee, add a policy moat with the built-in `guard` plugin:

```yaml
# in the guard plugin's config block
delegate_only_tools:
  'container_*': subagent_container_expert
  'network_*': subagent_container_expert
```

Now a direct `container_*` / `network_*` call from the main session is denied
with a hint to route through `subagent_container_expert`; the same calls pass
inside the sub-agent's own session. The dispatch tool itself is never blocked,
so delegation still works. (Requires arc with `guard.delegate_only_tools`
support.)

> **⚠️ Enforcement note (updated after the 2026-07 mitigation pass).** Child
> sessions now inherit a **hard-denylist guard** built from the parent's
> blocklist (`agent-runtime/_mitigation/07`), so a sub-agent's `bash_exec` can no
> longer run `rm -rf`, `dd`, `mkfs`, fork bombs, block-device writes, or **raw
> `docker`** — that closes the "shell out to `docker run --privileged`" escape.
> `curl` (health checks) and file writes stay allowed so the sub-agent still
> works. **`bash_exec` is kept deliberately (accepted risk, 2026-07-06):** it can
> still read host files / run arbitrary non-blocklisted commands, and the child
> runs against a provider that sees the output — but dispatches are **stateless**
> (no cross-dispatch memory), so the sub-agent needs a general shell to improvise
> and finish a task in one shot. For a single trusted operator that trade is
> worth it. **Revisit only if you point this sub-agent at untrusted/adversarial
> input** — then replace `bash_exec` with scoped `write_build_file`/`http_check`
> tools. See `agent-runtime/_code_review/02-security-audit.md` (H2).

## Provider — Gemini 3.5 Flash by default, any provider by override

Container orchestration is high-volume, tool-heavy, low-reasoning work, so the
spec pins **`gemini` / `gemini-3.5-flash`** for speed and price. That's a
default, not a hard wire — every provider field is overridable from the
`subagents:` block in `~/.arc/config.yml`, which arc's Registry merges onto the
shipped spec after `build()`.

**Point it at a local model** (e.g. on a GPU box running Ollama or llama.cpp):

```yaml
subagents:
  container_expert:
    provider: ollama                       # or: llama_cpp
    model: qwen2.5-coder:14b               # whatever you've pulled/loaded
    base_url: http://localhost:11434       # ollama default; llama.cpp: http://localhost:8080/v1
    # api_key_env: ...                     # only if your endpoint needs a key
```

`base_url`, `api_key_env`, and `params` all thread straight through to the
child's provider config, so the same orchestration methodology runs unchanged
against a local model. Everything else (system prompt, tool allowlist, dispatch
guards) is preserved across the override.

Other useful overrides:

```yaml
subagents:
  container_expert:
    timeout_s: 600                 # longer deploy-verify loops
    max_dispatches_per_session: 3  # tighten the quota
    max_turns: 40
```

## What it returns

A single JSON object (the parent parses it directly):

```json
{
  "goal": "run redis + a python web app that reads from it, expose web on 8080",
  "status": "healthy",
  "network": "cos-appnet",
  "containers": [
    {"name": "redis", "image": "redis:7-alpine", "state": "running",
     "healthy": true, "ports": [], "dns_name": "cos-redis"},
    {"name": "web", "image": "python:3.11-slim", "state": "running",
     "healthy": true, "ports": ["8080:8000"], "dns_name": "cos-web"}
  ],
  "endpoints": [{"url": "http://127.0.0.1:8080/", "reachable": true}],
  "checks": [
    {"target": "web", "method": "curl http://127.0.0.1:8080/", "ok": true, "detail": "HTTP 200"},
    {"target": "web->redis", "method": "container_exec redis-cli -h cos-redis ping", "ok": true, "detail": "PONG"}
  ],
  "notes": "...",
  "next_steps": ["add a volume for redis persistence"]
}
```

`status` is `healthy` only if every required check passed; `degraded` if it runs
but something is unverified/failed; `failed` if it couldn't come up.

## Networking model (what the prompt teaches the child)

- Containers that must talk to each other go on a **user-defined network**
  (`network_create <name>`, then `network=<name>` on each container).
- On a user network, a persistent container named `X` is reachable from peers at
  hostname **`cos-X`** — cos prefixes managed names with `cos-`. Use that in
  connection strings, not `localhost`.
- To reach a service from the host (curl checks), **publish a port**
  (`ports=["8080:80"]`, bound to `127.0.0.1`). The default `network="none"` has
  no connectivity; `bridge` has host reach but no inter-container DNS; `host`
  mode is forbidden.

## Development

```bash
pip install -e ".[dev]"
pip install -e ../v2          # so `from arc.subagent_api import ...` resolves
pytest
```

The tests run without Docker or a live model — they only exercise `build()` and
the override path.

## License

MIT — see `LICENSE`.
