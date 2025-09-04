import asyncio
import json
import os
import sys
from typing import Any, Iterable

from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters

SERVER_PATH = os.path.join(os.path.dirname(__file__), "server.py")

def as_dict(obj: Any) -> dict:
    """Return a JSON-serializable dict view of obj (model or dict)."""
    if isinstance(obj, dict):
        return obj
    # Try common model conversions
    for attr in ("model_dump", "dict", "to_dict"):
        fn = getattr(obj, attr, None)
        if callable(fn):
            try:
                return fn()
            except Exception:
                pass
    # Fallback: best-effort attr scrape
    out = {}
    for k in dir(obj):
        if k.startswith("_"):
            continue
        try:
            v = getattr(obj, k)
        except Exception:
            continue
        if callable(v):
            continue
        out[k] = v
    return out

def get_field(obj: Any, *names: str):
    """Get first existing attribute/key among names from dict/model."""
    if isinstance(obj, dict):
        for n in names:
            if n in obj:
                return obj[n]
        return None
    for n in names:
        if hasattr(obj, n):
            return getattr(obj, n)
    # Also try dict-view on models
    d = as_dict(obj)
    for n in names:
        if n in d:
            return d[n]
    return None

def iter_contents(result: Any):
    # Prefer structuredContent if available
    sc = get_field(result, "structuredContent")
    if sc:
        return get_field(sc, "content") or []
    return get_field(result, "content", "contents") or []


def extract_texts(result: Any):
    texts = []
    for c in iter_contents(result):
        t = get_field(c, "type")
        if t == "text":
            texts.append(get_field(c, "text"))
        # Some SDKs flatten text differently
        elif hasattr(c, "text"):
            texts.append(getattr(c, "text"))
    return texts

def extract_jsons(result: Any):
    jsons = []
    for c in iter_contents(result):
        t = get_field(c, "type")
        if t == "json":
            j = get_field(c, "json", "data", "value")
            if j is not None:
                jsons.append(j)
        # Fallbacks: some transports use MIME-style parts
        if t in ("application/json", "json"):
            j = get_field(c, "json", "data", "value")
            if j is not None:
                jsons.append(j)
    return jsons

async def main():
    params = StdioServerParameters(
        command=sys.executable,
        args=[SERVER_PATH],
        env=os.environ.copy(),
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools_resp = await session.list_tools()
            # Print tool names compatibly
            tools = getattr(tools_resp, "tools", None) or as_dict(tools_resp).get("tools", [])
            tool_names = [
                (getattr(t, "name", None) or (t.get("name") if isinstance(t, dict) else None))
                for t in tools
            ]
            print("Tools:", tool_names)

            # --- echo ---
            echo_res = await session.call_tool("echo", {"text": "Hello, world!"})
            print("RAW echo result:")
            print(json.dumps(as_dict(echo_res), indent=2))
            echo_texts = extract_texts(echo_res)
            print("echo (text):", echo_texts[0] if echo_texts else "<no text>")

            # --- add_numbers ---
            add_res = await session.call_tool("add_numbers", {"numbers": [1, 2, 3.5]})
            print("RAW add_numbers result:")
            print(json.dumps(as_dict(add_res), indent=2))
            add_jsons = extract_jsons(add_res)
            print("add_numbers (json):", add_jsons[0] if add_jsons else "<no json>")

            # --- now ---
            now_res = await session.call_tool("now", {"timezone": "Asia/Kolkata"})
            print("RAW now result:")
            print(json.dumps(as_dict(now_res), indent=2))
            now_jsons = extract_jsons(now_res)
            print("now (json):", now_jsons[0] if now_jsons else "<no json>")

            # --- word_count ---
            wc_res = await session.call_tool("word_count", {"text": "Hello from MCP world"})
            print("RAW word_count result:")
            print(json.dumps(as_dict(wc_res), indent=2))
            wc_jsons = extract_jsons(wc_res)
            print("word_count (json):", wc_jsons[0] if wc_jsons else "<no json>")


if __name__ == "__main__":
    asyncio.run(main())