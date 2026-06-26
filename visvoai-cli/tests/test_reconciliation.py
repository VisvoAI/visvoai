"""ReconciliationBlock tests — kept / reverted / added summary after a redirect."""
from __future__ import annotations

import pytest

from textual.containers import VerticalScroll
from textual.widgets import Static

from visvoai.cli import VisvoApp
from visvoai.cli.widgets import ReconciliationBlock

KEPT = ["verification partial output", "flake reproduction note"]
REVERTED = ["full suite re-run"]
ADDED = ["grep connection timeout settings", "verify timeout ≠ 0"]


async def _mount(app, block):
    log = app.screen.query_one("#log", VerticalScroll)
    await log.mount(block)


def _style_has(text, needle: str) -> bool:
    return any(needle in str(span.style) for span in text.spans)


@pytest.mark.asyncio
async def test_reconciliation_renders_header():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        block = ReconciliationBlock(KEPT, REVERTED, ADDED, context="redirected after run 23/50")
        await _mount(app, block)
        await pilot.pause()
        head = block.query_one(".recon-header", Static).render()
        assert head.plain.startswith("⟲ ")
        assert "redirected after run 23/50" in head.plain
        assert _style_has(head, app.theme_variables["warning"])


@pytest.mark.asyncio
async def test_reconciliation_renders_all_sections():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        block = ReconciliationBlock(KEPT, REVERTED, ADDED)
        await _mount(app, block)
        await pilot.pause()
        tv = app.theme_variables
        kept = block.query_one(".recon-section-kept", Static).render()
        rev = block.query_one(".recon-section-reverted", Static).render()
        added = block.query_one(".recon-section-added", Static).render()
        assert kept.plain == "✓ kept" and _style_has(kept, tv["success"])
        assert rev.plain == "✗ reverted" and _style_has(rev, tv["error"])
        assert added.plain == "+ added" and _style_has(added, tv["success"])


@pytest.mark.asyncio
async def test_reconciliation_omits_empty_sections():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        block = ReconciliationBlock(KEPT, [], ADDED)
        await _mount(app, block)
        await pilot.pause()
        assert len(block.query(".recon-section-reverted")) == 0
        assert len(block.query(".recon-section-kept")) == 1
        assert len(block.query(".recon-section-added")) == 1


@pytest.mark.asyncio
async def test_reconciliation_kept_items():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        block = ReconciliationBlock(KEPT, REVERTED, ADDED)
        await _mount(app, block)
        await pilot.pause()
        items = block.query(".recon-item-kept")
        assert len(items) == len(KEPT)
        rendered = items.first(Static).render()
        assert _style_has(rendered, app.theme_variables["muted"])
        assert not _style_has(rendered, "strike")


@pytest.mark.asyncio
async def test_reconciliation_reverted_items_struck():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        block = ReconciliationBlock(KEPT, REVERTED, ADDED)
        await _mount(app, block)
        await pilot.pause()
        item = block.query(".recon-item-reverted").first(Static).render()
        assert _style_has(item, "strike")


@pytest.mark.asyncio
async def test_reconciliation_added_items():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        block = ReconciliationBlock(KEPT, REVERTED, ADDED)
        await _mount(app, block)
        await pilot.pause()
        items = block.query(".recon-item-added")
        assert len(items) == len(ADDED)
        assert _style_has(items.first(Static).render(), app.theme_variables["muted"])


@pytest.mark.asyncio
async def test_reconciliation_no_context():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        block = ReconciliationBlock(KEPT, [], ADDED, context="")
        await _mount(app, block)
        await pilot.pause()
        assert block.query_one(".recon-header", Static).render().plain == "⟲ redirected"


@pytest.mark.asyncio
async def test_reconciliation_grid_alignment():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        block = ReconciliationBlock(KEPT, REVERTED, ADDED)
        await _mount(app, block)
        await pilot.pause()
        assert block.styles.padding.left == 1  # container at MARGIN (col 1)
        assert block.query_one(".recon-section-kept", Static).styles.padding.left == 2  # col 3
        assert block.query(".recon-item-kept").first(Static).styles.padding.left == 4  # col 5


@pytest.mark.asyncio
async def test_reconciliation_all_empty_renders_header_only():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        block = ReconciliationBlock([], [], [], context="nothing changed")
        await _mount(app, block)
        await pilot.pause()
        # documented behavior: no ValueError — just the header, no sections
        assert len(block.query(".recon-header")) == 1
        assert len(block.query(".recon-section")) == 0
