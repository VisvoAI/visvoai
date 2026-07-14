"""One line to any model — stream a reply.

    pip install "visvoai-ai[gemini]"
    export GEMINI_API_KEY=...
    python 01_hello_model.py

Swap the deployment id to switch providers — nothing else changes:
    "anthropic:claude-sonnet-4-5"   (needs ANTHROPIC_API_KEY + [anthropic])
    "openai:gpt-4o-mini"            (needs OPENAI_API_KEY + [openai])
"""
from visvoai.ai import build_chat_model

model = build_chat_model("gemini:gemini-2.5-flash")

for chunk in model.stream("Explain attention in one sentence."):
    print(chunk.content, end="", flush=True)
print()
