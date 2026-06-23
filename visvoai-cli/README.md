# visvoai-cli

A developer-tool CLI built on [`visvoai-core`](https://pypi.org/project/visvoai-core/).
The agent reads and edits local files, runs shell commands, and streams its work
to stdout. It is also the reference example of consuming `visvoai-core` to build
a real surface.

## Install

```bash
pip install visvoai-cli
```

This pulls `visvoai-core` and the default Gemini model integration.

## Usage

```bash
export GEMINI_API_KEY=...
visvoai "list the Python files in the current directory"
visvoai --cwd ./myproject "add type hints to utils.py"
```

Run `visvoai --help` for options (model, working directory, verbose streaming).

## License

MIT
