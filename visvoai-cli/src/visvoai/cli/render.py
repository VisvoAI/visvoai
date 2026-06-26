"""RenderMixin — answer rendering with inline mermaid diagram extraction.

A ```mermaid fence in an answer is split out into a prominent MermaidCard instead
of left as copyable-looking source; clicking a card writes a self-contained HTML
viewer into the conversation folder and opens it in the browser. Shared by the
live turn (`_reflow_answer` at turn end) and replay (`_mount_answer`)."""
from __future__ import annotations

from textual.containers import VerticalScroll

from visvoai.cli import mermaid, store
from visvoai.cli.widgets import Assistant, MermaidCard


class RenderMixin:
    """Answer + mermaid rendering. Mixed into the app; relies on the shell's
    `_mount_block` and the conversation-id/cwd state."""

    async def _mount_answer(self, log: VerticalScroll, raw_text: str) -> None:
        """Mount an answer, splitting ```mermaid fences out into prominent diagram
        cards so the raw source never shows as copyable code. Text → markdown
        blocks; each mermaid fence → a MermaidCard. The first piece carries the
        inter-block gap; the rest sit flush as one answer group. Used by replay."""
        first = True
        for kind, content in mermaid.split_segments(raw_text):
            if kind == "text":
                if not content.strip():
                    continue
                w = Assistant()
            else:
                w = MermaidCard(content)
            if first:
                await self._mount_block(log, w, "answer")
            else:
                await log.mount(w)
            if isinstance(w, Assistant):
                await w.add(content)
            first = False
        log.scroll_end(animate=False)

    async def _reflow_answer(self, log: VerticalScroll, block) -> None:
        """At turn end, replace a streamed answer block IN PLACE with its split
        segments when it carries a ```mermaid fence — text stays markdown, the
        fence becomes a card. No fence → leave the streamed block untouched."""
        segments = mermaid.split_segments(getattr(block, "_raw", ""))
        if not any(kind == "mermaid" for kind, _ in segments):
            return
        anchor = block
        first_gap = block.has_class("blk-gap")
        first = True
        for kind, content in segments:
            if kind == "text":
                if not content.strip():
                    continue
                w = Assistant()
            else:
                w = MermaidCard(content)
            await log.mount(w, after=anchor)
            if first and first_gap:
                w.add_class("blk-gap")   # inherit the replaced block's leading gap
            if isinstance(w, Assistant):
                await w.add(content)
            anchor = w
            first = False
        await block.remove()

    def on_mermaid_card_clicked(self, msg) -> None:
        """Render the diagram to an HTML viewer in the conversation folder and open
        it in the browser. Resolves the conversation id lazily (a diagram can be
        opened before the first save in a fresh, unsaved turn)."""
        msg.stop()
        if self._project_id is None:
            self._project_id = store.resolve_project_id(self._cwd)
        if self._conv_id is None:
            self._conv_id = store.new_conversation_id()
        try:
            conv_dir = store.conversation_dir(self._project_id, self._conv_id)
            path = mermaid.write_diagram_html(conv_dir, msg.source)
            if mermaid.open_path(path):
                self.notify("opened diagram in browser")
            else:
                self.notify(f"diagram written to {path}", severity="warning")
        except Exception as e:  # writing/opening must never crash the app
            self.notify(f"could not open diagram: {e}", severity="error")
