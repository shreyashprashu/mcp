# MCP Flask Server with OpenAI Bridge

This project demonstrates how to run a **Minimal Control Protocol (MCP)** server with Flask, expose its tools, and connect it to OpenAI’s API via a bridge.

---

## 🔍 Health Check

Verify the server is running:

```bash
curl -X GET https://localhost:8080/health
```

---

## ✅ MCP Endpoints

### List Tools

```bash
curl -X POST https://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -d '{"method":"listTools","id":1,"jsonrpc":"2.0"}'
```

### Call Tools

**Echo**

```bash
curl -X POST https://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -d '{"method":"callTool","id":2,"jsonrpc":"2.0","params":{"toolName":"echo","arguments":{"text":"Hello from Ubuntu"}}}'
```

**Add Numbers**

```bash
curl -X POST https://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -d '{"method":"callTool","id":3,"jsonrpc":"2.0","params":{"toolName":"add_numbers","arguments":{"numbers":[10,20,30]}}}'
```

**Now (with timezone)**

```bash
curl -X POST https://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -d '{"method":"callTool","id":4,"jsonrpc":"2.0","params":{"toolName":"now","arguments":{"timezone":"Asia/Kolkata"}}}'
```

**Word Count**

```bash
curl -X POST https://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -d '{"method":"callTool","id":5,"jsonrpc":"2.0","params":{"toolName":"word_count","arguments":{"text":"MCP is working on Ubuntu"}}}'
```

---

## 🔗 Using the OpenAI Bridge

### 1. Start your MCP Flask server

```bash
python mcp_plain_flask_app.py  # serves /mcp on :8080
```

### 2. Run the OpenAI Bridge

```bash
export OPENAI_API_KEY=sk-...
python mcp_openai_bridge.py   # serves /chat on :8090
```

### 3. Try a request

```bash
curl -s -X POST localhost:8090/chat \
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
