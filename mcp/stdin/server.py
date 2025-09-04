
import asyncio
import logging
from typing import Any, Dict, Optional
from datetime import datetime

from dateutil import tz
import pytz

from mcp.server.stdio import stdio_server
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from mcp.types import Tool  # IMPORTANT: use the model class here

# ---- Logging to STDERR (never stdout) ---------------------------------------
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("mcp-tools-py")

# ---- Server -----------------------------------------------------------------
server = Server(name="mcp-tools-py", version="0.2.0")

# ---- Tool catalog -----------------------------------------------------------
@server.list_tools()
async def list_tools():
    log.info("Listing tools")
    # RETURN Tool MODEL INSTANCES (not dicts); use camelCase inputSchema
    return [
        Tool(
            name="echo",
            description="Echo back the provided text.",
            inputSchema={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        ),
        Tool(
            name="add_numbers",
            description="Return the sum of a list of numbers.",
            inputSchema={
                "type": "object",
                "properties": {
                    "numbers": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 1,
                    }
                },
                "required": ["numbers"],
            },
        ),
        Tool(
            name="now",
            description="Return the current datetime in ISO 8601. Optionally pass a timezone like 'UTC' or 'Asia/Kolkata'.",
            inputSchema={
                "type": "object",
                "properties": {"timezone": {"type": "string"}},
            },
        ),
        Tool(
            name="word_count",
            description="Count words and characters in the given text.",
            inputSchema={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        ),
    ]

# ---- Tool handler -----------------------------------------------------------
@server.call_tool()
async def call_tool(name: str, arguments: Optional[Dict[str, Any]]):
    args = arguments or {}
    log.info("call_tool %s args=%s", name, args)

    if name == "echo":
        text = str(args.get("text", ""))
        return {"content": [{"type": "text", "text": text}]}

    if name == "add_numbers":
        nums = args.get("numbers")
        if not isinstance(nums, list) or not nums:
            raise ValueError("numbers must be a non-empty array")
        try:
            s = sum(float(n) for n in nums)
        except Exception:
            raise ValueError("numbers must contain only numeric values")
        return {
            "content": [
                {"type": "text", "text": f"sum = {s}"},
                {"type": "json", "json": {"sum": s}},
            ]
        }

    if name == "now":
        tzname = args.get("timezone")
        if tzname:
            try:
                zone = pytz.timezone(str(tzname))
                dt = datetime.now(zone)
            except Exception as e:
                log.warning("Timezone error: %s; falling back to local", e)
                dt = datetime.now(tz.tzlocal())
        else:
            dt = datetime.now(tz.tzlocal())
        iso = dt.isoformat()
        return {
            "content": [
                {"type": "text", "text": iso},
                {"type": "json", "json": {"iso": iso}},
            ]
        }

    if name == "word_count":
        text = str(args.get("text", ""))
        words = [w for w in text.split() if w]
        res = {"words": len(words), "characters": len(text)}
        return {
            "content": [
                {"type": "text", "text": f"words={res['words']} chars={res['characters']}"},
                {"type": "json", "json": res},
            ]
        }

    raise ValueError(f"Unknown tool: {name}")

# ---- Boot -------------------------------------------------------------------
async def main():
    log.info("Starting MCP Tools Server (stdio)")
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name=server.name,
                server_version=server.version,
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )
    log.info("Server stopped gracefully")

if __name__ == "__main__":
    asyncio.run(main())
