"""Wave-1 new widgets: StructureTree (F), FileCreation (F), Citation (G)."""
from __future__ import annotations

import pytest

from visvoai.cli import VisvoApp
from visvoai.cli.widgets import Citation, FileCreation, StructureTree
from visvoai.cli.widgets.output import OutputLine, ShowMore
from visvoai.cli.widgets.structure_tree import TreeRow

LAYOUT = {
    "app": {
        "main.py": None,
        "models": {"order.py": None},
        "db.py": None,
    },
    "tests": {"test_orders.py": None},
    "pyproject.toml": None,
}


# ── StructureTree ────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_structure_tree_flattens_all_nodes():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        t = StructureTree(LAYOUT)
        await app.query_one("#log").mount(t)
        await pilot.pause()
        rows = t.query(TreeRow)
        names = [r.node_name for r in rows]
        assert names == ["app", "main.py", "models", "order.py", "db.py",
                         "tests", "test_orders.py", "pyproject.toml"]
        # directories carry the .dir class; files don't
        app_row = next(r for r in rows if r.node_name == "app")
        assert app_row.is_dir and app_row.has_class("dir")
        assert app_row.path == "app"
        order = next(r for r in rows if r.node_name == "order.py")
        assert order.path == "app/models/order.py"


@pytest.mark.asyncio
async def test_structure_tree_collapse_hides_descendants():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        t = StructureTree(LAYOUT)
        await app.query_one("#log").mount(t)
        await pilot.pause()
        app_row = next(r for r in t.query(TreeRow) if r.node_name == "app")
        app_row.on_click()        # collapse "app"
        await pilot.pause()
        hidden = {r.node_name for r in t.query(TreeRow) if not r.display}
        assert {"main.py", "models", "order.py", "db.py"} <= hidden
        # siblings outside app stay visible
        assert next(r for r in t.query(TreeRow) if r.node_name == "tests").display
        app_row.on_click()        # expand again
        await pilot.pause()
        assert all(r.display for r in t.query(TreeRow))


# ── FileCreation ─────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_file_creation_summary_and_collapsed_body():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        content = "line1\nline2\nline3"
        fc = FileCreation("app/main.py", content)
        await app.query_one("#log").mount(fc)
        await pilot.pause()
        assert fc.row.status == "complete"       # creation already done
        assert "app/main.py" in str(fc.row.render())
        assert "3 lines" in str(fc.row.render())   # the rail count
        assert fc.line_count == 3
        # body present but collapsed (one click away)
        assert fc._body is not None
        assert fc._body.display is False


# ── Citation ─────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_citation_renders_source_and_quoted_excerpt():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        c = Citation(
            "SQLAlchemy 2.0 migration guide",
            "Query.get() is deprecated.\nUse Session.get() instead.",
            url="docs.sqlalchemy.org/20/migration",
        )
        await app.query_one("#log").mount(c)
        await pilot.pause()
        out = str(c.render())
        assert "≡" in out
        assert "SQLAlchemy 2.0 migration guide" in out
        assert "docs.sqlalchemy.org" in out
        assert "▍" in out                         # per-line quote tick (no cross-line glyph)
        assert "Use Session.get() instead." in out
