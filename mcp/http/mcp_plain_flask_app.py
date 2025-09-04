# filename: mcp_flask_fs_server.py
import logging
import json
import asyncio
from typing import Any, Dict, Optional, List
from datetime import datetime
import os
import mimetypes
import base64
from pathlib import Path
from dataclasses import asdict

from flask import Flask, request, jsonify, make_response
from dateutil import tz
import pytz

# If you have the official MCP python package installed, you can keep these imports;
# otherwise, we keep a tiny shim below so the file runs even without it.
try:
    from mcp.server.lowlevel import Server, NotificationOptions
    from mcp.types import Tool
except Exception:  # lightweight fallback to run without the SDK present
    class Tool:
        def __init__(self, name: str, description: str, inputSchema: dict, outputSchema: Optional[dict] = None):
            self.name = name
            self.description = description
            self.inputSchema = inputSchema
            self.outputSchema = outputSchema

    class Server:
        def __init__(self, name: str, version: str):
            self.name = name
            self.version = version

        def get_capabilities(self, notification_options=None, experimental_capabilities=None):
            return {
                "tools": {"listChanged": False},
                "resources": {"subscribe": False, "listChanged": False},
            }

        # Decorator shims
        def list_tools(self):
            def deco(fn): return fn
            return deco

        def call_tool(self):
            def deco(fn): return fn
            return deco

    class NotificationOptions:
        pass

# ------------------------------------------------------------------------------
# Logging setup
# ------------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger("mcp-fs-server")

# ------------------------------------------------------------------------------
# Configuration: sandbox root
# ------------------------------------------------------------------------------
BASE_DIR = Path("/home/dell/mcp-sandbox/")
BASE_DIR.mkdir(parents=True, exist_ok=True)
log.info("MCP filesystem sandbox root: %s", BASE_DIR)

# ------------------------------------------------------------------------------
# MCP server (metadata only; we’re serving JSON-RPC over Flask)
# ------------------------------------------------------------------------------
server = Server(name="mcp-fs-server", version="0.2.0")

# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------
def jsonrpc_result(result, request_id):
    return {"jsonrpc": "2.0", "result": result, "id": request_id}

def jsonrpc_error(code, message, request_id=None):
    return {"jsonrpc": "2.0", "error": {"code": code, "message": message}, "id": request_id}

def safe_join_under_base(user_path: str) -> Path:
    """
    Resolve a user path (absolute or relative) into a Path under BASE_DIR.
    Reject traversal/hops outside the sandbox.
    """
    p = Path(user_path)
    if p.is_absolute():
        # Treat absolute as BASE_RELATIVE absolute (strip leading '/')
        p = Path(p.as_posix().lstrip("/"))
    full = (BASE_DIR / p).resolve()
    if BASE_DIR not in full.parents and full != BASE_DIR:
        raise PermissionError("Path outside sandbox")
    return full

def path_to_file_uri(p: Path) -> str:
    return f"file://{p.as_posix()}"

def is_texty(mime: Optional[str], path: Path) -> bool:
    if mime and mime.startswith("text/"):
        return True
    return path.suffix.lower() in {".md", ".txt", ".py", ".json", ".csv", ".yaml", ".yml", ".toml", ".ini", ".log"}

# ------------------------------------------------------------------------------
# Define TOOLS (MCP tools/*) — includes file ops
# ------------------------------------------------------------------------------
@server.list_tools()
async def list_tools():
    return [
        # ---- Your original examples ----
        Tool(
            name="echo",
            description="Echo back the provided text.",
            inputSchema={"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
            outputSchema={"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
        ),
        Tool(
            name="add_numbers",
            description="Return the sum of a list of numbers.",
            inputSchema={
                "type": "object",
                "properties": {"numbers": {"type": "array", "items": {"type": "number"}, "minItems": 1}},
                "required": ["numbers"],
            },
            outputSchema={"type": "object", "properties": {"sum": {"type": "number"}}, "required": ["sum"]},
        ),
        Tool(
            name="now",
            description="Return the current datetime in ISO 8601. Optionally pass a timezone like 'UTC' or 'Asia/Kolkata'.",
            inputSchema={"type": "object", "properties": {"timezone": {"type": "string"}}},
            outputSchema={"type": "object", "properties": {"iso": {"type": "string"}}, "required": ["iso"]},
        ),
        Tool(
            name="word_count",
            description="Count words and characters in the given text.",
            inputSchema={"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
            outputSchema={
                "type": "object",
                "properties": {"words": {"type": "integer"}, "characters": {"type": "integer"}},
                "required": ["words", "characters"],
            },
        ),

        # ---- Filesystem tools (read/write) ----
        Tool(
            name="read_file",
            description="Read a file under the sandbox root. Returns text (utf-8) or base64 blob.",
            inputSchema={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
            outputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "mimeType": {"type": "string"},
                    "text": {"type": "string"},
                    "blob_b64": {"type": "string"},
                },
                "required": ["path", "mimeType"],
            },
        ),
        Tool(
            name="write_file",
            description="Create or overwrite a file with UTF-8 text content.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "text": {"type": "string"},
                    "make_parents": {"type": "boolean"},
                },
                "required": ["path", "text"],
            },
            outputSchema={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
        ),
        Tool(
            name="append_file",
            description="Append UTF-8 text to an existing (or new) file.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "text": {"type": "string"},
                    "make_parents": {"type": "boolean"},
                },
                "required": ["path", "text"],
            },
            outputSchema={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
        ),
        Tool(
            name="list_dir",
            description="List entries (files/dirs) under a directory path.",
            inputSchema={
                "type": "object",
                "properties": {"path": {"type": "string"}, "recursive": {"type": "boolean"}},
                "required": ["path"],
            },
            outputSchema={
                "type": "object",
                "properties": {
                    "entries": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "is_dir": {"type": "boolean"},
                                "size": {"type": "integer"},
                                "uri": {"type": "string"},
                            },
                            "required": ["name", "is_dir", "uri"],
                        },
                    }
                },
                "required": ["entries"],
            },
        ),
        Tool(
            name="make_dirs",
            description="Create a directory (and parents). No-op if it already exists.",
            inputSchema={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
            outputSchema={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
        ),
        Tool(
            name="move_path",
            description="Move/rename a file or directory.",
            inputSchema={
                "type": "object",
                "properties": {"src": {"type": "string"}, "dst": {"type": "string"}, "make_parents": {"type": "boolean"}},
                "required": ["src", "dst"],
            },
            outputSchema={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
        ),
        Tool(
            name="delete_path",
            description="Delete a file or an empty directory. Set confirm=true to proceed.",
            inputSchema={
                "type": "object",
                "properties": {"path": {"type": "string"}, "confirm": {"type": "boolean"}},
                "required": ["path", "confirm"],
            },
            outputSchema={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
        ),
    ]

@server.call_tool()
async def call_tool(name: str, arguments: Optional[Dict[str, Any]]):
    args = arguments or {}
    log.debug("call_tool %s args=%s", name, args)

    # ---- Your originals ----
    if name == "echo":
        text = str(args.get("text", ""))
        return {
            "content": [
                {"type": "text", "text": text},
                {"type": "json", "json": {"text": text}},
            ]
        }

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

    # ---- Filesystem tools ----
    if name == "read_file":
        path = safe_join_under_base(args.get("path", ""))
        if not path.exists() or not path.is_file():
            raise FileNotFoundError("File not found")
        mime, _ = mimetypes.guess_type(str(path))
        if is_texty(mime, path):
            text = path.read_text(encoding="utf-8", errors="replace")
            payload = {"path": str(path.relative_to(BASE_DIR)), "mimeType": mime or "text/plain", "text": text}
        else:
            blob_b64 = base64.b64encode(path.read_bytes()).decode("ascii")
            payload = {"path": str(path.relative_to(BASE_DIR)), "mimeType": mime or "application/octet-stream", "blob_b64": blob_b64}
        return {"content": [{"type": "json", "json": payload}]}

    if name == "write_file":
        path = safe_join_under_base(args.get("path", ""))
        text = args.get("text", "")
        make_parents = bool(args.get("make_parents"))
        if make_parents:
            path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return {"content": [{"type": "json", "json": {"ok": True}}]}

    if name == "append_file":
        path = safe_join_under_base(args.get("path", ""))
        text = args.get("text", "")
        make_parents = bool(args.get("make_parents"))
        if make_parents:
            path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(text)
        return {"content": [{"type": "json", "json": {"ok": True}}]}

    if name == "list_dir":
        path = safe_join_under_base(args.get("path", ""))
        recursive = bool(args.get("recursive"))
        if not path.exists() or not path.is_dir():
            raise NotADirectoryError("Directory not found")
        entries: List[Dict[str, Any]] = []
        if recursive:
            it = path.rglob("*")
        else:
            it = path.iterdir()
        for p in it:
            try:
                st = p.stat()
            except Exception:
                continue
            entries.append({
                "name": str(p.relative_to(path)),
                "is_dir": p.is_dir(),
                "size": 0 if p.is_dir() else int(getattr(st, "st_size", 0)),
                "uri": path_to_file_uri(p),
            })
        return {"content": [{"type": "json", "json": {"entries": entries}}]}

    if name == "make_dirs":
        path = safe_join_under_base(args.get("path", ""))
        path.mkdir(parents=True, exist_ok=True)
        return {"content": [{"type": "json", "json": {"ok": True}}]}

    if name == "move_path":
        src = safe_join_under_base(args.get("src", ""))
        dst = safe_join_under_base(args.get("dst", ""))
        make_parents = bool(args.get("make_parents"))
        if make_parents:
            dst.parent.mkdir(parents=True, exist_ok=True)
        if not src.exists():
            raise FileNotFoundError("Source not found")
        src.replace(dst)
        return {"content": [{"type": "json", "json": {"ok": True}}]}

    if name == "delete_path":
        path = safe_join_under_base(args.get("path", ""))
        confirm = bool(args.get("confirm"))
        if not confirm:
            raise ValueError("Refusing to delete without confirm=true")
        if not path.exists():
            return {"content": [{"type": "json", "json": {"ok": True}}]}
        if path.is_dir():
            # only delete empty dirs for safety
            try:
                path.rmdir()
            except OSError:
                raise OSError("Directory not empty")
        else:
            path.unlink()
        return {"content": [{"type": "json", "json": {"ok": True}}]}

    raise ValueError(f"Unknown tool: {name}")

# ------------------------------------------------------------------------------
# Flask app (with manual CORS)
# ------------------------------------------------------------------------------
app = Flask(__name__)

@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, Mcp-Session-Id"
    response.headers["Access-Control-Expose-Headers"] = "Mcp-Session-Id"
    return response

@app.before_request
def handle_preflight():
    if request.method == "OPTIONS":
        resp = make_response("", 204)
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, Mcp-Session-Id"
        resp.headers["Access-Control-Expose-Headers"] = "Mcp-Session-Id"
        return resp

# ------------------------------------------------------------------------------
# JSON-RPC routes implementing the MCP low-level protocol
# ------------------------------------------------------------------------------
@app.post("/mcp")
def mcp_endpoint():
    try:
        body = request.get_json(force=True, silent=False)
        if not isinstance(body, dict):
            return jsonify(jsonrpc_error(-32600, "Invalid Request: expected JSON object.", None)), 400

        method = body.get("method")
        params = body.get("params", {}) or {}
        request_id = body.get("id")

        # --- initialize ---
        if method == "initialize":
            result = {
                "serverInfo": {"name": server.name, "version": server.version},
                "capabilities": server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={}
                ),
            }
            return jsonify(jsonrpc_result(result, request_id))

        # --- tools/list ---
        if method == "tools/list":
            tools = asyncio.run(list_tools())
            serialized_tools = [
                {
                    "name": t.name,
                    "description": t.description,
                    "inputSchema": t.inputSchema,
                    **({"outputSchema": t.outputSchema} if getattr(t, "outputSchema", None) else {}),
                }
                for t in tools
            ]
            # No pagination here; omit nextCursor.
            return jsonify(jsonrpc_result({"tools": serialized_tools}, request_id))

        # --- tools/call ---
        if method == "tools/call":
            tool_name = params.get("name") or params.get("toolName")  # accept legacy
            arguments = params.get("arguments", {}) or {}
            result = asyncio.run(call_tool(tool_name, arguments))
            # result should be {"content":[...]} optionally with "isError"
            return jsonify(jsonrpc_result(result, request_id))

        # --- resources/list ---
        if method == "resources/list":
            # Simple list of files under BASE_DIR (non-paginated)
            items = []
            for path in BASE_DIR.rglob("*"):
                if path.is_file():
                    mime, _ = mimetypes.guess_type(str(path))
                    items.append({
                        "uri": path_to_file_uri(path),
                        "name": path.name,
                        "title": path.name,
                        "mimeType": mime or "application/octet-stream",
                    })
            return jsonify(jsonrpc_result({"resources": items}, request_id))

        # --- resources/read ---
        if method == "resources/read":
            uri = params.get("uri")
            if not uri or not isinstance(uri, str):
                return jsonify(jsonrpc_error(-32602, "Missing 'uri'", request_id)), 400
            if not uri.startswith("file://"):
                return jsonify(jsonrpc_error(-32602, "Only file:// URIs are supported", request_id)), 400

            raw = uri[len("file://"):]
            path = safe_join_under_base(raw)
            if not path.exists() or not path.is_file():
                return jsonify(jsonrpc_error(-32002, "Resource not found", request_id)), 404

            mime, _ = mimetypes.guess_type(str(path))
            if is_texty(mime, path):
                text = path.read_text(encoding="utf-8", errors="replace")
                contents = [{"uri": uri, "name": path.name, "mimeType": mime or "text/plain", "text": text}]
            else:
                data = path.read_bytes()
                contents = [{"uri": uri, "name": path.name, "mimeType": mime or "application/octet-stream",
                             "blob": base64.b64encode(data).decode("ascii")}]
            return jsonify(jsonrpc_result({"contents": contents}, request_id))

        # --- resources/templates/list (optional discoverability) ---
        if method == "resources/templates/list":
            tmpl = [{
                "uriTemplate": "file:///{relative_path}",
                "name": "Sandbox files",
                "title": "Files under sandbox root",
                "description": "Access files under the configured BASE_DIR",
                "mimeType": "application/octet-stream"
            }]
            return jsonify(jsonrpc_result({"resourceTemplates": tmpl}, request_id))

        # Unknown
        return jsonify(jsonrpc_error(-32601, f"Method not found: {method}", request_id)), 400

    except json.JSONDecodeError as e:
        log.exception("JSON decode error")
        return jsonify(jsonrpc_error(-32700, f"Parse error: {str(e)}")), 400
    except PermissionError as e:
        log.warning("Permission error: %s", e)
        return jsonify(jsonrpc_error(-32001, str(e), body.get("id") if isinstance(body, dict) else None)), 403
    except Exception as e:
        log.exception("Unhandled error")
        rid = None
        try:
            rid = body.get("id") if isinstance(body, dict) else None
        except Exception:
            pass
        return jsonify(jsonrpc_error(-32000, str(e), rid)), 500

# ------------------------------------------------------------------------------
# Health check
# ------------------------------------------------------------------------------
@app.get("/health")
def health():
    return jsonify({"status": "healthy", "baseDir": str(BASE_DIR)})

# ------------------------------------------------------------------------------
# Run (dev server)
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    # Deps:
    #   pip install flask python-dateutil pytz
    # (optional) pip install modelcontextprotocol
    #
    # Sandbox:
    #   export MCP_FS_ROOT=/absolute/path/you/want
    #
    # Start:
    #   python mcp_flask_fs_server.py
    #
    # Test (initialize):
    #   curl -s localhost:8080/mcp -H 'Content-Type: application/json' \
    #     -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' | jq
    app.run(host="0.0.0.0", port=8080, debug=True)
