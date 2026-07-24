"""Web Search Tool - Search the web for information."""

import json
from typing import Any

import httpx

from tools.base import BaseTool, ToolParameter, ParameterType


class WebSearchTool(BaseTool):
    """Tool for searching the web."""

    name = "web_search"
    description = "Search the web for information using DuckDuckGo"
    parameters = [
        ToolParameter(
            name="query",
            type=ParameterType.STRING,
            description="The search query",
            required=True,
        ),
        ToolParameter(
            name="max_results",
            type=ParameterType.INTEGER,
            description="Maximum number of results to return",
            required=False,
            default=5,
        ),
    ]

    async def _execute(self, query: str, max_results: int = 5) -> Any:
        """Execute web search."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Using DuckDuckGo Instant Answer API
                url = "https://api.duckduckgo.com/"
                params = {
                    "q": query,
                    "format": "json",
                    "no_html": "1",
                    "skip_disambig": "1",
                }

                response = await client.get(url, params=params)
                response.raise_for_status()

                data = response.json()

                results = []

                # Extract related topics
                for topic in data.get("RelatedTopics", [])[:max_results]:
                    if "Text" in topic and "FirstURL" in topic:
                        results.append({
                            "title": topic.get("Text", ""),
                            "url": topic.get("FirstURL", ""),
                            "snippet": topic.get("Text", ""),
                        })

                # If no related topics, try the abstract
                if not results and data.get("AbstractText"):
                    results.append({
                        "title": data.get("Heading", query),
                        "url": data.get("AbstractURL", ""),
                        "snippet": data.get("AbstractText", ""),
                    })

                return {
                    "query": query,
                    "results": results,
                    "count": len(results),
                }

        except httpx.HTTPError as e:
            return {"error": f"HTTP error: {str(e)}", "results": []}
        except Exception as e:
            return {"error": str(e), "results": []}
