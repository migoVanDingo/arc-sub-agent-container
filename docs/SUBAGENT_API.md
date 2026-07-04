# arc sub-agent API — public surface

This is the **only** stable import path external sub-agent packages may
depend on:

```python
from arc.subagent_api import (
    # Spec surface
    SubAgentSpec,
    SubAgentBuildContext,

    # Result type (handed back to the parent agent — useful for
    # type-checked test code that drives the runner directly)
    SubAgentResult,

    # Error types
    SubAgentError,
    SubAgentTimeoutError,
    SubAgentRecursionError,
)
```

Importing from anywhere else (`arc.runtime.subagents`, `arc.runtime.scope`,
etc.) is **unsupported** — those modules can be refactored without notice.
`arc.subagent_api` is a thin re-export shim arc maintains specifically so
sub-agent authors have one path that won't move under them.

## API version

The shim exposes `arc.subagent_api.__api_version__` as a `(major, minor)`
tuple. **0.2** at time of writing.

### Version history

- **0.2** (2026-05-24) — added `SubAgentSpec.params: dict[str, Any]` field
  for provider-specific config (e.g., `vertex_gemini`'s `project_id` +
  `region`). Additive — v0.1 specs still work (default factory = empty
  dict).
- **0.1** — initial release.

### Breakage policy

- **Patch / minor bump (0.1 → 0.2 → 0.3):** additive — new optional fields
  on `SubAgentSpec`, new symbols. Existing specs keep working unchanged.
- **Major bump (0.x → 1.x):** breaking. Renames, signature changes, removed
  fields. arc will emit a deprecation warning for at least one release
  before the bump.

If your spec needs a specific minimum API version, assert it:

```python
from arc.subagent_api import __api_version__
assert __api_version__ >= (0, 2), "needs arc sub-agent API ≥ 0.2 for params field"
```

## The spec

```python
@dataclass(frozen=True)
class SubAgentSpec:
    name: str                              # registry key, used as subagent_<name> tool
    description: str                       # shown to the parent agent in the tool schema
    provider: str                          # "anthropic" | "gemini" | "vertex_gemini" | "ollama" | "llama_cpp" | ...
    model: str                             # provider-specific model id
    system_prompt: str                     # child's system prompt
    tools: tuple[str, ...]                 # tool names the child gets access to
    timeout_s: float = 300.0
    max_turns: int = 25
    api_key_env: str | None = None         # override; defaults from provider catalog
    base_url: str | None = None            # override; defaults from provider catalog
    expected_output: str | None = None     # appended to system prompt as a JSON-shape sketch
    max_dispatches_per_session: int = 5    # parent-loop guard
    max_consecutive_failures: int = 2      # circuit breaker
    max_transient_retries: int = 2         # runner-internal retry for network/rate-limit/5xx
    params: dict[str, Any] = field(default_factory=dict)  # provider-specific config (v0.2+)
```

### The `params` field (v0.2+)

Provider-specific config that gets merged into the child's
`ProviderConfig.params` at dispatch time. Use this when your sub-agent
pins a provider that needs extra config beyond `api_key_env` / `base_url`.

Examples:

- **`vertex_gemini`** needs `project_id` and `region`:
  ```python
  SubAgentSpec(
      ...,
      provider="vertex_gemini",
      params={"vertex_project_id": "my-gcp-project", "vertex_region": "us-east1"},
  )
  ```

- **Future providers** can read whatever they want from
  `cfg.params.get(...)`. arc-core doesn't validate the contents.

Spec authors typically populate `params` in `build()` from user config
keys (per design 0022's "Config injection" pattern). Most sub-agents
that use stock providers (anthropic / gemini / ollama) can leave
`params={}`.

Frozen dataclass. Equality compares by field. The Registry merges
field-level overrides from the user's `subagents:` config block on top of
the spec your `build()` returns — your spec is the baseline, not the final
word.

## The build function

```python
def build(config: dict, build_ctx: SubAgentBuildContext) -> SubAgentSpec:
    ...
```

- `config` is reserved for future use. Typically `{}`. **Do not read user
  overrides from here.** Overrides go through the `subagents:` block in
  arc's config.yml, which the Registry merges onto your returned spec.
  Putting override logic in `build()` will fight the Registry and produce
  surprising precedence.
- `build_ctx` is a `SubAgentBuildContext` — minimal in v0.1 (carries
  `arc_home: Path`, reserved for future expansion).
- The return value must be a single `SubAgentSpec`. If your package ships
  multiple specs, register multiple entry points in `pyproject.toml`, each
  pointing at its own builder.

## Dispatch guards — what they do and how to tune

| Field | Default | Purpose |
|---|---|---|
| `max_dispatches_per_session` | 5 | Parent-loop guard. Hard cap on how many times the parent agent can call this spec in one session. When exhausted, the tool raises `ToolError("quota exceeded …")`. |
| `max_consecutive_failures` | 2 | Circuit breaker. After N back-to-back failures, the spec is hard-locked for the rest of the session. Successful dispatch resets the counter. |
| `max_transient_retries` | 2 | Runner-internal retry for transient errors (network, rate-limit, 5xx). Logical errors (timeout, tool error, max_turns) are NEVER retried internally — they surface to the parent. |

Tune by spec character:
- **Cheap and fast** (log_grepper, classifier): higher quota (10–25), default
  guards otherwise.
- **Expensive and slow** (video_analyst, deep-reasoning): low quota (1–3),
  longer `timeout_s`, default breaker.
- **Flaky upstream** (third-party API with intermittent outages): bump
  `max_transient_retries` to 3–4.

Users can override any of these in their config:

```yaml
subagents:
  example_log_grepper:
    max_dispatches_per_session: 5    # tighten the quota the spec ships
    timeout_s: 30                    # tighten the timeout
```

## System prompt — load from a file

Sub-agent prompts get long. Keep them in `prompts/system.md` alongside
your `spec.py`, load at module import:

```python
from pathlib import Path
_HERE = Path(__file__).resolve().parent
_SYSTEM_PROMPT = (_HERE / "prompts" / "system.md").read_text(encoding="utf-8")
```

Markdown files diff cleanly, lint cleanly, and don't require Python string
escaping. Include a methodology section, an output-schema section, and a
"hard limits" section — this is your sub-agent's voice and matters more
than the dataclass fields combined.

Make sure `pyproject.toml` ships the prompts directory in the wheel:

```toml
[tool.hatch.build.targets.wheel.force-include]
"src/arc_sub_agent_<name>/prompts" = "arc_sub_agent_<name>/prompts"
```

## Tool allowlist — narrow is better

`tools` is a tuple of tool names from the parent's already-resolved tool
registry. The Runner intersects this list with the available tools at
dispatch time. A name in the allowlist that isn't available is a hard
error.

Sub-agents **do not ship tools**. If your sub-agent needs custom tools
(e.g., `extract_frames`), package them in a sibling plugin
(`arc-plugin-<thing>`) and reference them by name here. The user installs
both packages.

Keep the list as small as the methodology actually requires. A sub-agent
with `tools=("bash", "read", "ls", "grep", "find", "stat", ...)` is a sign
the methodology is unfocused — narrow the prompt or split into two specs.

## Expected output — a JSON-shape sketch

`expected_output` is appended to the child's system prompt as a guide,
not enforced. The Runner doesn't validate the child's final message
against it. It's there so:

- The child knows what shape to produce.
- The parent agent knows what shape to expect when calling the
  sub-agent (visible via `arc subagents show <name>`).

Use a compact form with type names, not strict JSON:

```
{"matches": [{"file": str, "line": int}], "total": int, "truncated": bool}
```

## What sub-agents are NOT

- **They don't have hooks.** No `on_session_start`, no `before_tool_call`,
  no event bus binding. Sub-agents are pure declarative data. If you need
  hooks, write a plugin.
- **They don't ship tools.** They reference tools by name from the
  parent's registry. Tool packs ship as plugins.
- **They don't have cross-dispatch state.** Each dispatch is a fresh
  micro-session with no memory of prior dispatches. If you need state,
  it lives in a sibling plugin's session-scoped storage and the sub-agent
  uses a tool to read it.
- **They don't dispatch other sub-agents.** Recursion is hard-prohibited
  (depth-1). Your spec's `tools` list cannot include `subagent_*` entries;
  even if it could, the Runner's tripwire would refuse.

## Quarantine and failure handling

Sub-agent failures are bounded by the dispatch guards, not by plugin-style
quarantine. The circuit breaker handles the "spec is broken" case; the
quota handles the "parent is looping" case. There is no equivalent of
`plugins.failure_threshold` for sub-agents — each session is independent.

`build()` failures (import errors, exceptions inside your builder) mean
the spec is silently dropped at startup with a `subagent.discovery.failed`
event. Don't catch exceptions defensively inside `build()` — let arc
handle it. The one exception: if your spec wants to refuse to load under
specific conditions (e.g., a required env var is unset), raise a clear
exception with a message — arc will log it and the user will see why their
spec is missing.

## Naming collisions

If two entry points register the same spec name, the first one wins (load
order) and arc emits a `subagent.discovery.collision` warning. Namespace
your spec name with a prefix relevant to your package:
`<vendor>_log_grepper`, not just `log_grepper`.

A spec whose entry-point name collides with a built-in spec (currently
just `_test_echo`) is also dropped with a warning. Don't prefix with `_`.
