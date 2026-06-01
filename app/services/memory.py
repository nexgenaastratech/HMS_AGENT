import pyodbc
import json
import logging
import redis
from typing import Optional
from app.core.config import settings

# Initialize Redis client for production idempotency/locking
redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True) if settings.REDIS_URL else None


def get_conn():
    """Returns a fresh pyodbc connection to SQL Server."""
    return pyodbc.connect(settings.SQL_SERVER_CONN)


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

        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='conversations' AND xtype='U')
            CREATE TABLE conversations (
                phone_no NVARCHAR(50) PRIMARY KEY,
                conversation NVARCHAR(MAX),
                task_type NVARCHAR(100),
                created_at DATETIME DEFAULT GETDATE()
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
                created_at DATETIME DEFAULT GETDATE(),
                PRIMARY KEY (phone_no, booking_id)
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
            # Added updated_at tracking
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
            cursor.execute("""
                MERGE pending_followups AS target
                USING (VALUES (?, ?, ?)) AS source (phone_no, reservation_id, task_type)
                ON target.phone_no = source.phone_no AND target.reservation_id = source.reservation_id
                WHEN MATCHED THEN
                    UPDATE SET task_type = source.task_type
                WHEN NOT MATCHED THEN
                    INSERT (phone_no, reservation_id, task_type)
                    VALUES (source.phone_no, source.reservation_id, source.task_type);
            """, (phone_no, str(reservation_id), task_type))
            conn.commit()
    except Exception as e:
        logging.error(f"Add pending followup error: {e}")


def is_pending_followup(phone_no: str, reservation_id=None) -> bool:
    try:
        phone_no = clean_wa_id(phone_no)
        with get_conn() as conn:
            cursor = conn.cursor()
            if reservation_id:
                cursor.execute("SELECT 1 FROM pending_followups WHERE phone_no = ? AND reservation_id = ?", (phone_no, str(reservation_id)))
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
                    (str(phone_no), str(reservation_id))
                )
            else:
                cursor.execute(
                    "SELECT TOP 1 task_type FROM pending_followups WHERE phone_no = ? ORDER BY created_at DESC",
                    (str(phone_no),)
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
                    (new_type, str(phone_no), str(reservation_id))
                )
            else:
                cursor.execute(
                    "UPDATE pending_followups SET task_type = ? WHERE phone_no = ?",
                    (new_type, str(phone_no))
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
                cursor.execute("DELETE FROM pending_followups WHERE phone_no = ? AND reservation_id = ?", (phone_no, str(reservation_id)))
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
            """, (phone_no, notification_type, status, str(response_detail)))
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
