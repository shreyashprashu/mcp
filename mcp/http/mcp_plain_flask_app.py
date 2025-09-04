# filename: mcp_plain_flask_app.py
import logging
import json
import asyncio
from typing import Any, Dict, Optional
from datetime import datetime

from flask import Flask, request, jsonify, make_response

from dateutil import tz
import pytz

from mcp.server.lowlevel import Server, NotificationOptions
from mcp.types import Tool

# ------------------------------------------------------------------------------
# Logging setup
# ------------------------------------------------------------------------------
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger("mcp-tools-py")

# ------------------------------------------------------------------------------
# MCP server
# ------------------------------------------------------------------------------
server = Server(name="mcp-tools-py", version="0.2.0")

# Define tools
@server.list_tools()
async def list_tools():
    log.debug("Listing tools")
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


@server.call_tool()
async def call_tool(name: str, arguments: Optional[Dict[str, Any]]):
    args = arguments or {}
    log.debug("Calling tool %s with args=%s", name, args)
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
        return {"content": [{"type": "text", "text": iso}, {"type": "json", "json": {"iso": iso}}]}

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

# ------------------------------------------------------------------------------
# Flask app (with manual CORS)
# ------------------------------------------------------------------------------
app = Flask(__name__)

# Manual CORS: add headers to every response
@app.after_request
def add_cors_headers(response):
    # Adjust origins/methods/headers as needed
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, Mcp-Session-Id"
    response.headers["Access-Control-Expose-Headers"] = "Mcp-Session-Id"
    return response

# Handle preflight OPTIONS requests globally
@app.before_request
def handle_preflight():
    if request.method == "OPTIONS":
        resp = make_response("", 204)
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, Mcp-Session-Id"
        resp.headers["Access-Control-Expose-Headers"] = "Mcp-Session-Id"
        return resp

# Helpers for JSON-RPC responses
def _jsonrpc_result(result, request_id):
    return {"jsonrpc": "2.0", "result": result, "id": request_id}

def _jsonrpc_error(code, message, request_id=None):
    return {"jsonrpc": "2.0", "error": {"code": code, "message": message}, "id": request_id}

# Health check
@app.route("/health", methods=["GET"])
def health():
    log.debug("Health check requested")
    return jsonify({"status": "healthy"})

# MCP JSON-RPC endpoint
@app.route("/mcp", methods=["POST"])
def mcp_endpoint():
    try:
        body = request.get_json(force=True, silent=False)
        log.debug("Received request: %s", body)
        if not isinstance(body, dict):
            return jsonify(_jsonrpc_error(-32600, "Invalid Request: expected JSON object.", None)), 400

        method = body.get("method")
        params = body.get("params", {}) or {}
        request_id = body.get("id")

        if method == "initialize":
            log.debug("Handling initialize")
            result = {
                "serverInfo": {"name": server.name, "version": server.version},
                "capabilities": server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={}
                ),
            }
            return jsonify(_jsonrpc_result(result, request_id))

        elif method == "listTools":
            log.debug("Handling listTools")
            tools = asyncio.run(list_tools())
            serialized_tools = [
                {"name": t.name, "description": t.description, "inputSchema": t.inputSchema}
                for t in tools
            ]
            return jsonify(_jsonrpc_result({"tools": serialized_tools}, request_id))

        elif method == "callTool":
            log.debug("Handling callTool: %s", params)
            tool_name = params.get("toolName")
            arguments = params.get("arguments", {}) or {}
            result = asyncio.run(call_tool(tool_name, arguments))
            log.debug("Tool result: %s", result)
            return jsonify(_jsonrpc_result(result, request_id))

        else:
            log.warning("Unknown method: %s", method)
            return jsonify(_jsonrpc_error(-32601, f"Method not found: {method}", request_id)), 400

    except json.JSONDecodeError as e:
        log.error("JSON decode error: %s", e)
        return jsonify(_jsonrpc_error(-32700, f"Parse error: {str(e)}")), 400
    except Exception as e:
        log.error("Error processing request: %s", e, exc_info=True)
        req_id = None
        try:
            req_id = body.get("id") if isinstance(body, dict) else None
        except Exception:
            pass
        return jsonify(_jsonrpc_error(-32000, str(e), req_id)), 500

# ------------------------------------------------------------------------------
# Run (dev server)
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    # No external CORS package is required.
    # Install deps:
    #   pip install flask python-dateutil pytz mcp
    #
    # Start:
    #   python mcp_plain_flask_app.py
    #
    # Test:
    #   curl -X POST http://localhost:8080/mcp \
    #     -H "Content-Type: application/json" \
    #     -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}'
    app.run(host="0.0.0.0", port=8080, debug=True)
