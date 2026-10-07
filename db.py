import sqlite3
import os
import time
import uuid

DEFAULT_DB_PATH = os.path.expanduser('~/.mcp-agent-hub/hub.db')

def get_connection(db_path=DEFAULT_DB_PATH):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=10.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL;')
    conn.execute('PRAGMA busy_timeout=5000;')
    conn.execute('PRAGMA synchronous=NORMAL;')
    return conn

def init_db(db_path=DEFAULT_DB_PATH):
    with get_connection(db_path) as conn:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS agents (
                id TEXT PRIMARY KEY,
                name TEXT,
                provider TEXT,
                project TEXT,
                task TEXT,
                status TEXT,
                capabilities TEXT,
                last_seen REAL
            );

            CREATE TABLE IF NOT EXISTS rooms (
                id TEXT PRIMARY KEY,
                name TEXT,
                description TEXT
            );

            CREATE TABLE IF NOT EXISTS room_members (
                room_id TEXT,
                agent_id TEXT,
                joined_at REAL,
                PRIMARY KEY (room_id, agent_id)
            );

            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                sender_id TEXT,
                room_id TEXT,
                recipient_id TEXT,
                body TEXT,
                reply_to_id TEXT,
                metadata TEXT,
                timestamp REAL,
                type TEXT DEFAULT 'message'
            );
            
            CREATE TABLE IF NOT EXISTS message_status (
                message_id TEXT,
                agent_id TEXT,
                status TEXT,
                PRIMARY KEY (message_id, agent_id)
            );

            CREATE TABLE IF NOT EXISTS requests (
                id TEXT PRIMARY KEY,
                sender_id TEXT,
                recipient_id TEXT,
                body TEXT,
                status TEXT,
                timestamp REAL
            );
        ''')
        
def register_agent(db_path, agent_id, name, provider, project="", task="", status="online", capabilities=""):
    with get_connection(db_path) as conn:
        conn.execute('''
            INSERT INTO agents (id, name, provider, project, task, status, capabilities, last_seen)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,
                provider=excluded.provider,
                project=excluded.project,
                task=excluded.task,
                status=excluded.status,
                capabilities=excluded.capabilities,
                last_seen=excluded.last_seen
        ''', (agent_id, name, provider, project, task, status, capabilities, time.time()))

def list_agents(db_path):
    with get_connection(db_path) as conn:
        cursor = conn.execute('SELECT * FROM agents')
        return [dict(row) for row in cursor.fetchall()]

def update_agent_status(db_path, agent_id, task, status):
    with get_connection(db_path) as conn:
        conn.execute('UPDATE agents SET task=?, status=?, last_seen=? WHERE id=?', 
                     (task, status, time.time(), agent_id))

def create_room(db_path, room_id, name, description=""):
    with get_connection(db_path) as conn:
        conn.execute('''
            INSERT INTO rooms (id, name, description)
            VALUES (?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,
                description=excluded.description
        ''', (room_id, name, description))

def list_rooms(db_path):
    with get_connection(db_path) as conn:
        cursor = conn.execute('SELECT * FROM rooms')
        return [dict(row) for row in cursor.fetchall()]

def join_room(db_path, room_id, agent_id):
    with get_connection(db_path) as conn:
        conn.execute('''
            INSERT OR IGNORE INTO room_members (room_id, agent_id, joined_at)
            VALUES (?, ?, ?)
        ''', (room_id, agent_id, time.time()))

def leave_room(db_path, room_id, agent_id):
    with get_connection(db_path) as conn:
        conn.execute('DELETE FROM room_members WHERE room_id=? AND agent_id=?', (room_id, agent_id))

def get_room_members(db_path, room_id):
    with get_connection(db_path) as conn:
        cursor = conn.execute('''
            SELECT a.* FROM agents a
            JOIN room_members rm ON a.id = rm.agent_id
            WHERE rm.room_id = ?
        ''', (room_id,))
        return [dict(row) for row in cursor.fetchall()]

def send_message(db_path, sender_id, body, room_id=None, recipient_id=None, reply_to_id=None, msg_type="message", metadata=""):
    msg_id = str(uuid.uuid4())
    timestamp = time.time()
    
    with get_connection(db_path) as conn:
        conn.execute('BEGIN TRANSACTION')
        try:
            conn.execute('''
                INSERT INTO messages (id, sender_id, room_id, recipient_id, body, reply_to_id, metadata, timestamp, type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (msg_id, sender_id, room_id, recipient_id, body, reply_to_id, metadata, timestamp, msg_type))
            
            if room_id:
                members = conn.execute('SELECT agent_id FROM room_members WHERE room_id=?', (room_id,)).fetchall()
                for member in members:
                    if member['agent_id'] != sender_id:
                        conn.execute('INSERT INTO message_status (message_id, agent_id, status) VALUES (?, ?, ?)',
                                     (msg_id, member['agent_id'], 'unread'))
            elif recipient_id:
                conn.execute('INSERT INTO message_status (message_id, agent_id, status) VALUES (?, ?, ?)',
                             (msg_id, recipient_id, 'unread'))
            conn.execute('COMMIT')
            return msg_id
        except Exception as e:
            conn.execute('ROLLBACK')
            raise e

def get_messages(db_path, room_id=None, recipient_id=None, limit=50, before_ts=None):
    with get_connection(db_path) as conn:
        query = "SELECT * FROM messages WHERE 1=1 "
        params = []
        
        if room_id:
            query += " AND room_id = ?"
            params.append(room_id)
        elif recipient_id:
            query += " AND ((recipient_id = ?) OR (sender_id = ? AND recipient_id IS NOT NULL))"
            params.extend([recipient_id, recipient_id])
            
        if before_ts:
            query += " AND timestamp < ?"
            params.append(before_ts)
            
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        
        cursor = conn.execute(query, params)
        messages = [dict(row) for row in cursor.fetchall()]
        return sorted(messages, key=lambda x: x['timestamp'])

def get_inbox(db_path, agent_id):
    with get_connection(db_path) as conn:
        cursor = conn.execute('''
            SELECT m.* FROM messages m
            JOIN message_status ms ON m.id = ms.message_id
            WHERE ms.agent_id = ? AND ms.status = 'unread'
            ORDER BY m.timestamp ASC
        ''', (agent_id,))
        messages = [dict(row) for row in cursor.fetchall()]
        
        if messages:
            msg_ids = [m['id'] for m in messages]
            placeholders = ','.join(['?'] * len(msg_ids))
            params = msg_ids + [agent_id]
            conn.execute(f"UPDATE message_status SET status = 'read' WHERE message_id IN ({placeholders}) AND agent_id = ?", params)
            
        return messages

def create_request(db_path, sender_id, recipient_id, body):
    req_id = str(uuid.uuid4())
    timestamp = time.time()
    with get_connection(db_path) as conn:
        conn.execute('''
            INSERT INTO requests (id, sender_id, recipient_id, body, status, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (req_id, sender_id, recipient_id, body, 'pending', timestamp))
        
        msg_body = f"Task Request: {body}"
        msg_id = str(uuid.uuid4())
        conn.execute('BEGIN TRANSACTION')
        try:
            conn.execute('''
                INSERT INTO messages (id, sender_id, recipient_id, body, metadata, timestamp, type)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (msg_id, sender_id, recipient_id, msg_body, f'{{"request_id": "{req_id}"}}', timestamp, 'request'))
            conn.execute('INSERT INTO message_status (message_id, agent_id, status) VALUES (?, ?, ?)',
                         (msg_id, recipient_id, 'unread'))
            conn.execute('COMMIT')
        except:
            conn.execute('ROLLBACK')
            raise
    return req_id

def update_request_status(db_path, req_id, status):
    with get_connection(db_path) as conn:
        conn.execute('UPDATE requests SET status=? WHERE id=?', (status, req_id))
