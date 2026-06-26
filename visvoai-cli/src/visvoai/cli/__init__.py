"""
visvoai.cli — Developer tool CLI built on visvoai-core.

Two surfaces, one entry point (`visvoai`, a console script):
  • `visvoai`            → launch the Textual TUI (a REPL coding agent)
  • `visvoai "prompt"`   → single-shot: stream one turn to stdout

The agent reads/edits local files, runs shell commands, searches the web, and
renders its work (diffs, tools, thinking, diagrams) in the terminal.

VisvoApp (the Textual app) is exposed lazily so importing this package — or the
single-shot path — does not pull in Textual until the TUI is actually launched.
"""


def __getattr__(name):
    # PEP 562 lazy export: `from visvoai.cli import VisvoApp` works without making
    # Textual a hard cost of every `import visvoai.cli`.
    if name == "VisvoApp":
        from visvoai.cli.app import VisvoApp
        return VisvoApp
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["VisvoApp"]
