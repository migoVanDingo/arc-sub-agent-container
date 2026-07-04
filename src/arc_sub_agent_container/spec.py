"""container_expert — a container-orchestration sub-agent.

Delegate "get these containers running and prove they're healthy" to a focused
child agent. It drives the `cos` MCP server (container_* / network_* tools),
deploys workloads, wires multi-container topologies on a shared network, and
health-checks everything before returning a structured report.

Provider is pinned to Gemini 3.5 Flash — container orchestration is high-volume,
tool-heavy, low-reasoning work where Flash's speed and price win. It is NOT
hard-wired: provider/model/base_url/api_key_env are all overridable from the
`subagents:` block in arc's config.yml, so the same spec runs against a local
Ollama or llama.cpp model on a GPU box (see README).

The container_* / network_* tools come from the cos MCP server, not this
package. Install + register it first (see README); the runner raises a clear
ToolError at dispatch if the tools aren't in the parent registry.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from arc.subagent_api import SubAgentBuildContext, SubAgentSpec

_HERE = Path(__file__).resolve().parent
_SYSTEM_PROMPT = (_HERE / "prompts" / "system.md").read_text(encoding="utf-8")


def build(config: dict[str, Any], build_ctx: SubAgentBuildContext) -> SubAgentSpec:
    return SubAgentSpec(
        name="container_expert",
        description=(
            "Deploy and verify Docker workloads. Give it a goal in plain terms "
            "(e.g. 'run a redis and a python web app that talks to it, expose the "
            "web app on 8080') and it selects images, wires a shared network, "
            "publishes ports, and health-checks each container before reporting. "
            "Returns structured JSON: containers, endpoints, health, and next steps. "
            "Requires the cos MCP server (container_*/network_* tools)."
        ),
        provider="gemini",
        model="gemini-3.5-flash",
        system_prompt=_SYSTEM_PROMPT,
        # cos MCP tools (registered with an empty tool_prefix) + local shell for
        # writing build contexts / running curl health checks from the host.
        tools=(
            "container_run",
            "container_ensure",
            "container_exec",
            "container_logs",
            "container_stop",
            "container_rm",
            "container_list",
            "container_reap",
            "network_create",
            "network_remove",
            "network_list",
            "image_build",
            "image_remove",
            "image_list",
            "gc",
            "bash_exec",
            "ls",
        ),
        # Deploy-verify loops are multi-step (pull, start, poll, curl, fix) —
        # give it room, but the watchdog still bounds wall-clock.
        timeout_s=300.0,
        max_turns=30,
        # Orchestration is moderately expensive (spins real containers) — keep
        # the per-session quota modest so a confused parent can't fork-bomb it.
        max_dispatches_per_session=8,
        max_consecutive_failures=2,
        max_transient_retries=2,
        expected_output=(
            '{"goal": str, "status": "healthy" | "degraded" | "failed", '
            '"network": str | null, '
            '"containers": [{"name": str, "image": str, "state": str, '
            '"healthy": bool, "ports": [str], "dns_name": str | null}], '
            '"endpoints": [{"url": str, "reachable": bool}], '
            '"checks": [{"target": str, "method": str, "ok": bool, "detail": str}], '
            '"notes": str, "next_steps": [str]}'
        ),
    )
