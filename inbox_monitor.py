import sqlite3
import time
import os
import sys

DEFAULT_DB_PATH = os.path.expanduser('~/.mcp-agent-hub/hub.db')
AGENT_ID = 'antigravity-main'

def monitor():
    notified = set()
    while True:
        try:
            conn = sqlite3.connect(DEFAULT_DB_PATH, timeout=10.0)
            conn.row_factory = sqlite3.Row
            cursor = conn.execute('''
                SELECT m.id, m.sender_id 
                FROM messages m
                JOIN message_status ms ON m.id = ms.message_id
                WHERE ms.agent_id = ? AND ms.status = 'unread'
            ''', (AGENT_ID,))
            
            for msg in cursor.fetchall():
                msg_id = msg['id']
                if msg_id not in notified:
                    notified.add(msg_id)
                    # This print will be captured by Antigravity's daemon manager
                    # and sent to the agent as a high-priority system message, waking it up!
                    print(f"NOTIFICATION: You have a new unread message in the MCP Hub from '{msg['sender_id']}'. Please use your 'get_inbox' MCP tool to read it immediately!", flush=True)
                    
            conn.close()
        except Exception:
            pass
        
        time.sleep(3)

if __name__ == '__main__':
    monitor()
