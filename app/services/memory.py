import json
import logging
import redis
from typing import Optional
from app.core.config import settings

try:
    import pyodbc
except ImportError:
    pyodbc = None
import sqlite3

# Initialize Redis client for production idempotency/locking
redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True) if settings.REDIS_URL else None

USE_SQLITE = not settings.SQL_SERVER_CONN

class ConnectionWrapper:
    def __init__(self, conn):
        self.conn = conn

    def __getattr__(self, name):
        return getattr(self.conn, name)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            try:
                self.conn.rollback()
            except Exception as e:
                logging.error(f"Error during rollback: {e}")
        else:
            try:
                self.conn.commit()
            except Exception as e:
                logging.error(f"Error during commit: {e}")
        try:
            self.conn.close()
        except Exception as e:
            logging.error(f"Error during connection close: {e}")

def get_conn():
    """Returns a wrapped connection that commits/rolls back and closes upon exiting the context manager."""
    if USE_SQLITE:
        raw_conn = sqlite3.connect(settings.SQLITE_DB_PATH)
    else:
        if pyodbc is None:
            raise ImportError("pyodbc is not installed but SQL_SERVER_CONN is configured.")
        raw_conn = pyodbc.connect(settings.SQL_SERVER_CONN)
    return ConnectionWrapper(raw_conn)


def clean_wa_id(wa_id: str) -> str:
    """Standardizes phone numbers by removing '+', spaces, and dashes."""
    if not wa_id:
        return wa_id
    return wa_id.replace("+", "").replace(" ", "").replace("-", "").strip()


# -------------------------------------------------------
# Initialize DB
# -------------------------------------------------------
def init_db():
    try:
        conn = get_conn()
        cursor = conn.cursor()

        if USE_SQLITE:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    phone_no TEXT PRIMARY KEY,
                    conversation TEXT,
                    task_type TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pending_followups (
                    phone_no TEXT,
                    reservation_id TEXT,
                    task_type TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (phone_no, reservation_id)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS notification_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phone_no TEXT,
                    notification_type TEXT,
                    status TEXT,
                    response_detail TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS welcome_sent (
                    phone_no TEXT,
                    reservation_id TEXT,
                    sent_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (phone_no, reservation_id)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS guest_reservations (
                    phone_no TEXT,
                    booking_id TEXT,
                    booking_code TEXT,
                    meta_data TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (phone_no, booking_id)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phone_no TEXT,
                    sender TEXT,
                    message_text TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
            conn.close()
            logging.info("✅ SQLite DB initialized successfully.")
        else:
            cursor.execute("""
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='conversations' AND xtype='U')
                CREATE TABLE conversations (
                    phone_no NVARCHAR(50) PRIMARY KEY,
                    conversation NVARCHAR(MAX),
                    task_type NVARCHAR(100),
                    created_at DATETIME DEFAULT GETDATE(),
                    updated_at DATETIME DEFAULT GETDATE()
                )
            """)
            cursor.execute("""
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='pending_followups' AND xtype='U')
                CREATE TABLE pending_followups (
                    phone_no NVARCHAR(50),
                    reservation_id NVARCHAR(100),
                    task_type NVARCHAR(100),
                    created_at DATETIME DEFAULT GETDATE(),
                    PRIMARY KEY (phone_no, reservation_id)
                )
            """)
            cursor.execute("""
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='notification_logs' AND xtype='U')
                CREATE TABLE notification_logs (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    phone_no NVARCHAR(50),
                    notification_type NVARCHAR(100),
                    status NVARCHAR(50),
                    response_detail NVARCHAR(MAX),
                    created_at DATETIME DEFAULT GETDATE()
                )
            """)
            cursor.execute("""
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='welcome_sent' AND xtype='U')
                CREATE TABLE welcome_sent (
                    phone_no NVARCHAR(50),
                    reservation_id NVARCHAR(100),
                    sent_at DATETIME DEFAULT GETDATE(),
                    PRIMARY KEY (phone_no, reservation_id)
                )
            """)
            cursor.execute("""
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='guest_reservations' AND xtype='U')
                CREATE TABLE guest_reservations (
                    phone_no NVARCHAR(50),
                    booking_id NVARCHAR(100),
                    booking_code NVARCHAR(100),
                    meta_data NVARCHAR(MAX),
                    created_at DATETIME DEFAULT GETDATE(),
                    PRIMARY KEY (phone_no, booking_id)
                )
            """)
            cursor.execute("""
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='chat_messages' AND xtype='U')
                CREATE TABLE chat_messages (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    phone_no NVARCHAR(50),
                    sender NVARCHAR(50),
                    message_text NVARCHAR(MAX),
                    created_at DATETIME DEFAULT GETDATE()
                )
            """)
            conn.commit()
            conn.close()
            logging.info("✅ SQL Server DB initialized successfully.")
    except Exception as e:
        logging.error(f"DB Init Error: {e}")


init_db()


# -------------------------------------------------------
# Conversations
# -------------------------------------------------------
def get_conversation(phone_no: str) -> list:
    try:
        with get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT conversation FROM conversations WHERE phone_no = ?", (phone_no,))
            row = cursor.fetchone()
            if row:
                return json.loads(row[0])
        return []
    except Exception as e:
        logging.error(f"Get Memory Error: {e}")
        return []


def add_chat_message(phone_no: str, sender: str, text: str):
    """
    Stores an individual message in the chat_messages table.
    sender: 'guest' or 'bot'
    """
    try:
        phone_no = clean_wa_id(phone_no)
        with get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO chat_messages (phone_no, sender, message_text)
                VALUES (?, ?, ?)
            """, (phone_no, sender, text))
            conn.commit()
    except Exception as e:
        logging.error(f"Error adding chat message to DB: {e}")


def get_chat_history_for_ssms(phone_no: str, limit: int = 50) -> list:
    """
    Retrieves history as a list of readable strings for display.
    """
    try:
        phone_no = clean_wa_id(phone_no)
        with get_conn() as conn:
            cursor = conn.cursor()
            if USE_SQLITE:
                cursor.execute("""
                    SELECT sender, message_text, created_at 
                    FROM chat_messages 
                    WHERE phone_no = ? 
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (phone_no, limit))
            else:
                cursor.execute("""
                    SELECT TOP (?) sender, message_text, created_at 
                    FROM chat_messages 
                    WHERE phone_no = ? 
                    ORDER BY created_at DESC
                """, (limit, phone_no))
            rows = cursor.fetchall()
            return rows
    except Exception as e:
        logging.error(f"Error reading chat history: {e}")
        return []


def store_conversation(phone_no: str, conversation: list):
    try:
        trimmed_history = conversation[-20:]
        json_data = json.dumps(trimmed_history)

        with get_conn() as conn:
            cursor = conn.cursor()
            if USE_SQLITE:
                cursor.execute("""
                    INSERT INTO conversations (phone_no, conversation, updated_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(phone_no) DO UPDATE SET
                        conversation = excluded.conversation,
                        updated_at = CURRENT_TIMESTAMP
                """, (phone_no, json_data))
            else:
                cursor.execute("""
                    MERGE conversations AS target
                    USING (VALUES (?, ?)) AS source (phone_no, conversation)
                    ON target.phone_no = source.phone_no
                    WHEN MATCHED THEN
                        UPDATE SET 
                            conversation = source.conversation,
                            updated_at = GETDATE()
                    WHEN NOT MATCHED THEN
                        INSERT (phone_no, conversation) VALUES (source.phone_no, source.conversation);
                """, (phone_no, json_data))
            conn.commit()
    except Exception as e:
        logging.error(f"Store Memory Error: {e}")


def store_message(phone_no: str, role: str, text: str):
    """
    Appends a new message to the LLM's conversation history and stores it in the DB.
    Also logs individual messages to chat_messages.
    role: 'user' or 'assistant'
    """
    try:
        # Update the LLM conversation context
        conversation = get_conversation(phone_no)
        conversation.append({"role": role, "content": text})
        store_conversation(phone_no, conversation)

        # Log individual message for SQL Server viewing
        sender = "bot" if role == "assistant" else "guest"
        add_chat_message(phone_no, sender, text)
    except Exception as e:
        logging.error(f"Store Message Error: {e}")


# -------------------------------------------------------
# Pending Follow-ups
# -------------------------------------------------------
def add_pending_followup(phone_no: str, task_type="checkin", reservation_id="default"):
    try:
        phone_no = clean_wa_id(phone_no)
        with get_conn() as conn:
            cursor = conn.cursor()
            if USE_SQLITE:
                cursor.execute("""
                    INSERT INTO pending_followups (phone_no, reservation_id, task_type)
                    VALUES (?, ?, ?)
                    ON CONFLICT(phone_no, reservation_id) DO UPDATE SET
                        task_type = excluded.task_type
                """, (phone_no, reservation_id, task_type))
            else:
                cursor.execute("""
                    MERGE pending_followups AS target
                    USING (VALUES (?, ?, ?)) AS source (phone_no, reservation_id, task_type)
                    ON target.phone_no = source.phone_no AND target.reservation_id = source.reservation_id
                    WHEN MATCHED THEN
                        UPDATE SET task_type = source.task_type
                    WHEN NOT MATCHED THEN
                        INSERT (phone_no, reservation_id, task_type)
                        VALUES (source.phone_no, source.reservation_id, source.task_type);
                """, (phone_no, reservation_id, task_type))
            conn.commit()
    except Exception as e:
        logging.error(f"Add pending followup error: {e}")


def is_pending_followup(phone_no: str, reservation_id=None) -> bool:
    try:
        phone_no = clean_wa_id(phone_no)
        with get_conn() as conn:
            cursor = conn.cursor()
            if reservation_id:
                cursor.execute("SELECT 1 FROM pending_followups WHERE phone_no = ? AND reservation_id = ?", (phone_no, reservation_id))
            else:
                cursor.execute("SELECT 1 FROM pending_followups WHERE phone_no = ?", (phone_no,))
            result = cursor.fetchone()
            return result is not None
    except Exception as e:
        logging.error(f"Check pending followup error: {e}")
        return False


def get_pending_task_type(phone_no: str, reservation_id: Optional[str] = None) -> Optional[str]:
    try:
        with get_conn() as conn:
            cursor = conn.cursor()
            if reservation_id:
                cursor.execute(
                    "SELECT task_type FROM pending_followups WHERE phone_no = ? AND reservation_id = ?",
                    (phone_no, reservation_id)
                )
            else:
                if USE_SQLITE:
                    cursor.execute(
                        "SELECT task_type FROM pending_followups WHERE phone_no = ? ORDER BY created_at DESC LIMIT 1",
                        (phone_no,)
                    )
                else:
                    cursor.execute(
                        "SELECT TOP 1 task_type FROM pending_followups WHERE phone_no = ? ORDER BY created_at DESC",
                        (phone_no,)
                    )
            row = cursor.fetchone()
            return row[0] if row else None
    except Exception as e:
        logging.error(f"Error getting pending task type: {e}")
        return None


def update_pending_task_type(phone_no: str, new_type: str, reservation_id: Optional[str] = None):
    try:
        with get_conn() as conn:
            cursor = conn.cursor()
            if reservation_id:
                cursor.execute(
                    "UPDATE pending_followups SET task_type = ? WHERE phone_no = ? AND reservation_id = ?",
                    (new_type, phone_no, reservation_id)
                )
            else:
                cursor.execute(
                    "UPDATE pending_followups SET task_type = ? WHERE phone_no = ?",
                    (new_type, phone_no)
                )
            conn.commit()
    except Exception as e:
        logging.error(f"Error updating task type: {e}")


def remove_pending_followup(phone_no: str, reservation_id=None):
    try:
        phone_no = clean_wa_id(phone_no)
        with get_conn() as conn:
            cursor = conn.cursor()
            if reservation_id:
                cursor.execute("DELETE FROM pending_followups WHERE phone_no = ? AND reservation_id = ?", (phone_no, reservation_id))
            else:
                cursor.execute("DELETE FROM pending_followups WHERE phone_no = ?", (phone_no,))
            conn.commit()
    except Exception as e:
        logging.error(f"Remove pending followup error: {e}")


# -------------------------------------------------------
# Notification Logs
# -------------------------------------------------------
def log_notification(phone_no: str, notification_type: str, status: str, response_detail: str):
    try:
        with get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO notification_logs (phone_no, notification_type, status, response_detail)
                VALUES (?, ?, ?, ?)
            """, (phone_no, notification_type, status, response_detail))
            conn.commit()
    except Exception as e:
        logging.error(f"Add notification log error: {e}")


# -------------------------------------------------------
# Welcome Sent Tracking
# -------------------------------------------------------
def has_sent_welcome_followup(phone_no: str, reservation_id: str) -> bool:
    try:
        phone_no = clean_wa_id(phone_no)
        with get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 1 FROM welcome_sent
                WHERE phone_no = ? AND reservation_id = ?
            """, (phone_no, reservation_id))
            result = cursor.fetchone()
            return result is not None
    except Exception as e:
        logging.error(f"Check welcome_sent error: {e}")
        return False


def mark_welcome_followup_sent(phone_no: str, reservation_id: str):
    try:
        phone_no = clean_wa_id(phone_no)
        with get_conn() as conn:
            cursor = conn.cursor()
            if USE_SQLITE:
                cursor.execute("""
                    INSERT OR IGNORE INTO welcome_sent (phone_no, reservation_id)
                    VALUES (?, ?)
                """, (phone_no, reservation_id))
            else:
                cursor.execute("""
                    IF NOT EXISTS (SELECT 1 FROM welcome_sent WHERE phone_no = ? AND reservation_id = ?)
                        INSERT INTO welcome_sent (phone_no, reservation_id) VALUES (?, ?)
                """, (phone_no, reservation_id, phone_no, reservation_id))
            conn.commit()
    except Exception as e:
        logging.error(f"Mark welcome_sent error: {e}")


def can_send_welcome_followup(phone_no: str, reservation_id: str) -> bool:
    if not redis_client:
        return not has_sent_welcome_followup(phone_no, reservation_id)

    phone_no = clean_wa_id(phone_no)
    lock_key = f"chatbot:welcome_lock:{phone_no}:{reservation_id}"

    acquired = redis_client.set(lock_key, "1", nx=True)

    if acquired:
        mark_welcome_followup_sent(phone_no, reservation_id)
        return True

    return False


# -------------------------------------------------------
# Guest Reservations
# -------------------------------------------------------
def save_reservation_meta(phone_no: str, booking_id: str, booking_code: str = "", meta_data: Optional[dict] = None) -> bool:
    try:
        phone_no = clean_wa_id(phone_no)
        json_meta = json.dumps(meta_data) if meta_data else None
        
        with get_conn() as conn:
            cursor = conn.cursor()
            if USE_SQLITE:
                cursor.execute("""
                    INSERT INTO guest_reservations (phone_no, booking_id, booking_code, meta_data)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(phone_no, booking_id) DO UPDATE SET
                        booking_code = excluded.booking_code,
                        meta_data = excluded.meta_data
                """, (phone_no, booking_id, booking_code, json_meta))
            else:
                cursor.execute("""
                    MERGE guest_reservations AS target
                    USING (VALUES (?, ?, ?, ?)) AS source (phone_no, booking_id, booking_code, meta_data)
                    ON target.phone_no = source.phone_no AND target.booking_id = source.booking_id
                    WHEN MATCHED THEN
                        UPDATE SET 
                            booking_code = source.booking_code,
                            meta_data = source.meta_data
                    WHEN NOT MATCHED THEN
                        INSERT (phone_no, booking_id, booking_code, meta_data)
                        VALUES (source.phone_no, source.booking_id, source.booking_code, source.meta_data);
                """, (phone_no, booking_id, booking_code, json_meta))
            conn.commit()
        return True
    except Exception as e:
        logging.error(f"Error storing reservation meta: {e}")
        return False


def get_reservation_meta(phone_no: Optional[str] = None) -> list:
    try:
        with get_conn() as conn:
            cursor = conn.cursor()
            if phone_no:
                phone_no = clean_wa_id(phone_no)
                cursor.execute(
                    "SELECT phone_no, booking_id, booking_code, created_at, meta_data FROM guest_reservations WHERE phone_no = ? ORDER BY created_at DESC",
                    (phone_no,)
                )
            else:
                cursor.execute(
                    "SELECT phone_no, booking_id, booking_code, created_at, meta_data FROM guest_reservations ORDER BY created_at DESC"
                )

            rows = cursor.fetchall()

            return [
                {
                    "phone_no": row[0],
                    "booking_id": row[1],
                    "booking_code": row[2],
                    "created_at": row[3],
                    "meta_data": json.loads(row[4]) if row[4] else {}
                } for row in rows
            ]
    except Exception as e:
        logging.error(f"Error retrieving reservation meta: {e}")
        return []
