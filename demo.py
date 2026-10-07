import asyncio
import os
import sys
from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters

async def run_agent(name, provider, target_script):
    """Run an agent session to demonstrate communication."""
    
    # We create two completely separate MCP server processes
    server_params = StdioServerParameters(
        command=sys.executable,
        args=[target_script],
        env=os.environ.copy()
    )
    
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            # Helper to call tools
            async def call_tool(tool_name, arguments):
                result = await session.call_tool(tool_name, arguments)
                return result.content[0].text
                
            return session, call_tool

async def main():
    target_script = os.path.abspath(os.path.join(os.path.dirname(__file__), 'server.py'))
    
    # Optional: use a fresh DB for demo
    os.environ['MCP_HUB_DB_PATH'] = os.path.abspath(os.path.join(os.path.dirname(__file__), 'demo_hub.db'))
    if os.path.exists(os.environ['MCP_HUB_DB_PATH']):
        os.remove(os.environ['MCP_HUB_DB_PATH'])
        
    print("Starting Claude Code simulated process...")
    server_params_claude = StdioServerParameters(command=sys.executable, args=[target_script], env=os.environ.copy())
    
    print("Starting Codex simulated process...")
    server_params_codex = StdioServerParameters(command=sys.executable, args=[target_script], env=os.environ.copy())
    
    async with stdio_client(server_params_claude) as (read_c, write_c), stdio_client(server_params_codex) as (read_x, write_x):
        async with ClientSession(read_c, write_c) as claude_session, ClientSession(read_x, write_x) as codex_session:
            await claude_session.initialize()
            await codex_session.initialize()
            
            async def call_claude(tool, args):
                res = await claude_session.call_tool(tool, args)
                return res.content[0].text
                
            async def call_codex(tool, args):
                res = await codex_session.call_tool(tool, args)
                return res.content[0].text
                
            print("\n--- Registration ---")
            print("Claude:", await call_claude("register_agent", {"agent_id": "claude", "name": "Claude", "provider": "Anthropic"}))
            print("Codex:", await call_codex("register_agent", {"agent_id": "codex", "name": "Codex", "provider": "OpenAI"}))
            
            print("\n--- Messaging ---")
            print("Claude sends a message to Codex...")
            await call_claude("send_message", {"sender_id": "claude", "recipient_id": "codex", "body": "Engine collision queries need batched raycasts. Can you implement this?"})
            
            print("\n--- Inbox Polling ---")
            print("Codex checks its inbox...")
            codex_inbox = await call_codex("get_inbox", {"agent_id": "codex"})
            print(f"Codex Inbox:\n{codex_inbox}")
            
            print("\n--- Replying ---")
            print("Codex sends a reply...")
            await call_codex("send_message", {"sender_id": "codex", "recipient_id": "claude", "body": "Implemented batched raycasts. API is available. Please test."})
            
            print("\n--- Inbox Polling ---")
            print("Claude checks its inbox...")
            claude_inbox = await call_claude("get_inbox", {"agent_id": "claude"})
            print(f"Claude Inbox:\n{claude_inbox}")

if __name__ == "__main__":
    asyncio.run(main())
