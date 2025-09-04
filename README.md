curl -X GET https://localhost:8080/health


✅ List Tools
curl -X POST https://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -d '{"method":"listTools","id":1,"jsonrpc":"2.0"}'


✅ Call Tools
Echo
curl -X POST https://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -d '{"method":"callTool","id":2,"jsonrpc":"2.0","params":{"toolName":"echo","arguments":{"text":"Hello from Ubuntu"}}}'
Add Numbers
curl -X POST https://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -d '{"method":"callTool","id":3,"jsonrpc":"2.0","params":{"toolName":"add_numbers","arguments":{"numbers":[10,20,30]}}}'
Now (timezone)
curl -X POST https://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -d '{"method":"callTool","id":4,"jsonrpc":"2.0","params":{"toolName":"now","arguments":{"timezone":"Asia/Kolkata"}}}'
Word Count
curl -X POST https://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -d '{"method":"callTool","id":5,"jsonrpc":"2.0","params":{"toolName":"word_count","arguments":{"text":"MCP is working on Ubuntu"}}}'


USING OPENAI BRIDGE:
# 1) Start your MCP Flask server
python mcp_plain_flask_app.py  # serves /mcp on :8080

# 2) In another shell, run the bridge
export OPENAI_API_KEY=sk-...
python mcp_openai_bridge.py  # serves /chat on :8090

# 3) Try it
curl -s -X POST localhost:8090/chat \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"What time is it in Asia/Kolkata and how many words in \"hello brave new world\"?"}'
