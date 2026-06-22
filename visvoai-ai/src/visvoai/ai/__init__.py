"""
visvoai.ai — Unified multi-provider LLM access.

Provides a single Provider facade across Gemini, Anthropic, OpenAI, and Together.
ModelRegistry maps model IDs to capability-aware provider implementations.

Public API (populated as code is migrated from backend/llm/):
  from visvoai.ai import ModelRegistry, Provider, Capability
"""
