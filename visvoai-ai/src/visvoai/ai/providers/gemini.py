"""GeminiProvider — facade for Google Gemini.

Low-level build() for the LangGraph agent loop. Thinking kwargs are computed by the
top-level resolver (visvoai.ai.build_chat_model) and passed in via **extra — the
provider just constructs. Subclass to add anything beyond chat (generate/search).
"""
from .base import Provider
from .config import resolve_api_key


class GeminiProvider(Provider):
    def build(self, slug, api_key=None, base_url=None, **extra):
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=slug,
            google_api_key=resolve_api_key("gemini", api_key),
            temperature=1.0,
            streaming=True,
            **extra,
        )

    def search(self, query, *, slug, api_key=None, system=None):
        """Grounded web search via Google Search grounding. Returns a SearchResult
        with the synthesized answer + the web sources it was grounded on. Uses the
        google-genai SDK directly (the grounding metadata is cleanest there)."""
        from google import genai
        from google.genai import types

        from visvoai.ai.search import SearchResult, SearchSource

        client = genai.Client(api_key=resolve_api_key("gemini", api_key))
        config = types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            temperature=0.0,
            **({"system_instruction": system} if system else {}),
        )
        resp = client.models.generate_content(model=slug, contents=query, config=config)

        text = (getattr(resp, "text", None) or "").strip()
        sources: list[SearchSource] = []
        queries: list[str] = []
        candidates = getattr(resp, "candidates", None) or []
        if candidates:
            gm = getattr(candidates[0], "grounding_metadata", None)
            if gm is not None:
                queries = list(getattr(gm, "web_search_queries", None) or [])
                for chunk in getattr(gm, "grounding_chunks", None) or []:
                    web = getattr(chunk, "web", None)
                    if web is not None:
                        sources.append(SearchSource(
                            title=getattr(web, "title", "") or "",
                            url=getattr(web, "uri", "") or "",
                        ))
        return SearchResult(text=text, sources=sources, queries=queries)

    def fetch_url(self, url, *, slug, api_key=None):
        """Fetch a URL via Gemini URL Context (provider-side retrieval) and return it
        as clean markdown. Raises FetchError on a failed/blocked/empty retrieval."""
        from google import genai
        from google.genai import types

        from visvoai.ai.search import FetchError

        client = genai.Client(api_key=resolve_api_key("gemini", api_key))
        resp = client.models.generate_content(
            model=slug,
            contents=(
                "Read the content at this URL and return it as clean, structured "
                "markdown. Preserve headings, lists, tables, and important details. "
                f"URL: {url}"
            ),
            config=types.GenerateContentConfig(
                tools=[types.Tool(url_context=types.UrlContext())],
            ),
        )

        # Status shape varies across SDK versions — scan the metadata blob defensively.
        candidates = getattr(resp, "candidates", None) or []
        if candidates:
            meta = getattr(candidates[0], "url_context_metadata", None)
            blob = str(meta) if meta is not None else ""
            if any(k in blob for k in ("ERROR", "UNSAFE", "FAILED")):
                raise FetchError(f"could not retrieve {url} ({blob[:200]})")

        text = (getattr(resp, "text", None) or "").strip()
        if not text:
            raise FetchError(
                "the page returned no extractable text (it may be JS-rendered, "
                "paywalled, or non-HTML)")
        return text
