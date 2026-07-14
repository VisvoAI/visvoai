"""Any OpenAI-compatible endpoint — and your own Provider subclass.

    pip install "visvoai-ai[openai]"
    python 03_openai_compatible_and_custom.py     # structure runs w/o a key

Two ways to reach beyond the built-in provider families:

  A. You don't need a subclass for most things — Together, Groq, OpenRouter,
     vLLM, LM Studio, llama.cpp servers are all OpenAI-compatible: an api key
     + base_url through OpenAICompatProvider and you're done.
  B. A genuinely different provider family (custom auth, custom streaming)
     subclasses Provider — all methods optional; implement what exists.
"""
from visvoai.ai.providers.base import NotSupported, Provider
from visvoai.ai.providers.openai_compat import OpenAICompatProvider

# ── A · an OpenAI-compatible endpoint: no new code, just configuration ───────
import os
if os.environ.get("GROQ_API_KEY"):
    model = OpenAICompatProvider().build(
        slug="llama-3.3-70b-versatile",
        api_key=os.environ["GROQ_API_KEY"],
        base_url="https://api.groq.com/openai/v1",
    )
    print(model.invoke("One word: fast or slow?").content)
else:
    print("(set GROQ_API_KEY — or any compatible endpoint's key — to run part A)")


# ── B · a custom provider family: subclass, implement what you have ─────────
class EchoProvider(Provider):
    """A fake 'provider' proving the seam: build_chat_model is the only method
    the agent loop needs; everything else defaults to NotSupported."""

    def build_chat_model(self, model_id: str, **kwargs):
        from langchain_core.language_models.fake_chat_models import FakeListChatModel
        return FakeListChatModel(responses=[f"[{model_id}] echo: hello"])


model = EchoProvider().build_chat_model("demo-1")
print(model.invoke("hi").content)

try:
    EchoProvider().search("anything", slug="demo-1")
except (NotSupported, NotImplementedError):
    print("unimplemented capabilities raise NotSupported — consumers can probe")
