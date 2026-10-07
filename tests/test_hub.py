import os
import pytest
import time
import uuid

# Override the DB_PATH before importing server
TEST_DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'test_hub.db'))
os.environ['MCP_HUB_DB_PATH'] = TEST_DB_PATH

import db
import server

@pytest.fixture(autouse=True)
def setup_teardown():
    # Remove db before test
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)
    if os.path.exists(TEST_DB_PATH + "-wal"):
        os.remove(TEST_DB_PATH + "-wal")
    if os.path.exists(TEST_DB_PATH + "-shm"):
        os.remove(TEST_DB_PATH + "-shm")
        
    db.init_db(TEST_DB_PATH)
    
    yield
    
    # Optional: cleanup after
    pass

def test_a_cross_agent_messaging():
    """Test A — Cross-agent messaging"""
    # Claude registers
    server.register_agent("claude-1", "Claude", "Anthropic")
    # Codex registers
    server.register_agent("codex-1", "Codex", "OpenAI")
    
    # Claude sends message to Codex
    msg_id = db.send_message(TEST_DB_PATH, "claude-1", "Hello Codex", recipient_id="codex-1")
    
    # Codex checks inbox
    inbox = db.get_inbox(TEST_DB_PATH, "codex-1")
    assert len(inbox) == 1
    assert inbox[0]['body'] == "Hello Codex"
    assert inbox[0]['sender_id'] == "claude-1"
    
    # Codex replies
    reply_id = db.send_message(TEST_DB_PATH, "codex-1", "Hello Claude", recipient_id="claude-1", reply_to_id=msg_id)
    
    # Claude checks inbox
    claude_inbox = db.get_inbox(TEST_DB_PATH, "claude-1")
    assert len(claude_inbox) == 1
    assert claude_inbox[0]['body'] == "Hello Claude"
    assert claude_inbox[0]['sender_id'] == "codex-1"
    
    # Inbox should now be empty for both
    assert len(db.get_inbox(TEST_DB_PATH, "claude-1")) == 0
    assert len(db.get_inbox(TEST_DB_PATH, "codex-1")) == 0

def test_b_offline_delivery():
    """Test B — Offline delivery"""
    server.register_agent("claude-1", "Claude", "Anthropic")
    server.register_agent("codex-1", "Codex", "OpenAI")
    
    # Codex is "offline" (just not checking inbox)
    db.send_message(TEST_DB_PATH, "claude-1", "Msg 1", recipient_id="codex-1")
    db.send_message(TEST_DB_PATH, "claude-1", "Msg 2", recipient_id="codex-1")
    db.send_message(TEST_DB_PATH, "claude-1", "Msg 3", recipient_id="codex-1")
    
    # Codex "reconnects" and checks inbox
    inbox = db.get_inbox(TEST_DB_PATH, "codex-1")
    assert len(inbox) == 3
    assert inbox[0]['body'] == "Msg 1"
    assert inbox[1]['body'] == "Msg 2"
    assert inbox[2]['body'] == "Msg 3"

def test_c_shared_rooms():
    """Test C — Shared rooms"""
    server.register_agent("agent-1", "A1", "P1")
    server.register_agent("agent-2", "A2", "P2")
    server.register_agent("agent-3", "A3", "P3")
    
    server.create_room("general", "General Chat")
    
    server.join_room("general", "agent-1")
    server.join_room("general", "agent-2")
    server.join_room("general", "agent-3")
    
    db.send_message(TEST_DB_PATH, "agent-1", "Hello room", room_id="general")
    db.send_message(TEST_DB_PATH, "agent-2", "Hi A1", room_id="general")
    db.send_message(TEST_DB_PATH, "agent-3", "Greetings", room_id="general")
    
    # Retrieve complete room history (should be 3 messages)
    history = db.get_messages(TEST_DB_PATH, room_id="general", limit=10)
    assert len(history) == 3
    assert history[0]['body'] == "Hello room"
    assert history[2]['body'] == "Greetings"
    
    # Check A1's inbox (should get messages from A2 and A3, but not its own)
    a1_inbox = db.get_inbox(TEST_DB_PATH, "agent-1")
    assert len(a1_inbox) == 2
    assert a1_inbox[0]['body'] == "Hi A1"
    assert a1_inbox[1]['body'] == "Greetings"

def test_d_persistence():
    """Test D — Persistence"""
    server.register_agent("a1", "A", "P")
    server.create_room("persists", "Persist Room")
    server.join_room("persists", "a1")
    
    db.send_message(TEST_DB_PATH, "a1", "Persistent message", room_id="persists")
    
    # "Restart" server by just re-initializing DB connection (handled by new get_connection in db.py)
    # The message should still be there
    history = db.get_messages(TEST_DB_PATH, room_id="persists")
    assert len(history) == 1
    assert history[0]['body'] == "Persistent message"

def test_f_task_handoff():
    """Test F — Task handoff"""
    server.register_agent("claude-1", "Claude", "A")
    server.register_agent("codex-1", "Codex", "A")
    
    req_id = db.create_request(TEST_DB_PATH, "claude-1", "codex-1", "Fix the engine")
    
    # Codex gets the request notification in inbox
    inbox = db.get_inbox(TEST_DB_PATH, "codex-1")
    assert len(inbox) == 1
    assert "Task Request:" in inbox[0]['body']
    
    # Codex updates status
    db.update_request_status(TEST_DB_PATH, req_id, "completed")
    
    # Codex sends result back
    db.send_message(TEST_DB_PATH, "codex-1", "Fixed it!", recipient_id="claude-1")
    
    # Claude checks inbox
    claude_inbox = db.get_inbox(TEST_DB_PATH, "claude-1")
    assert len(claude_inbox) == 1
    assert claude_inbox[0]['body'] == "Fixed it!"
