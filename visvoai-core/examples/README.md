# visvoai-core examples

Seven small files, in order. Four run with **no API key** — you can watch the
machinery work before you spend anything:

```bash
pip install visvoai-core "visvoai-ai[gemini]"
python examples/07_everything_together.py     # no key needed — start here
```

### Start here if you're skimming

**[`07_everything_together.py`](./07_everything_together.py) — a whole product
in 180 lines.** *(no key needed)*
A tiny ops assistant: ask "is the api healthy?", then "restart **it** anyway."
Watch retrieval pick 3 relevant tools out of 10, memory resolve what "it"
means, and a SQLite audit row appear for the restart. Same file runs on a
real model when a key is present. If you read one file, read this one.

### Then, one idea at a time

**[`01_minimal_agent.py`](./01_minimal_agent.py) — how small is a real
agent?** ~20 lines. Tools are plain Python functions; no framework imports
anywhere in the file.

**[`02_streaming_events.py`](./02_streaming_events.py) — how do I build a
live UI on this?** Text chunks, tool-start events, tool results, as they
happen — the pattern every chat surface uses.

**[`03_creating_tools.py`](./03_creating_tools.py) — do I have to learn a
tool framework?** *(no key needed)* No. The four ways, from a bare function
to the lifecycle class — it even prints the exact help text the model sees
from your docstring.

**[`04_extend_the_runtime.py`](./04_extend_the_runtime.py) — what if I need
to change how the loop itself works?** *(no key needed)* The three seams —
tool lifecycle, injected persistence, runtime hooks — the same ones our own
CLI and a hosted platform are built on.

**[`05_tool_retrieval.py`](./05_tool_retrieval.py) — what happens when I
have 300 tools?** *(no key needed)* Binding all of them wrecks the model.
Index the fleet once, bind only the handful that match each request.

**[`06_sqlite_audit_trail.py`](./06_sqlite_audit_trail.py) — can I see every
call my agent ever made?** *(no key needed)* Implement four methods, inject
once — every call including failures lands in your database. No wrappers at
call sites.
