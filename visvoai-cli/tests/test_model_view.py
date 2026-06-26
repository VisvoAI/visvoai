"""ModelScreen — grouped connected-first list + thinking-level chooser."""
from __future__ import annotations

import pytest

from textual.widgets import OptionList

from visvoai.cli import VisvoApp
from visvoai.cli.agent import DeployView
from visvoai.cli.screens.model_view import ModelScreen, ThinkChip


def _row_ids(screen) -> list[str]:
    """Selectable option ids in display order (skips disabled group headers)."""
    ol = screen.query_one("#model-list", OptionList)
    return [ol.get_option_at_index(i).id for i in range(ol.option_count)
            if ol.get_option_at_index(i).id is not None]


def _highlight(screen, dep_id: str) -> None:
    ol = screen.query_one("#model-list", OptionList)
    for i in range(ol.option_count):
        if ol.get_option_at_index(i).id == dep_id:
            ol.highlighted = i
            return
    raise AssertionError(f"{dep_id} not in the list")


def _dv(id, name, provider, connected, thinking=("off", "low", "medium", "high"),
        default="medium", ic=0.3, oc=2.5, ctx=1_048_576):
    return DeployView(
        id=id, display_name=name, provider=provider, family=provider,
        in_cost=ic, out_cost=oc, supports_thinking=len(thinking) > 1,
        thinking_levels=list(thinking), default_thinking=default,
        context_window=ctx, connected=connected,
    )


async def _push(app, pilot, screen, on_result):
    app.push_screen(screen, on_result)
    for _ in range(40):
        await pilot.pause()
        if isinstance(app.screen, ModelScreen):
            return app.screen
    raise AssertionError("model screen never opened")


@pytest.mark.asyncio
async def test_connected_first_then_locked():
    deps = [
        _dv("openai:gpt", "GPT", "openai", connected=False),
        _dv("gemini:f", "Flash", "gemini", connected=True),
        _dv("anthropic:s", "Sonnet", "anthropic", connected=True),
    ]
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _push(app, pilot, ModelScreen(deps, current_id="gemini:f"), lambda r: None)
        # connected (sorted by provider) come first, locked last — all selectable.
        assert _row_ids(screen) == ["anthropic:s", "gemini:f", "openai:gpt"]
        # opens highlighted on the current model
        ol = screen.query_one("#model-list", OptionList)
        assert ol.get_option_at_index(ol.highlighted).id == "gemini:f"


@pytest.mark.asyncio
async def test_search_filters_rows():
    deps = [
        _dv("gemini:f", "Flash", "gemini", connected=True),
        _dv("openrouter:grok", "Grok 3", "openrouter", connected=True),
        _dv("together:llama", "Llama 3.3", "together", connected=True),
    ]
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _push(app, pilot, ModelScreen(deps), lambda r: None)
        screen.query_one("#model-search").value = "grok"
        await pilot.pause()
        assert _row_ids(screen) == ["openrouter:grok"]
        # provider name also matches
        screen.query_one("#model-search").value = "together"
        await pilot.pause()
        assert _row_ids(screen) == ["together:llama"]


@pytest.mark.asyncio
async def test_sort_cycle_reorders_within_provider():
    deps = [
        _dv("together:a", "Alpha", "together", connected=True, ic=5.0),
        _dv("together:b", "Beta", "together", connected=True, ic=1.0),
    ]
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _push(app, pilot, ModelScreen(deps), lambda r: None)
        assert _row_ids(screen) == ["together:a", "together:b"]   # name order
        screen.action_cycle_sort()                                # name → cost
        await pilot.pause()
        assert screen._sort == "cost"
        assert _row_ids(screen) == ["together:b", "together:a"]   # cheapest first


@pytest.mark.asyncio
async def test_thinking_only_and_connected_only_filters():
    deps = [
        _dv("gemini:f", "Flash", "gemini", connected=True),                       # thinks, connected
        _dv("together:ll", "Llama", "together", connected=True, thinking=("off",)),  # no thinking
        _dv("openai:gpt", "GPT", "openai", connected=False),                      # locked
    ]
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _push(app, pilot, ModelScreen(deps), lambda r: None)
        assert set(_row_ids(screen)) == {"gemini:f", "together:ll", "openai:gpt"}
        screen.action_toggle_thinking()          # only thinking-capable (Llama has none)
        await pilot.pause()
        assert set(_row_ids(screen)) == {"gemini:f", "openai:gpt"}
        screen.action_toggle_thinking()          # back to all
        await pilot.pause()
        screen.action_toggle_connected()         # hide locked providers
        await pilot.pause()
        assert "openai:gpt" not in _row_ids(screen)


@pytest.mark.asyncio
async def test_pick_thinking_model_returns_id_and_level():
    deps = [_dv("gemini:f", "Flash", "gemini", connected=True)]
    app = VisvoApp()
    result = {}
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _push(app, pilot, ModelScreen(deps, current_id="gemini:f", current_level="medium"),
                             lambda r: result.update(r=r))
        await screen.action_confirm()          # → thinking phase (model has 4 levels)
        await pilot.pause()
        assert screen._phase == "think"
        assert [c.level for c in screen.query(ThinkChip)] == ["off", "low", "medium", "high"]
        screen.action_think_next()              # medium → high (sync action)
        await screen.action_confirm()
        await pilot.pause()
        assert result["r"] == ("gemini:f", "high")


@pytest.mark.asyncio
async def test_clicking_think_chip_selects_and_confirms():
    deps = [_dv("gemini:f", "Flash", "gemini", connected=True)]
    app = VisvoApp()
    result = {}
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _push(app, pilot, ModelScreen(deps), lambda r: result.update(r=r))
        await screen.action_confirm()           # → thinking chooser
        await pilot.pause()
        chips = list(screen.query(ThinkChip))
        high = next(c for c in chips if c.level == "high")
        high.on_click()                          # click the 'high' chip
        await pilot.pause()
        assert result["r"] == ("gemini:f", "high")


def test_provider_label_capitalizes():
    from visvoai.cli.screens.model_view import _provider_label
    assert _provider_label("gemini") == "Gemini"
    assert _provider_label("openai") == "OpenAI"
    assert _provider_label("openrouter") == "OpenRouter"


@pytest.mark.asyncio
async def test_single_level_model_dismisses_immediately():
    deps = [_dv("img:x", "Imagen", "gemini", connected=True, thinking=("off",), default="off")]
    app = VisvoApp()
    result = {}
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _push(app, pilot, ModelScreen(deps), lambda r: result.update(r=r))
        await screen.action_confirm()           # no real thinking choice → straight to result
        await pilot.pause()
        assert result["r"] == ("img:x", "off")
        assert not isinstance(app.screen, ModelScreen)


@pytest.mark.asyncio
async def test_esc_from_thinking_returns_to_list():
    deps = [_dv("gemini:f", "Flash", "gemini", connected=True)]
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _push(app, pilot, ModelScreen(deps), lambda r: None)
        await screen.action_confirm()           # → thinking
        await pilot.pause()
        assert screen._phase == "think"
        screen.action_back()                    # esc → back to model list
        await pilot.pause()
        assert screen._phase == "model"
        assert isinstance(app.screen, ModelScreen)   # still open, not cancelled
