"""MCP Tool: AWS Documentation — Search and read AWS docs."""
import json
import urllib.request
import urllib.parse
import re


def lambda_handler(event, context):
    # AgentCore Gateway: tool name in context, input as event directly
    delimiter = "___"
    try:
        original_tool_name = context.client_context.custom["bedrockAgentCoreToolName"]
        tool_name = original_tool_name[original_tool_name.index(delimiter) + len(delimiter):]
    except (AttributeError, KeyError, ValueError):
        tool_name = event.pop("toolName", event.pop("name", "search_documentation"))
    tool_input = event

    handlers = {
        "search_documentation": _search_docs,
        "read_documentation": _read_docs,
    }

    handler = handlers.get(tool_name)
    if not handler:
        return _response(f"Unknown tool: {tool_name}. Available: {list(handlers.keys())}")

    try:
        result = handler(tool_input)
        return _response(result)
    except Exception as e:
        return _response(f"Error: {str(e)}")


def _search_docs(params):
    """Search AWS documentation using the public search API."""
    query = params.get("query", params.get("search_phrase", ""))
    limit = params.get("limit", 5)

    if not query:
        return json.dumps({"error": "query parameter is required"})

    encoded = urllib.parse.quote(query)
    url = f"https://docs.aws.amazon.com/search/doc-search.html?searchQuery={encoded}&is498=true&lng=en"

    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; MCPBot/1.0)",
        "Accept": "application/json",
    })

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            items = data.get("items", [])[:limit]
            results = []
            for item in items:
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("href", ""),
                    "excerpt": _clean_html(item.get("excerpt", ""))[:200],
                    "guide": item.get("guide", ""),
                })
            return json.dumps({"results": results, "count": len(results), "query": query})
    except Exception as e:
        return json.dumps({"error": f"Search failed: {str(e)}", "query": query})


def _read_docs(params):
    """Fetch an AWS documentation page and return key content."""
    url = params.get("url", "")
    if not url:
        return json.dumps({"error": "url parameter is required"})

    if not url.startswith("https://docs.aws.amazon.com"):
        return json.dumps({"error": "Only docs.aws.amazon.com URLs are supported"})

    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; MCPBot/1.0)",
        "Accept": "text/html",
    })

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode()
            content = _extract_content(html)
            return json.dumps({"url": url, "content": content[:3000]})
    except Exception as e:
        return json.dumps({"error": f"Failed to fetch: {str(e)}", "url": url})


def _clean_html(text):
    """Remove HTML tags."""
    return re.sub(r'<[^>]+>', '', text).strip()


def _extract_content(html):
    """Extract main text content from AWS docs HTML."""
    match = re.search(r'<div id="main-col-body">(.*?)</div>\s*<div', html, re.DOTALL)
    if not match:
        match = re.search(r'<main[^>]*>(.*?)</main>', html, re.DOTALL)
    if match:
        content = match.group(1)
    else:
        content = html

    content = re.sub(r'<(script|style|nav)[^>]*>.*?</\1>', '', content, flags=re.DOTALL)
    content = re.sub(r'<br\s*/?>', '\n', content)
    content = re.sub(r'</(p|h[1-6]|li|div)>', '\n', content)
    content = _clean_html(content)
    content = re.sub(r'\n{3,}', '\n\n', content)
    return content.strip()


def _response(content):
    return {"content": [{"text": content if isinstance(content, str) else json.dumps(content, default=str)}]}
