# visvoai-cli

A developer-tool CLI built on [`visvoai-core`](https://pypi.org/project/visvoai-core/).
The agent reads and edits local files, runs shell commands, and streams its work
to stdout. It is also the reference example of consuming `visvoai-core` to build
a real surface.

## Install

```bash
pip install visvoai-cli
```

That's everything — `visvoai-core`, `visvoai-ai`, and **all** provider integrations
(Gemini, Anthropic, OpenAI + any OpenAI-compatible provider). The model picker's full
catalog works out of the box; you only supply an API key for the provider you use.

### From source (local checkout)

Install as an editable command on your PATH — code changes are picked up live:

```bash
uv tool install --editable path/to/visvoai-cli
# then, from any directory:
visvoai
```

## Usage

```bash
export GEMINI_API_KEY=...
visvoai "list the Python files in the current directory"
visvoai --cwd ./myproject "add type hints to utils.py"
```

Run `visvoai --help` for options (model, working directory, verbose streaming).

## License

MIT
