"""Web tools: web_search (grounded answer + sources) and web_fetch (one URL → markdown).

Both delegate to the public visvoai-ai grounding seam (run_search / fetch_url) so
the provider SDK stays in one package — this module never imports a vendor SDK.
Errors are returned as ERROR: … data so the agent recovers.
"""
from langchain_core.tools import tool

from visvoai.cli.tools._common import cap_lines

WEB_LINE_CAP = 500       # max lines from web_search / web_fetch (prose, not a file)

# Keeps the grounded answer tight + sourced — the model synthesizes from the search
# snippets, not from its own priors.
_SEARCH_SYNTHESIS = (
    "You are an expert web researcher. Answer the query concisely and factually, "
    "based only on the live search results. If the answer isn't found, say so plainly."
)


@tool
def web_search(query: str) -> str:
    """Search the public web and return a synthesized, cited answer.

    Reach for this when the answer depends on CURRENT, CHANGING, or EXTERNAL
    information you don't already have: recent events, today's data, specific
    people/companies/products, or web documentation. The tool runs the search and
    returns prose with a numbered Sources list — you describe what to find, it picks
    the queries. If you can already answer reliably from your own knowledge, do that
    instead. To read one specific page you already have a URL for, use web_fetch.
    """
    from visvoai.ai import run_search
    from visvoai.ai.providers.base import NotSupported

    try:
        result = run_search(query, system=_SEARCH_SYNTHESIS)
    except NotSupported:
        return "ERROR: web search is not available for the configured provider."
    except KeyError:
        return "ERROR: GEMINI_API_KEY is not configured — web search needs it."
    except Exception as e:  # network / SDK / quota — report as data so the agent recovers
        return f"ERROR: {e}"

    if not result.text:
        return f"No results found for '{query}'."
    out = [result.text]
    if result.sources:
        out.append("\nSources:")
        for i, s in enumerate(result.sources, 1):
            out.append(f"[{i}] {s.title or s.url} — {s.url}")
    return cap_lines("\n".join(out), WEB_LINE_CAP)


@tool
def web_fetch(url: str) -> str:
    """Fetch and read one specific web page you already have the URL for, as clean
    markdown. Use it to open a link the user pasted, read a full article, or pull a
    known page's content for close reading. You supply the exact URL — this does not
    search. Paywalled/login-only/JS-rendered/local pages may return nothing; if so,
    try web_search. (Retrieval is done by the model provider, not this machine.)
    """
    from visvoai.ai import FetchError, fetch_url as _fetch_url
    from visvoai.ai.providers.base import NotSupported

    try:
        content = _fetch_url(url)
    except NotSupported:
        return "ERROR: URL fetch is not available for the configured provider."
    except KeyError:
        return "ERROR: GEMINI_API_KEY is not configured — web_fetch needs it."
    except FetchError as e:
        return f"ERROR: {e}. Try web_search instead."
    except Exception as e:  # network / SDK / quota — report as data so the agent recovers
        return f"ERROR: {e}"
    return cap_lines(content, WEB_LINE_CAP)
