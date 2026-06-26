"""ModelScreen — grouped connected-first list + thinking-level chooser."""
from __future__ import annotations

import pytest

from visvoai.cli import VisvoApp
from visvoai.cli.agent import DeployView
from visvoai.cli.screens.model_view import ModelScreen, ModelRow, ThinkChip


def _dv(id, name, provider, connected, thinking=("off", "low", "medium", "high"), default="medium"):
    return DeployView(
        id=id, display_name=name, provider=provider, family=provider,
        in_cost=0.3, out_cost=2.5, supports_thinking=len(thinking) > 1,
        thinking_levels=list(thinking), default_thinking=default,
        context_window=1_048_576, connected=connected,
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
        assert [d.connected for d in screen._selectable] == [True, True, False]
        assert [d.id for d in screen._selectable] == ["anthropic:s", "gemini:f", "openai:gpt"]
        assert len(screen.query(ModelRow)) == 3


@pytest.mark.asyncio
async def test_pick_thinking_model_returns_id_and_level():
    deps = [_dv("gemini:f", "Flash", "gemini", connected=True)]
    app = VisvoApp()
    result = {}
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _push(app, pilot, ModelScreen(deps, current_id="gemini:f", current_level="medium"),
                             lambda r: result.update(r=r))
        screen._idx = 0
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
        screen._idx = 0
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
        screen._idx = 0
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
        screen._idx = 0
        await screen.action_confirm()           # → thinking
        await pilot.pause()
        assert screen._phase == "think"
        screen.action_back()                    # esc → back to model list
        await pilot.pause()
        assert screen._phase == "model"
        assert isinstance(app.screen, ModelScreen)   # still open, not cancelled
