# visvoai-ai examples

| File | Teaches | Needs a key? |
|---|---|---|
| [`01_hello_model.py`](./01_hello_model.py) | one line to any provider's streaming model | yes |
| [`02_choose_and_meter.py`](./02_choose_and_meter.py) | the registry: pick models by facts (price, context, thinking); meter a call's cost | listing: **no** · metering: yes |
| [`03_openai_compatible_and_custom.py`](./03_openai_compatible_and_custom.py) | any OpenAI-compatible endpoint (Groq/Together/vLLM/…) with zero new code, and a custom `Provider` subclass | structure: **no** |

```bash
pip install "visvoai-ai[gemini]"
export GEMINI_API_KEY=...
python examples/01_hello_model.py
```
