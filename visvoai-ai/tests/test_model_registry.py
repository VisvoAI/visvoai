

def test_gemini_cache_read_is_ten_percent_of_input():
    """Google prices Gemini context-cache reads at 10% of the input rate
    (https://ai.google.dev/gemini-api/docs/pricing).

    Regression test with a real history: every Gemini entry carried 25% for
    months. It was uniform, which is what made it look like a deliberate
    convention rather than a bug, and a new model was added matching the wrong
    value because the rest of the table agreed with it.
    """
    from visvoai.ai.model_registry import MODELS

    wrong = []
    for m in MODELS:
        if m.provider != "gemini" or not m.input_cost_per_million:
            continue
        if not m.cache_read_cost_per_million:
            continue  # not all models publish a cache rate
        expected = round(m.input_cost_per_million * 0.10, 6)
        if abs(m.cache_read_cost_per_million - expected) > 1e-9:
            wrong.append(f"{m.api_id}: {m.cache_read_cost_per_million} (expected {expected})")
    assert not wrong, "Gemini cache_read must be 10% of input:\n  " + "\n  ".join(wrong)
