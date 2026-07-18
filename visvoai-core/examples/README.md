# visvoai-core examples

In order — each builds on the previous; three run with **no API key**.

| File | Teaches | Needs a key? |
|---|---|---|
| [`01_minimal_agent.py`](./01_minimal_agent.py) | a working agent in ~20 lines: tools are plain Python functions | yes |
| [`02_streaming_events.py`](./02_streaming_events.py) | the live-UI pattern: astream_events → text chunks, tool starts, results | yes |
| [`03_creating_tools.py`](./03_creating_tools.py) | **the four ways to write a tool** — plain function, `Args:` help text, async, and the lifecycle class — and when to use which | **no** |
| [`04_extend_the_runtime.py`](./04_extend_the_runtime.py) | the extension seams: tool lifecycle, injected persistence, runtime hooks | **no** |
| [`05_tool_retrieval.py`](./05_tool_retrieval.py) | the 300-tools problem: index a fleet, bind only the relevant slice per request | **no** |
| [`06_sqlite_audit_trail.py`](./06_sqlite_audit_trail.py) | a real `ToolPersistence`: every call — including failures — audited into SQLite | **no** |
| [`07_everything_together.py`](./07_everything_together.py) | **the capstone** — model picked by registry facts, tools in three shapes, SQLite audit, retrieval over a fleet, multi-turn memory: one small product | **no** (scripted model; live with a key) |

```bash
pip install visvoai-core "visvoai-ai[gemini]"
python examples/03_creating_tools.py      # no key needed
```
