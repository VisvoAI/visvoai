"""
identity.py — composite deployment identity (provider × model × thinking effort).

A *model* (e.g. "llama-3.3-70b") can be served by several *providers* (Together,
Groq, OpenRouter) at different prices. The thing we resolve, price, and track is a
**deployment**, identified by a composite id. The string scheme is pluggable via
IdentityCodec so a consumer can adapt it (the CLI keeps the readable default; a
platform may inject an opaque/stable id for its datastore).

Default scheme — ColonAtCodec:  "<provider>:<model>[@<effort>]"
  gemini:gemini-3-flash@medium   together:llama-3.3-70b   openrouter:deepseek-r1@high
(no "@effort" == no thinking.)
"""
from __future__ import annotations

from typing import NamedTuple, Optional, Protocol, runtime_checkable


class DeploymentId(NamedTuple):
    """The three axes of a deployment identity."""
    provider: str
    model: str
    effort: Optional[str] = None   # neutral thinking intent; None = off / non-reasoning


@runtime_checkable
class IdentityCodec(Protocol):
    """Builds/parses the string form of a DeploymentId. Override to change the scheme.

    Contract: parse(build(p, m, e)) == DeploymentId(p, m, e). A single codec must own
    a given surface (the writer of a stored id must be its reader) — don't mix codecs
    against one store.
    """
    def build(self, provider: str, model: str, effort: Optional[str] = None) -> str: ...
    def parse(self, deployment_id: str) -> DeploymentId: ...


class ColonAtCodec:
    """Readable default: ``provider:model[@effort]``.

    Splits on the FIRST ':' (provider) and the FIRST '@' (effort), so model slugs
    that contain '/' (OpenRouter's ``vendor/model``) pass through untouched.
    """

    def build(self, provider: str, model: str, effort: Optional[str] = None) -> str:
        if not provider or not model:
            raise ValueError("provider and model are required to build a deployment id")
        base = f"{provider}:{model}"
        return f"{base}@{effort}" if effort else base

    def parse(self, deployment_id: str) -> DeploymentId:
        provider, sep, rest = deployment_id.partition(":")
        if not sep or not provider or not rest:
            raise ValueError(f"not a deployment id (expected 'provider:model[@effort]'): {deployment_id!r}")
        model, at, effort = rest.partition("@")
        if not model or (at and not effort):
            raise ValueError(f"malformed deployment id: {deployment_id!r}")
        return DeploymentId(provider, model, effort or None)


# The default codec instance consumers get unless they inject their own.
DEFAULT_CODEC: IdentityCodec = ColonAtCodec()
