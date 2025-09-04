# filename: openai_bridge.py
import os
import json
import uuid
import requests
from typing import Any, Dict, List

# --- OpenAI SDK (v1.x) ---
from openai import OpenAI
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "sk-proj-xxx"))

MCP_URL = os.environ.get("MCP_URL", "http://localhost:8080/mcp")
MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

# ---------- MCP helpers ----------
def mcp_jsonrpc(method: str, params: Dict[str, Any]) -> Dict[str, Any]:
    payload = {"jsonrpc": "2.0", "id": str(uuid.uuid4()), "method": method, "params": params}
    r = requests.post(MCP_URL, json=payload, timeout=60)
    r.raise_for_status()
    data = r.json()
    if "error" in data:
        raise RuntimeError(f"MCP error {data['error'].get('code')}: {data['error'].get('message')}")
    return data["result"]

def mcp_initialize():
    return mcp_jsonrpc("initialize", {})

def mcp_list_tools() -> List[Dict[str, Any]]:
    res = mcp_jsonrpc("tools/list", {"cursor": None})
    return res.get("tools", [])

def mcp_call_tool(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    return mcp_jsonrpc("tools/call", {"name": name, "arguments": args})

# Optional helpers
def mcp_resources_list() -> List[Dict[str, Any]]:
    res = mcp_jsonrpc("resources/list", {})
    return res.get("resources", [])

def mcp_resources_read(uri: str) -> Dict[str, Any]:
    res = mcp_jsonrpc("resources/read", {"uri": uri})
    return res

# ---------- Convert MCP → OpenAI function tools ----------
def to_openai_tools(mcp_tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    tools = []
    for t in mcp_tools:
        tools.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description") or "",
                "parameters": t.get("inputSchema") or {"type": "object", "properties": {}},
            }
        })
    return tools

# ---------- Chat loop with tool-calling ----------
def run_chat(prompt: str, system: str = "You are a cautious assistant that prefers using available tools.") -> str:
    mcp_initialize()  # make sure server is ready
    mcp_tools = mcp_list_tools()
    tools = to_openai_tools(mcp_tools)

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt}
    ]

    for _ in range(8):
        resp = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=tools,
            tool_choice="auto",
        )

        msg = resp.choices[0].message
        tool_calls = msg.tool_calls or []

        if not tool_calls:
            return msg.content or ""

        # echo assistant msg (if any) so model can keep its chain-of-thought (not shown to user)
        messages.append({
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [tc.dict() for tc in tool_calls]
        })

        for tc in tool_calls:
            name = tc.function.name
            args = json.loads(tc.function.arguments or "{}")
            try:
                mcp_result = mcp_call_tool(name, args)
                # Return JSON directly if present; else compose from text parts
                text_parts = []
                json_obj = None
                for part in mcp_result.get("content", []):
                    if part.get("type") == "json" and "json" in part:
                        json_obj = part["json"]
                    elif part.get("type") == "text":
                        text_parts.append(part.get("text", ""))

                content_for_model = json.dumps(json_obj, ensure_ascii=False) if json_obj is not None else "\n".join(tp for tp in text_parts if tp)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": name,
                    "content": content_for_model or ""
                })
            except Exception as e:
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": name,
                    "content": json.dumps({"error": str(e)})
                })

    return "Too many tool-calling steps."

# ---------- Minimal Flask for chatting (optional) ----------
if __name__ == "__main__":
    from flask import Flask, request, jsonify
    app = Flask(__name__)

    @app.post("/chat")
    def chat():
        data = request.get_json(force=True) or {}
        prompt = data.get("prompt", "")
        if not prompt:
            return jsonify({"error": "Missing 'prompt'"}), 400
        try:
            answer = run_chat(prompt)
            return jsonify({"answer": answer})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    app.run(host="0.0.0.0", port=8090, debug=True)
