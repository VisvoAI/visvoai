"""
visvoai.cli.context — the configurable context-assembly pipeline.

`build_assembler(system_prompt, cwd)` is the single entry point: it constructs the
v1 providers, applies the layered config, and returns a ready ContextAssembler for
CLIRuntime to drive from its `_build_agent_node` hook.
"""
from __future__ import annotations

from .assembler import ContextAssembler
from .config import apply_to_providers, global_budget, load_context_config
from .protocol import ContextProvider, ContextSection
from .providers import (
    BasePromptProvider,
    DateTimeProvider,
    EnvironmentProvider,
    GitStateProvider,
    ProjectInstructionsProvider,
)

__all__ = [
    "ContextAssembler",
    "ContextProvider",
    "ContextSection",
    "build_assembler",
]


def build_assembler(system_prompt: str, cwd: str) -> ContextAssembler:
    """The v1 assembler: 5 providers + layered config applied."""
    providers = [
        BasePromptProvider(system_prompt),
        ProjectInstructionsProvider(cwd),
        EnvironmentProvider(cwd),
        DateTimeProvider(),
        GitStateProvider(cwd),
    ]
    config = load_context_config(cwd)
    apply_to_providers(providers, config)
    return ContextAssembler(providers, global_budget_tokens=global_budget(config))
