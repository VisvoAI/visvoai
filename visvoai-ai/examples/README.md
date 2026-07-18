# visvoai-ai examples

```bash
pip install "visvoai-ai[gemini]"
export GEMINI_API_KEY=...
python examples/01_hello_model.py
```

**[`01_hello_model.py`](./01_hello_model.py) — how fast can I talk to a
model?** One line: name a provider and model, get a streaming chat model
back. Change the string, change the provider.

**[`02_choose_and_meter.py`](./02_choose_and_meter.py) — which model should
I use, and what did that call just cost?** *(listing needs no key)* The
registry knows every model's price, context size, and thinking levels — so
your code can *choose* by facts, then meter each call to the cent.

**[`03_openai_compatible_and_custom.py`](./03_openai_compatible_and_custom.py)
— my model isn't on your list. Now what?** *(structure needs no key)* Any
OpenAI-compatible endpoint (Groq, Together, vLLM, your own server) works
with zero new code; and if it's truly exotic, a `Provider` subclass is one
small class.
