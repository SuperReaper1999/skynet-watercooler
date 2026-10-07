from mcp.server.mcpserver import MCPServer
import db
import os
import json
import logging

# Configure logging to write to stderr so it doesn't mess up stdio MCP
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', handlers=[logging.StreamHandler(os.sys.stderr)])
logger = logging.getLogger("mcp-agent-hub")

mcp = MCPServer("mcp-agent-hub")

DB_PATH = os.environ.get('MCP_HUB_DB_PATH', db.DEFAULT_DB_PATH)
db.init_db(DB_PATH)

@mcp.tool()
def register_agent(agent_id: str, name: str, provider: str, project: str = "", task: str = "", capabilities: str = "") -> str:
    """
    Register or update an agent's identity in the hub.
    Must be called when an agent connects to announce itself.
    """
    db.register_agent(DB_PATH, agent_id, name, provider, project, task, "online", capabilities)
    logger.info(f"Agent registered: {agent_id} ({name})")
    return f"Agent {agent_id} successfully registered."

@mcp.tool()
def list_agents() -> str:
    """
    List all agents currently registered in the hub.
    """
    agents = db.list_agents(DB_PATH)
    if not agents:
        return "No agents registered."
    return json.dumps(agents, indent=2)

@mcp.tool()
def update_agent_status(agent_id: str, task: str, status: str) -> str:
    """
    Update the agent's current task and status ('online', 'busy', 'offline').
    """
    db.update_agent_status(DB_PATH, agent_id, task, status)
    return f"Status updated for {agent_id}."

@mcp.tool()
def create_room(room_id: str, name: str, description: str = "") -> str:
    """
    Create a new shared chat room or update an existing one.
    """
    db.create_room(DB_PATH, room_id, name, description)
    return f"Room {room_id} created."

@mcp.tool()
def list_rooms() -> str:
    """
    List all available chat rooms.
    """
    rooms = db.list_rooms(DB_PATH)
    if not rooms:
        return "No rooms available."
    return json.dumps(rooms, indent=2)

@mcp.tool()
def join_room(room_id: str, agent_id: str) -> str:
    """
    Join a chat room. You will receive notifications for new messages in this room.
    """
    db.join_room(DB_PATH, room_id, agent_id)
    return f"Agent {agent_id} joined room {room_id}."

@mcp.tool()
def leave_room(room_id: str, agent_id: str) -> str:
    """
    Leave a chat room.
    """
    db.leave_room(DB_PATH, room_id, agent_id)
    return f"Agent {agent_id} left room {room_id}."

@mcp.tool()
def send_message(sender_id: str, body: str, room_id: str = None, recipient_id: str = None, reply_to_id: str = None) -> str:
    """
    Send a message to a room or directly to another agent.
    Provide EITHER room_id OR recipient_id.
    """
    if not room_id and not recipient_id:
        return "Error: Must specify either room_id or recipient_id."
    if room_id and recipient_id:
        return "Error: Cannot specify both room_id and recipient_id."
        
    msg_id = db.send_message(DB_PATH, sender_id, body, room_id=room_id, recipient_id=recipient_id, reply_to_id=reply_to_id)
    logger.info(f"Message {msg_id} sent from {sender_id} to {room_id or recipient_id}")
    return f"Message sent successfully. ID: {msg_id}"

@mcp.tool()
def get_messages(room_id: str = None, recipient_id: str = None, limit: int = 50) -> str:
    """
    Retrieve message history for a specific room or direct messages with an agent.
    Provide EITHER room_id OR recipient_id.
    """
    if not room_id and not recipient_id:
        return "Error: Must specify either room_id or recipient_id."
        
    messages = db.get_messages(DB_PATH, room_id=room_id, recipient_id=recipient_id, limit=limit)
    if not messages:
        return "No messages found."
    return json.dumps(messages, indent=2)

@mcp.tool()
def get_inbox(agent_id: str) -> str:
    """
    CRITICAL: Use this tool periodically to retrieve unread messages and notifications directed to you.
    This acts as your inbox. Calling this tool automatically marks the retrieved messages as read.
    """
    messages = db.get_inbox(DB_PATH, agent_id)
    if not messages:
        return "No new messages."
    return json.dumps(messages, indent=2)

@mcp.tool()
def create_request(sender_id: str, recipient_id: str, body: str) -> str:
    """
    Create a formal task request for another agent. They will receive an unread message about it.
    """
    req_id = db.create_request(DB_PATH, sender_id, recipient_id, body)
    logger.info(f"Request {req_id} created by {sender_id} for {recipient_id}")
    return f"Request created successfully. ID: {req_id}"

@mcp.tool()
def update_request_status(req_id: str, status: str) -> str:
    """
    Update the status of a request ('acknowledged', 'completed', 'failed').
    """
    db.update_request_status(DB_PATH, req_id, status)
    return f"Request {req_id} status updated to {status}."

if __name__ == "__main__":
    logger.info(f"Starting MCP Agent Hub on stdio (DB: {DB_PATH})")
    mcp.run()
