"""Actual run cost from the run log (sys-design "Cost reporting"): token usage of new calls, priced per model."""

# US$ per 1M tokens. shortcut: not set yet (neither doc gives GPT-6 prices); fill in from OpenAI's pricing page.
# While a model used by the run has no price, the total is None and only token counts are reported.
PRICES: dict[str, dict[str, float]] = {}
WEB_SEARCH: float | None = None  # US$ per web-search call


def run_cost(records: list[dict]) -> dict:
    """Sum over the run's new call records (cached ones add nothing), per call type and in total."""
    by_type: dict[str, dict] = {}
    total, priced = 0.0, True
    for r in records:
        if r["type"] != "call" or r["cached"]:
            continue
        u, p = r["usage"], PRICES.get(r["model"])
        t = by_type.setdefault(r["call_type"], {"calls": 0, "input_tokens": 0, "cached_tokens": 0, "output_tokens": 0,
                                                "web_search_calls": 0, "cost": 0.0, "web_search_cost": 0.0})
        web = u.get("web_search_calls", 0)
        t["calls"] += 1
        for k in ("input_tokens", "cached_tokens", "output_tokens"):
            t[k] += u[k]
        t["web_search_calls"] += web
        if p is None or (web and WEB_SEARCH is None):
            priced = False
            continue
        c = ((u["input_tokens"] - u["cached_tokens"]) * p["input"] + u["cached_tokens"] * p["cached_input"]
             + u["output_tokens"] * p["output"]) / 1e6
        t["cost"] += c + web * (WEB_SEARCH or 0)
        t["web_search_cost"] += web * (WEB_SEARCH or 0)
        total += c + web * (WEB_SEARCH or 0)
    return {"total": total if priced else None, "by_type": by_type,
            "web_search_calls": sum(t["web_search_calls"] for t in by_type.values())}
