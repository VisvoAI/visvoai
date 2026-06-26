"""mermaid.py — render ```mermaid fences to a viewable HTML file (no local deps).

A terminal can't draw a mermaid diagram, so instead of rendering it locally
(which would need a headless browser), we write a tiny self-contained HTML file
into the conversation's own folder and open it in the user's browser. The browser
loads mermaid.js from a CDN and does the rendering — nothing to install.

Pure helpers: no Textual, no app state. The widget + app wire these to a click.
"""
from __future__ import annotations

import hashlib
import html
import re
import webbrowser
from pathlib import Path

# A fenced ```mermaid block. Non-greedy body; tolerant of a trailing newline before
# the closing fence. The language tag is matched case-insensitively (```Mermaid),
# but it MUST be present — we never guess a bare ``` fence is a diagram, since that
# would mis-render ordinary code. The system prompt instructs the model to use this
# exact fence; anything it emits otherwise degrades to a normal code block (no loss).
_FENCE = re.compile(r"```[ \t]*mermaid[ \t]*\r?\n(.*?)```", re.DOTALL | re.IGNORECASE)

_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
  body {{ margin: 0; padding: 24px; background: #ffffff;
          font-family: system-ui, sans-serif; }}
  .mermaid {{ display: flex; justify-content: center; }}
</style>
</head>
<body>
<pre class="mermaid">
{source}
</pre>
<script type="module">
  import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs';
  mermaid.initialize({{ startOnLoad: true }});
</script>
</body>
</html>
"""


def extract_mermaid(text: str) -> list[str]:
    """Every ```mermaid block's source (trimmed), in order. Empty list if none."""
    return [m.group(1).strip() for m in _FENCE.finditer(text or "") if m.group(1).strip()]


def split_segments(text: str) -> list[tuple[str, str]]:
    """Split an answer into ordered ('text', md) / ('mermaid', source) segments, so
    the raw fence can be REPLACED inline by a diagram card instead of left as code.
    Text segments are returned verbatim (caller skips blank ones); mermaid segments
    are trimmed. Always returns at least one segment."""
    text = text or ""
    segs: list[tuple[str, str]] = []
    last = 0
    for m in _FENCE.finditer(text):
        if m.start() > last:
            segs.append(("text", text[last:m.start()]))
        source = m.group(1).strip()
        if source:
            segs.append(("mermaid", source))
        last = m.end()
    if last < len(text):
        segs.append(("text", text[last:]))
    return segs or [("text", text)]


def write_diagram_html(conv_dir: Path, source: str) -> Path:
    """Write a self-contained viewer for `source` into `conv_dir`, named by a content
    hash so identical diagrams reuse one file (and distinct ones never collide).
    Returns the file path. The diagram source is HTML-escaped — mermaid reads the
    element's textContent, which un-escapes entities back to the raw definition."""
    conv_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(source.encode("utf-8")).hexdigest()[:8]
    path = conv_dir / f"diagram-{digest}.html"
    if not path.exists():
        path.write_text(
            _HTML.format(title=f"diagram-{digest}", source=html.escape(source)),
            encoding="utf-8",
        )
    return path


def open_path(path: Path) -> bool:
    """Open a file in the default browser. Returns webbrowser's success flag."""
    return webbrowser.open(path.as_uri())
