from __future__ import annotations

import json

from arc_sub_agent_container.spec import build


def test_build_returns_spec(build_ctx):
    spec = build({}, build_ctx)
    assert spec.name == "container_expert"
    assert spec.provider == "gemini"
    assert spec.model == "gemini-3.5-flash"


def test_spec_description_is_actionable(build_ctx):
    spec = build({}, build_ctx)
    # Description is what the parent agent reads in the tool schema.
    d = spec.description.lower()
    assert "deploy" in d and "container" in d


def test_spec_tools_cover_container_and_network(build_ctx):
    spec = build({}, build_ctx)
    # Must reference the cos MCP tools by name plus a host shell.
    for t in ("container_run", "container_ensure", "container_exec",
              "container_logs", "network_create", "bash_exec"):
        assert t in spec.tools
    # Recursion is prohibited — no subagent_* in the allowlist.
    assert not any(t.startswith("subagent_") for t in spec.tools)


def test_spec_has_system_prompt_loaded_from_file(build_ctx):
    spec = build({}, build_ctx)
    assert len(spec.system_prompt) > 500
    assert "Container-orchestration sub-agent" in spec.system_prompt
    assert "Output schema" in spec.system_prompt
    # The DNS convention the child depends on must be spelled out.
    assert "cos-" in spec.system_prompt


def test_spec_guards_are_explicit(build_ctx):
    spec = build({}, build_ctx)
    # Orchestration spins real containers → modest quota.
    assert spec.max_dispatches_per_session == 8
    assert spec.max_consecutive_failures == 2
    assert spec.max_transient_retries == 2


def test_spec_timeout_and_turns(build_ctx):
    spec = build({}, build_ctx)
    assert spec.timeout_s == 300.0
    assert spec.max_turns == 30


def test_provider_is_overridable_for_local_models(build_ctx):
    """The pin is a default; local-provider override must be clean.

    The user deploys this to a GPU box and repoints it at ollama/llama_cpp via
    the `subagents:` config block. merged_with is what the Registry uses.
    """
    spec = build({}, build_ctx)
    local = spec.merged_with({
        "provider": "ollama",
        "model": "qwen2.5-coder:14b",
        "base_url": "http://localhost:11434",
    })
    assert local.provider == "ollama"
    assert local.model == "qwen2.5-coder:14b"
    assert local.base_url == "http://localhost:11434"
    # Everything else — prompt, tools, guards — is preserved.
    assert local.tools == spec.tools
    assert local.system_prompt == spec.system_prompt


def test_expected_output_is_a_parseable_sketch(build_ctx):
    spec = build({}, build_ctx)
    assert spec.expected_output is not None
    for field_name in ("status", "containers", "endpoints", "checks", "next_steps"):
        assert field_name in spec.expected_output


def test_build_ignores_config_dict(build_ctx):
    spec_empty = build({}, build_ctx)
    spec_with_junk = build(
        {"model": "should-be-ignored", "timeout_s": 9999, "garbage": True},
        build_ctx,
    )
    assert spec_empty == spec_with_junk


def test_spec_is_serializable_for_telemetry(build_ctx):
    spec = build({}, build_ctx)
    payload = {
        "name": spec.name,
        "provider": spec.provider,
        "model": spec.model,
        "tools": list(spec.tools),
        "timeout_s": spec.timeout_s,
        "max_turns": spec.max_turns,
        "max_dispatches_per_session": spec.max_dispatches_per_session,
        "max_consecutive_failures": spec.max_consecutive_failures,
        "max_transient_retries": spec.max_transient_retries,
    }
    json.dumps(payload)
