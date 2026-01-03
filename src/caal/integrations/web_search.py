"""Web search tool with DuckDuckGo + Gemini summarization.

Provides a voice-friendly web search capability that:
1. Searches DuckDuckGo (free, no API key)
2. Summarizes results with Gemini for concise voice output
3. Returns 1-3 sentence answers instead of raw search results

Usage:
    class VoiceAssistant(WebSearchTools, Agent):
        pass  # web_search tool is automatically available
"""

import asyncio
import logging
import os
from typing import Any

import httpx
from livekit.agents import function_tool

logger = logging.getLogger(__name__)

SUMMARIZE_PROMPT = """Summarize the following search results in 1-3 sentences for voice output.
Be concise and conversational. Do not include URLs, markdown, or bullet points.
Focus on directly answering what the user would want to know.

Search query: {query}

Results:
{results}

Summary:"""


class WebSearchTools:
    """Mixin providing web search via DuckDuckGo with Gemini summarization.

    Requires the parent class to have:
    - self.llm: GeminiLLM instance (for model/base_url/api_key access)

    Configuration (override in subclass if needed):
    - _search_max_results: int = 5
    - _search_timeout: float = 10.0
    """

    _search_max_results: int = 5
    _search_timeout: float = 10.0

    @function_tool
    async def web_search(self, query: str) -> str:
        """Search the web for current events, news, prices, store hours, or any time-sensitive information not available from other tools.

        Args:
            query: What to search for on the web.
        """
        logger.info(f"web_search: {query}")

        try:
            raw_results = await asyncio.wait_for(
                self._do_search(query),
                timeout=self._search_timeout
            )

            if not raw_results:
                return "I couldn't find any results for that search."

            return await self._summarize_results(query, raw_results)

        except asyncio.TimeoutError:
            logger.warning(f"Web search timed out for query: {query}")
            return "The search took too long. Please try a simpler query."
        except Exception as e:
            logger.error(f"Web search error: {e}", exc_info=True)
            return "I had trouble searching the web. Please try again."

    async def _do_search(self, query: str) -> list[dict[str, Any]]:
        """Execute DuckDuckGo search in thread pool (blocking API).

        Returns list of result dicts with 'title', 'body', 'href' keys.
        """
        from ddgs import DDGS

        def _search():
            with DDGS(timeout=self._search_timeout) as ddgs:
                return list(ddgs.text(
                    query,
                    max_results=self._search_max_results,
                    safesearch="moderate"
                ))

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _search)

    async def _summarize_results(
        self,
        query: str,
        results: list[dict[str, Any]]
    ) -> str:
        """Summarize search results with Gemini for voice-friendly output."""

        # Truncate to avoid exceeding context limits
        formatted = []
        for i, r in enumerate(results, 1):
            title = r.get("title", "")[:100]
            body = r.get("body", "")[:200]
            formatted.append(f"{i}. {title}: {body}")

        results_text = "\n".join(formatted)
        prompt = SUMMARIZE_PROMPT.format(query=query, results=results_text)

        # Get API config from agent's LLM
        base_url = getattr(self.llm, "base_url", os.getenv("GEMINI_API_URL", "http://localhost:8888/v1"))
        api_key = getattr(self.llm, "api_key", os.getenv("GEMINI_API_KEY", "caal-secret"))
        model = getattr(self.llm, "model", os.getenv("GEMINI_MODEL", "gemini-3-flash"))

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.3,  # Low temp for factual output
                        "stream": False,
                    },
                )
                response.raise_for_status()
                data = response.json()
                
                if data.get("choices") and len(data["choices"]) > 0:
                    summary = data["choices"][0].get("message", {}).get("content", "").strip()
                    return summary or "I found some results but couldn't summarize them."
                
                return "I found some results but couldn't summarize them."

        except Exception as e:
            logger.error(f"Summarization error: {e}")
            # Fallback: return first result's snippet
            if results:
                return results[0].get("body", "No description available.")
            return "I had trouble processing the search results."
