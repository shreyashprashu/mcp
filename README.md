# MCP Tools (Flask + OpenAI Bridge)

This project provides a **Minimal Control Protocol (MCP) server** exposing simple utility tools, along with a **bridge to OpenAI’s API** that enables automatic tool-calling inside chat completions.

It includes multiple components:

* **MCP Server (Flask)** – A JSON-RPC API exposing tools over HTTP.
* **MCP Server (stdio)** – An alternative stdio-based MCP server for local clients.
* **Client** – Example async client demonstrating how to connect and call MCP tools.
* **OpenAI Bridge** – Connects MCP tools to OpenAI’s `chat.completions` endpoint, letting GPT automatically discover and call tools.

---

## 🚀 Features

* Implements the **MCP protocol** over both HTTP (Flask) and stdio.
* Exposes a catalog of tools:

  * **echo** – Returns back a string.
  * **add\_numbers** – Sums a list of numbers.
  * **now** – Returns the current datetime (with optional timezone).
  * **word\_count** – Counts words and characters in text.
* JSON-RPC compliant endpoints (`listTools`, `callTool`, `initialize`).
* CORS-friendly Flask server for web integrations.
* Full **OpenAI integration**: tools are dynamically mapped into OpenAI’s tool schema so GPT models can invoke them seamlessly.
* Example client to test MCP servers directly.

---

## 📂 Project Structure

```
mcp/
├── server.py              # stdio-based MCP server (async, model-driven)
├── mcp_plain_flask_app.py # HTTP MCP server with Flask
├── client.py              # Example MCP client (stdio)
└── mcp_openai_bridge.py   # Bridge MCP → OpenAI tool-calling
```

---

## ⚙️ Installation

Requirements: **Python 3.10+**

```bash
pip install flask requests openai python-dateutil pytz mcp
```

---

## 🖥️ Running the MCP Servers

### 1. Flask MCP Server (HTTP)

Start the HTTP server (serves `/mcp` on port 8080):

```bash
python mcp_plain_flask_app.py
```

Health check:

```bash
curl http://localhost:8080/health
```

List available tools:

```bash
curl -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -d '{"method":"listTools","id":1,"jsonrpc":"2.0"}'
```

Call a tool:

```bash
curl -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -d '{"method":"callTool","id":2,"jsonrpc":"2.0","params":{"toolName":"echo","arguments":{"text":"Hello from MCP"}}}'
```

### 2. MCP Server (stdio)

Run the stdio server:

```bash
python server.py
```

### 3. Example Client

Run the sample client (connects to stdio server):

```bash
python client.py
```

### 4. OpenAI Bridge

Start the bridge (serves `/chat` on port 8090):

```bash
export OPENAI_API_KEY=sk-...
python mcp_openai_bridge.py
```

Query via chat:

```bash
curl -s -X POST http://localhost:8090/chat \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"What time is it in Asia/Kolkata and how many words in \"hello brave new world\"?"}'
```

---

## 📝 Example Response

```json
{
  "answer": "The current time in Asia/Kolkata is 2025-09-04T19:10:10 (UTC+05:30). The phrase \"hello brave new world\" contains 4 words."
}
```
