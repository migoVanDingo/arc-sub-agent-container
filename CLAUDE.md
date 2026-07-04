# arc-sub-agent-container — developer guide

An out-of-tree arc sub-agent (`arc.subagents` entry point) that contributes a
single `SubAgentSpec`: **`container_expert`**, a container-orchestration expert.
Forked from `arc-sub-agent-template`.

| | |
|---|---|
| Target API | `arc.subagent_api` (v0.1+) |
| Provider | `gemini` / `gemini-3.5-flash` (default; overridable) |
| Depends on | the `cos` MCP server for `container_*` / `network_*` tools |
| Parent tool | `subagent_container_expert` |

## Code map

```
src/arc_sub_agent_container/
  spec.py              SubAgentSpec + build() entry point
  prompts/system.md    the container-expert methodology + output schema
tests/test_spec.py     build() field assertions + the local-provider override
```

## The two things that make this sub-agent work

1. **The cos tools must be in the parent registry under their native names.**
   The spec's `tools` allowlist lists `container_run`, `container_ensure`,
   `network_create`, etc. Those come from the `cos` MCP server. Register it in
   arc with an **explicit empty tool prefix** so the names aren't doubled:

   ```bash
   arc mcp add container --transport http --url http://127.0.0.1:8770/mcp --tool-prefix ""
   ```

   (arc distinguishes an unset prefix — falls back to the server name, giving
   `container_container_run` — from an explicit `""`, which strips the prefix.)
   If the tools are absent at dispatch, arc's runner raises a clear `ToolError`.

2. **Provider is a default, not a wire.** `build()` pins Gemini 3.5 Flash, but
   the runner threads `provider` / `model` / `base_url` / `api_key_env` /
   `params` from the spec into the child's provider config. Users override via
   the `subagents:` config block (Registry merges field-level). The
   `test_provider_is_overridable_for_local_models` test locks in the
   ollama/llama.cpp override path. Do NOT read overrides in `build()`.

## Conventions

- Use Edit/Write, not bash heredocs.
- No multi-paragraph docstrings; WHY-only comments.
- No emojis in code / commits / PRs.
- Run `pytest` after non-trivial changes (needs arc checked out next door:
  `pip install -e ../v2`).
- Keep the `tools` allowlist tight and the prompt's output schema in sync with
  `spec.expected_output`.
