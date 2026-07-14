"""The registry: choose a model by facts, then meter what a call cost.

    pip install "visvoai-ai[gemini]"
    python 02_choose_and_meter.py          # listing works with NO api key

The catalog = a curated baked set + the live models.dev catalog for providers
you hold keys for — new models appear without a package upgrade.
"""
from visvoai.ai import Capability, build_chat_model, cost_of, list_deployments, usage_from

# ── choose: every deployment carries its facts ───────────────────────────────
for d in list_deployments(Capability.CHAT)[:10]:
    thinking = ",".join(l.value for l in d.thinking_levels) or "-"
    print(f"{d.id:<42} ${d.input_cost_per_million:>6.2f}/M in "
          f"ctx={d.context_window:>9,}  thinking: {thinking}")

# ── meter: usage + cost from a real call (needs GEMINI_API_KEY) ──────────────
import os
if os.environ.get("GEMINI_API_KEY"):
    dep = "gemini:gemini-2.5-flash"
    reply = build_chat_model(dep).invoke("Say hi in five words.")
    u = usage_from(reply)
    print(f"\n{reply.content}")
    print(f"tokens: {u['input']} in / {u['output']} out"
          f" → ${cost_of(dep, u['input'], u['output']):.6f}")
