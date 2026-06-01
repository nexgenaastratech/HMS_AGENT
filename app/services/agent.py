# app/services/agent.py

import json
import logging
from datetime import datetime, timedelta

import redis

from app.core.config import settings
from app.services.ai import call_azure_openai_api
from app.services.memory import (
    get_conversation,
    store_message,
    get_pending_task_type,
    remove_pending_followup,
    get_reservation_meta,
    log_notification,
)
from app.services.hms import (
    notify_hotel_staff,
    get_room_list,
    get_all_query_request,
    mark_request_completed,
    check_reserved_status,
    add_special_request,
)
from app.services.whatsapp import (
    send_text,
    send_image,
    send_services_request,
    send_interactive_list,
)
from app.rag import RAGSystem

rag_system = RAGSystem()

redis_client = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    password=settings.REDIS_PASSWORD,
    decode_responses=True,
)



# ---------------------------------------------------------------------------
# Greeting logic (replaces greeting block in bot.py process_message)
# ---------------------------------------------------------------------------

def handle_greeting(wa_id: str, guest_name: str) -> bool:
    """
    Sends the correct greeting based on guest reservation status.
    Returns True if greeting was sent (caller should return early).
    Replaces the greeting block in bot.py.
    """
    try:
        # Check active rooms
        response_data = get_room_list(wa_id)
        rooms = []
        if isinstance(response_data, dict):
            rooms = response_data.get("data", [])
        elif isinstance(response_data, list):
            rooms = response_data

        if rooms:
            # --- EXISTING GUEST: currently checked in ---
            utc_now  = datetime.utcnow()
            ist_now  = utc_now + timedelta(hours=5, minutes=30)
            hour     = ist_now.hour

            if 5 <= hour < 12:
                time_greeting = "Good Morning"
            elif 12 <= hour < 17:
                time_greeting = "Good Afternoon"
            elif 17 <= hour < 22:
                time_greeting = "Good Evening"
            else:
                time_greeting = "Hello"

            greeting_text = f"{time_greeting} {guest_name}!\nHow can I assist you today?"
            send_text(wa_id, greeting_text)
            store_message(wa_id, "assistant", greeting_text)
            send_services_request(wa_id)

        elif check_reserved_status(wa_id):
            # --- PRE-ARRIVAL: confirmed future reservation ---
            welcome_msg = (
                "*Your stay at Hotel Harriet is confirmed!* 🏨\n\n"
                "We see you have a reservation for your upcoming visit to Rameswaram.\n"
                "We are excitedly preparing for your arrival.\n\n"
                "During your stay, you will enjoy:\n"
                "• Complimentary breakfast\n"
                "• Free Wi-Fi\n"
                "• Car parking\n"
                "• Well-maintained rooms and thoughtful amenities\n\n"
                "If you need any assistance before checking in, just ask!\n"
                "🌐 https://www.hotelharriet.com/\n"
                "📍 https://maps.app.goo.gl/42u62826558844448\n\n"
                "We look forward to welcoming you! 🙏"
            )
            send_text(wa_id, welcome_msg)
            store_message(wa_id, "assistant", welcome_msg)

        else:
            # --- NEW VISITOR: no reservation yet ---
            welcome_msg = (
                "*Welcome to Hotel Harriet* 🏨\n\n"
                "We're delighted to assist you with your stay in Rameswaram.\n\n"
                "At *Hotel Harriet*, we offer comfortable accommodation along with:\n"
                "• Complimentary breakfast\n"
                "• Free Wi-Fi\n"
                "• Car parking\n"
                "• Well-maintained rooms and thoughtful amenities\n\n"
                "To help us serve you better, please share your stay dates and number of guests.\n"
                "For more information, visit our website:\n"
                "🌐 https://www.hotelharriet.com/\n\n"
                "We look forward to welcoming you! 🙏"
            )
            send_text(wa_id, welcome_msg)
            send_location(wa_id)
            store_message(wa_id, "assistant", welcome_msg)

        return True

    except Exception as e:
        logging.exception(f"[Agent] handle_greeting error for {wa_id}: {e}")
        return False


# ---------------------------------------------------------------------------
# Special request follow-up (replaces pending_type logic in bot.py)
# ---------------------------------------------------------------------------

def handle_pending_followup(wa_id: str, user_text: str) -> bool:
    """
    Checks if there is a pending follow-up task for this guest and handles it.
    Returns True if handled (caller should return early), False to continue normally.
    Replaces the pending_type block in bot.py.
    """
    pending_type = get_pending_task_type(wa_id)
    if not pending_type:
        return False

    remove_pending_followup(wa_id)
    logging.info(f"[Agent] Handling pending follow-up '{pending_type}' for {wa_id}")

    if pending_type in ("get_special_request", "reminder_special_request"):
        res_data   = get_reservation_meta(wa_id)
        booking_id = res_data[0].get("booking_id") if res_data else None

        if not booking_id:
            logging.warning(f"[Agent] No booking found for {wa_id} — cannot save special request.")
            return False

        # Ask AI if this message is a real specific request
        analysis_resp = call_azure_openai_api(
            messages=[
                {"role": "system", "content": "You are a hotel request analyzer."},
                {"role": "user", "content": (
                    f"Classify the guest message as 'get_special_request' if it contains a specific "
                    f"pre-arrival need (early check-in, pickup, extra bed, dietary, etc.), "
                    f"or 'other' if it is a greeting or generic acknowledgment.\n\n"
                    f"Message: \"{user_text}\"\n\nReply ONLY with 'get_special_request' or 'other'."
                )}
            ],
            max_tokens=10,
        )

        is_real = False
        if analysis_resp and "choices" in analysis_resp:
            result   = analysis_resp["choices"][0]["message"]["content"].strip().lower()
            is_real  = "get_special_request" in result

        if is_real:
            add_special_request(booking_id, user_text)
            confirm = "Thank you! I've shared your request with our front desk team. They will assist you shortly."
            send_text(wa_id, confirm)
            store_message(wa_id, "assistant", confirm)
            logging.info(f"[Agent] Special request saved for {wa_id}: '{user_text}'")
            return True
        else:
            # Not a specific request — fall through to normal agent
            logging.info(f"[Agent] Message not a special request — continuing to agent.")
            return False

    # checkin or other pending types — cancel and continue normally
    return False


# ---------------------------------------------------------------------------
# YES / NO button handler (replaces YES/NO block in bot.py)
# ---------------------------------------------------------------------------

def handle_yes_no(wa_id: str, user_text: str, msg_type: str, msg_context_id: str) -> bool:
    """
    Handles YES/NO interactive button replies for request completion.
    Returns True if fully handled, False to continue to agent.
    """
    answer = user_text.strip().upper()
    if answer not in ("YES", "NO"):
        return False
    if msg_type != "interactive":
        return False

    # Fetch open requests
    reqs_data     = get_all_query_request(wa_id)
    requests_list = _extract_requests_list(reqs_data)

    # Find the matching open request from Redis active_request
    try:
        active_raw  = redis_client.get(f"active_request:{wa_id}")
        active_req  = json.loads(active_raw) if active_raw else None
        active_room = active_req.get("room") if active_req else None
    except Exception:
        active_req  = None
        active_room = None

    target_req_id = None
    for req in requests_list:
        if not isinstance(req, dict):
            continue
        r_status = _get_request_status(req)
        if r_status in ("completed", "closed"):
            continue
        r_room = str(req.get("roomNumber", "")).upper()
        r_id   = req.get("queryRequestId") or req.get("requestId")
        if active_room and r_room == str(active_room).upper():
            target_req_id = r_id
            break
        if not target_req_id:
            target_req_id = r_id

    if not target_req_id:
        return False

    if answer == "YES":
        success = mark_request_completed(target_req_id)
        if success:
            bot_reply    = "Thank you! Your request has been marked as completed. We are glad we could help."
            followup_msg = "If you need anything else—food, services, or assistance—just send us a message. We're always happy to help. 😊"
            send_text(wa_id, bot_reply)
            send_text(wa_id, followup_msg)
            store_message(wa_id, "assistant", bot_reply)
            store_message(wa_id, "assistant", followup_msg)
            redis_client.delete(f"active_request:{wa_id}")
            send_services_request(wa_id)
        else:
            msg = "We tried to update the status but encountered an issue. Please contact reception if needed."
            send_text(wa_id, msg)
            store_message(wa_id, "assistant", msg)
        return True

    elif answer == "NO":
        mark_request_completed(target_req_id, status="false")
        bot_reply = "We are sorry to hear that. Our team has been notified and will attend to you shortly."
        send_text(wa_id, bot_reply)
        store_message(wa_id, "assistant", bot_reply)
        return True

    return False



def handle_pending_room_selection(wa_id: str, user_text: str) -> bool:
    """
    If a room selector was sent and the guest replied with a room number,
    completes the pending request.
    Returns True if handled, False to continue to agent.
    Replaces WAITING_FOR_ROOM stage logic in bot.py.
    """
    try:
        raw = redis_client.get(f"pending_request:{wa_id}")
        if not raw:
            return False

        pending     = json.loads(raw)
        req_type    = pending.get("type")
        req_message = pending.get("message")

        if not req_type or not req_message:
            return False

        room_number = user_text.strip().upper()

        # Complete the request
        result = _execute_tool(
            "complete_request_with_confirmation",
            {"request_type": req_type, "message": req_message, "room_number": room_number},
            wa_id,
        )

        store_message(wa_id, "user",      f"Room {room_number}")
        store_message(wa_id, "assistant", f"Request completed for Room {room_number}")

        logging.info(f"[Agent] Pending room selection completed: {result}")
        return True

    except Exception as e:
        logging.exception(f"[Agent] handle_pending_room_selection error: {e}")
        return False


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_guest_rooms",
            "description": (
                "Fetches the list of rooms currently booked by this guest. "
                "Call this first whenever you need a room number and the guest has not stated one."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_room_selector",
            "description": (
                "Sends an interactive WhatsApp room selection list to the guest. "
                "Use when the guest has multiple rooms and you need them to pick one. "
                "If only 1 room exists, skip this and call complete_request_with_confirmation directly."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "rooms":           {"type": "array", "items": {"type": "string"}, "description": "Room numbers to show."},
                    "request_type":    {"type": "string", "enum": ["food", "service", "complaint", "late_checkout"]},
                    "request_message": {"type": "string", "description": "What the guest originally asked for."},
                },
                "required": ["rooms", "request_type", "request_message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "complete_request_with_confirmation",
            "description": (
                "Notifies hotel staff AND sends the branded confirmation image+text to the guest. "
                "Call once you have both the request details AND the confirmed room number."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "request_type": {"type": "string", "enum": ["food", "service", "complaint", "late_checkout"]},
                    "message":      {"type": "string", "description": "Full description of the request."},
                    "room_number":  {"type": "string", "description": "Confirmed room number e.g. '101'."},
                },
                "required": ["request_type", "message", "room_number"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_open_requests",
            "description": "Gets all open service requests for this guest. Use when guest says issue is resolved or still ongoing.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mark_request_done",
            "description": "Marks a service request as completed or re-opens it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "request_id": {"type": "string"},
                    "resolved":   {"type": "boolean", "description": "True = completed, False = re-open."},
                },
                "required": ["request_id", "resolved"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_guest_special_request",
            "description": (
                "Saves a pre-arrival special request (early check-in, pickup, dietary, extra bed). "
                "Use for guests with a confirmed future booking."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "request_text": {"type": "string"},
                },
                "required": ["request_text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_knowledge_base",
            "description": (
                "Searches hotel knowledge base and Rameswaram travel info. "
                "Use for questions about hotel amenities, policies, local attractions, or travel."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_service_menu",
            "description": "Sends the interactive services menu. Use after greeting an existing guest or when guest asks what help is available.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
    "type": "function",
    "function": {
        "name": "complete_request_with_confirmation",
        "description": (
            "Notifies hotel staff AND sends a confirmation message to the guest. "
            "Call once you have the request details and confirmed room number. "
            "You will write the confirmation_message yourself based on the request type."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "request_type": {
                    "type": "string",
                    "description": (
                        "Category of the request — decide based on what the guest needs. "
                        "Common values: 'food', 'service', 'complaint', 'late_checkout', 'laundry'. "
                        "You can use any value that best describes the request."
                    ),
                },
                "message": {
                    "type": "string",
                    "description": "Full description of the guest's request, in their words.",
                },
                "room_number": {
                    "type": "string",
                    "description": "Confirmed room number e.g. '101' or 'G06'.",
                },
                "confirmation_message": {
                    "type": "string",
                    "description": (
                        "The confirmation message to send to the guest. "
                        "Write it yourself — warm, concise, branded as Hotel Harriet. "
                        "Always end with: 'If you need anything else, just ask!'\n\n"
                        "Examples:\n"
                        "food → 'We have received your order: [msg] for Room [room]. "
                        "Our Restaurant Team will assist you shortly.'\n"
                        "service → 'Request for [msg] in Room [room] confirmed. "
                        "Housekeeping will arrive shortly.'\n"
                        "complaint → 'Your complaint: [msg] for Room [room] received. "
                        "The Front Desk team will assist you shortly.'\n"
                        "laundry → 'Laundry pickup request for Room [room] received. "
                        "Our team will collect shortly.'\n"
                        "Follow the same pattern for any new request type."
                    ),
                },
            },
            "required": ["request_type", "message", "room_number", "confirmation_message"],
        },
    },
},
]

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

AGENT_SYSTEM_PROMPT = """
You are the AI concierge for Hotel Harriet in Rameswaram, India.
You assist hotel guests via WhatsApp in a warm, concise, and helpful manner.

## What you can do (use the provided tools):
- Handle food orders, housekeeping, complaints, and late checkout requests.
- Answer questions about the hotel and local Rameswaram travel.
- Log pre-arrival special requests for guests with future bookings.
- Mark service requests resolved when guests confirm.

## Rules:
1. For ANY service request (food, housekeeping, complaint, late checkout):
   a. Call get_guest_rooms first — UNLESS the guest stated a room number explicitly.
   b. If 1 room → call complete_request_with_confirmation directly.
   c. If multiple rooms → call send_room_selector and wait for guest to pick.
   d. If no rooms → tell the guest no active booking was found and suggest reception.
2. Never make up hotel information — use search_knowledge_base.
3. Keep responses short and friendly. No bullet-point overload.
4. After completing a request, DO NOT send another text — the confirmation image/text is already sent by the tool.
5. If a guest says 'yes' to a completion prompt, call get_open_requests then mark_request_done.
6. Do not ask for information you can get via a tool.

## Confirmation Messages:
When you call complete_request_with_confirmation, always write
the confirmation_message yourself following this pattern:

  "[Acknowledgment of what was received] for Room [room].
   [Which team will handle it] will assist you shortly.
   If you need anything else, just ask!"

Be warm, concise, and professional. Always mention the room number.
Never use generic text like 'your request has been received' alone —
always specify what the request was.

## CRITICAL CLASSIFICATION RULE:
Before responding, always ask yourself:

  Is the guest making a REQUEST that needs staff action?
    → call complete_request_with_confirmation or send_room_selector

  Is the guest asking a QUESTION that needs information?
    → call search_knowledge_base

  Is the guest just having a CONVERSATION? (thanks, ok, yes, greeting)
    → reply directly, no tool needed

## Examples to guide you:
  "I need towels"              → ACTION  → complete_request_with_confirmation
  "do you have towels?"        → QUESTION → search_knowledge_base
  "AC not working"             → ACTION  → complete_request_with_confirmation
  "does the room have AC?"     → QUESTION → search_knowledge_base
  "send me idli"               → ACTION  → complete_request_with_confirmation
  "what food do you serve?"    → QUESTION → search_knowledge_base
  "train from Chennai"         → QUESTION → search_knowledge_base
  "thank you"                  → CONVERSATION → reply directly

## Other rules:
1. For ACTION requests: call get_guest_rooms first if room not stated.
2. Never make up hotel info — always use search_knowledge_base.
3. After complete_request_with_confirmation — do NOT send extra text.
   The confirmation image is already sent by the tool.
4. Keep replies short and friendly.
"""

## Guest context will be injected at runtime (name, room status).

# ---------------------------------------------------------------------------
# Tool executor
# ---------------------------------------------------------------------------

def _execute_tool(tool_name: str, args: dict, wa_id: str) -> dict:
    logging.info(f"[Agent] Tool: '{tool_name}' | Args: {args}")

    if tool_name == "get_guest_rooms":
        response_data = get_room_list(wa_id)
        rooms = []
        if isinstance(response_data, dict):
            rooms = response_data.get("data", [])
        elif isinstance(response_data, list):
            rooms = response_data
        # Normalise to list of room number strings
        room_numbers = []
        for r in rooms:
            num = r.get("roomNumber") or r.get("roomNo") if isinstance(r, dict) else r
            if num:
                room_numbers.append(str(num).upper())
        return {"rooms": room_numbers}

    elif tool_name == "send_room_selector":
        rooms           = args["rooms"]
        request_type    = args["request_type"]
        request_message = args["request_message"]

        rows = [{"id": r, "title": r} for r in rooms]
        send_interactive_list(
            wa_id=wa_id,
            header_text="Select Your Room",
            body_text="Please tap your room number to proceed.",
            button_text="Select Room",
            sections=[{"title": "Your Rooms", "rows": rows}],
            footer_text="Hotel Harriet",
        )
        # Save pending request so next message (room tap) can complete it
        redis_client.setex(
            f"pending_request:{wa_id}",
            60 * 30,
            json.dumps({"type": request_type, "message": request_message}),
        )
        return {"sent": True, "waiting_for": "room_selection", "rooms_shown": rooms}

    elif tool_name == "complete_request_with_confirmation":
        req_type = args["request_type"]
        message  = args["message"]
        room     = args["room_number"]
        con_text = args["confirmation_text"]

        success = notify_hotel_staff(wa_id, message, req_type, room)
        log_notification(wa_id, req_type, "sent" if success else "failed", message)
        send_text(wa_id, con_text)
        logging.info(f"[Agent] Confirmation sent for '{req_type}' Room {room}")

        # 3. Save active request for YES/NO follow-up
        redis_client.setex(
            f"active_request:{wa_id}",
            60 * 60 * 6,
            json.dumps({"room": room, "type": req_type}),
        )
        redis_client.delete(f"pending_request:{wa_id}")

        return {"success": bool(success), "room": room, "type": req_type}

    elif tool_name == "get_open_requests":
        reqs_data     = get_all_query_request(wa_id)
        requests_list = _extract_requests_list(reqs_data)
        open_reqs     = [
            r for r in requests_list
            if isinstance(r, dict) and _get_request_status(r) not in ("completed", "closed")
        ]
        return {"open_requests": open_reqs}

    elif tool_name == "mark_request_done":
        request_id = args["request_id"]
        resolved   = args.get("resolved", True)
        success    = mark_request_completed(request_id, status="true" if resolved else "false")
        if resolved:
            redis_client.delete(f"active_request:{wa_id}")
        return {"success": bool(success), "request_id": request_id, "resolved": resolved}

    elif tool_name == "add_guest_special_request":
        request_text = args["request_text"]
        res_data     = get_reservation_meta(wa_id)
        booking_id   = res_data[0].get("booking_id") if res_data else None
        if not booking_id:
            return {"success": False, "error": "No upcoming booking found."}
        success = add_special_request(booking_id, request_text)
        return {"success": bool(success)}

    elif tool_name == "search_knowledge_base":
        query = args["query"]
        try:
            result = rag_system.get_context(query)
            return {"answer": result}
        except Exception as e:
            logging.error(f"[Agent] RAG error: {e}")
            return {"answer": "Unable to retrieve that information. Please contact reception."}

    elif tool_name == "send_service_menu":
        send_services_request(wa_id)
        return {"sent": True}

    else:
        logging.warning(f"[Agent] Unknown tool: {tool_name}")
        return {"error": f"Unknown tool: {tool_name}"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_requests_list(reqs_data) -> list:
    if isinstance(reqs_data, list):
        return reqs_data
    if isinstance(reqs_data, dict):
        data_node = reqs_data.get("data", {})
        if isinstance(data_node, list):
            return data_node
        if isinstance(data_node, dict):
            return data_node.get("dailyIssuesLog") or data_node.get("docs") or []
    return []


def _get_request_status(req: dict) -> str:
    status = str(req.get("queryStatus", "")).lower()
    if not status or status == "none":
        status_obj = req.get("status", {})
        if isinstance(status_obj, dict):
            status = str(status_obj.get("state", "")).lower()
    return status


# ---------------------------------------------------------------------------
# Main agent loop
# ---------------------------------------------------------------------------

def run_agent(wa_id: str, guest_name: str, user_text: str) -> str | None:
    """
    Core agentic loop. Replaces the full process_message business logic.
    Returns final text response, or None if response was already sent by a tool.
    """
    store_message(wa_id, "user", user_text)
    conversation = get_conversation(wa_id)

    # Inject guest context into system prompt
    system_prompt = AGENT_SYSTEM_PROMPT + f"\n\n## Current Guest: {guest_name} | Phone: {wa_id}"

    messages = [{"role": "system", "content": system_prompt}] + conversation

    MAX_ITERATIONS = 6
    final_response = None
    tool_sent_response = False  # tracks if a tool already sent a WhatsApp message

    for iteration in range(MAX_ITERATIONS):
        logging.info(f"[Agent] Iteration {iteration + 1} for {wa_id}")

        api_response = call_azure_openai_api(
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            max_tokens=50,
        )

        if not api_response or "choices" not in api_response:
            logging.error("[Agent] Empty API response.")
            final_response = "I'm having trouble right now. Please contact reception."
            break

        choice           = api_response["choices"][0]
        finish_reason    = choice.get("finish_reason")
        assistant_message = choice["message"]
        messages.append(assistant_message)

        if finish_reason == "tool_calls":
            tool_calls = assistant_message.get("tool_calls", [])

            for tc in tool_calls:
                tool_name = tc["function"]["name"]
                try:
                    tool_args = json.loads(tc["function"]["arguments"])
                except json.JSONDecodeError:
                    tool_args = {}

                tool_result = _execute_tool(tool_name, tool_args, wa_id)

                # These tools send their own WhatsApp messages — agent text not needed
                if tool_name in ("complete_request_with_confirmation", "send_room_selector", "send_service_menu"):
                    tool_sent_response = True

                messages.append({
                    "role":         "tool",
                    "tool_call_id": tc["id"],
                    "content":      json.dumps(tool_result),
                })

            continue

        elif finish_reason == "stop":
            final_response = assistant_message.get("content", "").strip()
            break

        else:
            logging.warning(f"[Agent] Unexpected finish_reason: {finish_reason}")
            final_response = "Something went wrong. Please try again."
            break

    if not final_response and not tool_sent_response:
        final_response = "I'm unable to process your request right now. Please contact reception."

    if final_response:
        store_message(wa_id, "assistant", final_response)

    # If tool already sent the response (image/confirmation), suppress agent text
    return None if tool_sent_response else final_response