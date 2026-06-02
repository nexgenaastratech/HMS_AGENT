
import logging

from app.services.agent import run_agent
from app.services.whatsapp import send_text


def process_message(data: dict) -> None:
    try:
        entry = data.get("entry", [])
        if not entry:
            return
        changes = entry[0].get("changes", [])
        if not changes:
            return
        value = changes[0].get("value", {})

        # Delivery status updates — no reply needed
        if "statuses" in value:
            for status in value["statuses"]:
                if status["status"] == "failed":
                    logging.error(f"WhatsApp delivery failed: {status.get('errors')}")
                else:
                    logging.info(f"Message status: {status['status']}")
            return

        if "messages" not in value:
            return

        msg        = value["messages"][0]
        wa_id      = msg["from"]
        msg_type   = msg.get("type")
        guest_name = value.get("contacts", [])[0].get("profile", {}).get("name", wa_id)

        if msg_type not in ("text", "interactive"):
            return

        # Extract text from either plain text or interactive button/list reply
        user_text = ""
        if msg_type == "text":
            user_text = msg.get("text", {}).get("body", "").strip()
        elif msg_type == "interactive":
            interactive = msg.get("interactive", {})
            user_text = (
                interactive.get("list_reply") or interactive.get("button_reply", {})
            ).get("title", "")

        if not user_text:
            return

        logging.info(f"[Webhook] {guest_name} ({wa_id}): {user_text}")

        # Everything goes to the agent — it handles all scenarios
        response = run_agent(
            wa_id=wa_id,
            guest_name=guest_name,
            user_text=user_text,
            msg_type=msg_type,
        )

        if response:
            send_text(wa_id, response)

    except Exception:
        logging.exception("[Webhook] Error in process_message")
