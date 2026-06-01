import logging
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Header, Query
from pydantic import BaseModel, Field
from typing import Optional, List
from app.core.security import verify_api_key
from app.core.config import settings
from app.services.whatsapp import send_template, send_text, send_interactive_cta_url, send_image, send_video, send_document, send_interactive_buttons
from app.services.button_keys import store_button_keys
import httpx
import json
import sys
import uuid
from app.api.worker import send_test_followup, send_welcome_followup
from app.services.memory import add_pending_followup, log_notification
# Configure logging
logger = logging.getLogger("notification_logger")
logger.setLevel(logging.DEBUG)  # log everything DEBUG and above

# File Handler
file_handler = logging.FileHandler("notifications.log")
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# Stream Handler (for Render / Console)
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)

class NotificationRequest(BaseModel):
    type: str = Field(..., alias="Type") # text, document, template, cta, image, video, list
    
    model_config = {
        "populate_by_name": True,
    }
    guest_phone: str
    message: Optional[str] = None
    invoice_url: Optional[str] = None
    template_name: Optional[str] = ""
    template_lang: Optional[str] = "en"
    template_params: Optional[List[str]] = []
    button_params: Optional[List[str]] = []
    header_document_url: Optional[str] = None
    header_video_url: Optional[str] = None
    header_image_url: Optional[str] = None
    header_text: Optional[str] = None
    flow_token: Optional[str] = None
    button_text: Optional[str] = None
    button_url: Optional[str] = None
    footer_text: Optional[str] = None
    filename: Optional[str] = None # For document filename
    reservation_id: Optional[str] = "id_not_set"

class sendReservationDataMeta(BaseModel):
    guest_phone: str
    booking_id: str
    booking_code: str
    

router = APIRouter()

@router.post("/test-followup")
async def test_followup(
    request: NotificationRequest,
    api_key: str = Header(..., alias="api-key")
):
    if api_key != settings.API_KEY:
         raise HTTPException(status_code=401, detail="Invalid API Key")
    
    logger.info(f"Starting test followup flow for: {request.guest_phone}")
    
    # 1. Send the initial message immediately
    from app.services.whatsapp import send_text
    response_msg = request.message or "This is a test. If you don't reply in 60 seconds, I will ping you again!"
    send_text(request.guest_phone, response_msg)
    
    # 2. Add pending state in memory
    add_pending_followup(request.guest_phone, task_type="test")
    
    # 3. Schedule the celery task in exactly 60 seconds
    send_test_followup.apply_async(args=[request.guest_phone], countdown=60)
    
    return {"status": "success", "detail": "Test initiated! Countdown started ⏳"}

@router.post("/send-notification")
async def send_notification(
    request: NotificationRequest, 
    background_tasks: BackgroundTasks, 
    api_key: str = Header(..., alias="api-key")
):
    if api_key != settings.API_KEY:
         raise HTTPException(status_code=401, detail="Invalid API Key")

    logger.info(f"Received notification request: {request.json()}")
    
    if request.reservation_id == "id_not_set" or not request.reservation_id:
        request.reservation_id = f"auto_{uuid.uuid4().hex[:8]}"
        logger.info(f"Generated automatic unique reservation_id: {request.reservation_id}")

    try:
        headers = {
            "Authorization": f"Bearer {settings.WHATSAPP_TOKEN}",
            "Content-Type": "application/json"
        }
        whatsapp_api_url = f"https://graph.facebook.com/{settings.VERSION}/{settings.PHONE_NUMBER_ID}/messages"
        logger.debug(f"WhatsApp API URL: {whatsapp_api_url}")

        # 1. TEMPLATE
        if request.type == "template":
            logger.info(f"Sending template: {request.template_name} to {request.guest_phone}")
            
            # Button Keys Logic
            if request.template_name == "welcome_in_checkin" and request.button_params:
                button_keys = {}
                for idx, param in enumerate(request.button_params):
                    param_str = str(param)
                    if "food" in param_str.lower() or idx == 0:
                        button_keys["food"] = param_str
                    elif "service" in param_str.lower() or idx == 1:
                        button_keys["service"] = param_str

                if button_keys:
                    store_button_keys(request.guest_phone, button_keys)
                    logger.debug(f"Stored button keys: {button_keys}")
            
            template_payload = {
                "messaging_product": "whatsapp",
                "to": request.guest_phone,
                "type": "template",
                "template": {
                    "name": request.template_name,
                    "language": {"code": request.template_lang},
                }
            }
            components = []
       
        if request.type == "template":
            if request.template_name =="precheckin_details":
                logger.info("Stopping: We are not sending the precheckin template.")
                return {"status": "skipped", "detail": "Precheckin is blocked"}
                
            from app.services.memory import clean_wa_id
            welcome_templates = ["welcome_hotelharriet"]
            
            if request.template_name in welcome_templates:
                wa_id = clean_wa_id(request.guest_phone)
                
                from app.services.memory import can_send_welcome_followup
                
                trigger_followup = False
                if can_send_welcome_followup(wa_id, request.reservation_id):
                    trigger_followup = True
                else:
                    logger.info(f"Duplicate reservation event for {wa_id} | {request.reservation_id}. Skipping.")

            # Headers
            if request.header_document_url:
                doc_filename = request.filename or "Booking_Confirmation.pdf"
                components.append({
                    "type": "header",
                    "parameters": [{"type": "document", "document": {"link": request.header_document_url, "filename": doc_filename}}]
                })
            elif request.header_video_url:
                components.append({"type": "header", "parameters": [{"type": "video", "video": {"link": request.header_video_url}}]})
            elif request.header_image_url:
                components.append({"type": "header", "parameters": [{"type": "image", "image": {"link": request.header_image_url}}]})
            elif request.header_text:
                components.append({"type": "header", "parameters": [{"type": "text", "text": request.header_text}]})

            # Body Params
            if request.template_params:
                parameters = [{"type": "text", "text": str(p)} for p in request.template_params]
                components.append({"type": "body", "parameters": parameters})
                logger.debug(f"Template body parameters: {parameters}")

            # Button Params
            if request.button_params:
                for idx, token_val in enumerate(request.button_params):
                    formatted_payload = token_val if token_val.startswith("?") or token_val.startswith("&") else f"&token={token_val}"
                    components.append({
                        "type": "button",
                        "sub_type": "url",
                        "index": str(idx),
                        "parameters": [{"type": "text", "text": formatted_payload}]
                    })
                logger.debug(f"Button parameters added: {request.button_params}")

            # Flow Button
            if request.flow_token:
                idx = str(len(request.button_params)) if request.button_params else "0"
                components.append({
                    "type": "button",
                    "sub_type": "flow",
                    "index": idx,
                    "parameters": [{"type": "action", "action": {"flow_token": request.flow_token}}]
                })
                logger.debug(f"Flow token added: {request.flow_token}")

            if components:
                template_payload["template"]["components"] = components

            logger.info(f"Sending payload: {json.dumps(template_payload)}")
            async with httpx.AsyncClient() as client:
                resp = await client.post(whatsapp_api_url, headers=headers, json=template_payload)
                logger.info(f"WhatsApp API response: {resp.status_code}, {resp.text}")
                if resp.status_code == 200:
                    # Trigger the follow-up flow ONLY if the initial message was successful
                    if 'trigger_followup' in locals() and trigger_followup:
                        from app.services.memory import add_pending_followup
                        from app.api.worker import send_welcome_followup
                        
                        add_pending_followup(wa_id, task_type="checkin", reservation_id=request.reservation_id)
                        send_welcome_followup.apply_async(
                            args=[wa_id, 0, request.reservation_id],
                            countdown=settings.INITIAL_FOLLOWUP_DELAY_SECONDS
                        )
                        logger.info(f"Follow-up flow triggered for {wa_id} after successful Welcome message.")

                    log_notification(request.guest_phone, request.type, "success", f"Template '{request.template_name}' sent successfully!")
                    return {"status": "success", "detail": f"Template '{request.template_name}' sent successfully!"}
                else:
                    log_notification(request.guest_phone, request.type, "error", str(resp.json()))
                    return {"status": "error", "detail": resp.json()}

        # TEXT
        elif request.type == "text":
            if not request.message:
                raise HTTPException(status_code=400, detail="message is required for text")
            text_payload = {"messaging_product": "whatsapp", "to": request.guest_phone, "type": "text", "text": {"body": request.message}}
            logger.info(f"Sending text message: {request.message}")
            async with httpx.AsyncClient() as client:
                resp = await client.post(whatsapp_api_url, headers=headers, json=text_payload)
                logger.info(f"Text message response: {resp.status_code}, {resp.text}")
                if resp.status_code != 200:
                    log_notification(request.guest_phone, request.type, "error", str(resp.json()))
                    return {"status": "error", "detail": resp.json()}
                log_notification(request.guest_phone, request.type, "success", "Text message sent successfully!")
                return {"status": "success", "detail": "Text message sent successfully!"}

        # CTA (URL Button)
        elif request.type == "cta":
            if not request.button_url or not request.button_text:
                raise HTTPException(status_code=400, detail="button_url and button_text are required for cta")
            
            logger.info(f"Sending CTA to {request.guest_phone}")
            resp = send_interactive_cta_url(
                request.guest_phone, 
                request.header_image_url, 
                request.message or "Check this out!", 
                request.button_text, 
                request.button_url, 
                request.footer_text
            )
            if not resp:
                 log_notification(request.guest_phone, request.type, "error", "Failed to send CTA")
                 return {"status": "error", "detail": "Failed to send CTA"}
            log_notification(request.guest_phone, request.type, "success", "CTA sent successfully")
            return {"status": "success", "detail": "CTA sent successfully"}

        # BUTTONS (Reply Buttons - Yes/No, etc.)
        elif request.type == "buttons":
            if not request.button_params:
                raise HTTPException(status_code=400, detail="button_params (list of button titles) is required for buttons type")
            
            logger.info(f"Sending Interactive Buttons to {request.guest_phone}")
            resp = send_interactive_buttons(
                request.guest_phone,
                request.message or "Please select an option:",
                request.button_params,
                request.footer_text,
                request.header_text
            )
            if not resp:
                log_notification(request.guest_phone, request.type, "error", "Failed to send buttons")
                return {"status": "error", "detail": "Failed to send buttons"}
            log_notification(request.guest_phone, request.type, "success", "Buttons sent successfully")
            return {"status": "success", "detail": "Buttons sent successfully"}

        # IMAGE
        elif request.type == "image":
             if not request.header_image_url:
                 raise HTTPException(status_code=400, detail="header_image_url is required for image")
             resp = send_image(request.guest_phone, request.header_image_url, request.message)
             status_label = "success" if resp else "error"
             log_notification(request.guest_phone, request.type, status_label, "Image sent")
             return {"status": status_label, "detail": "Image sent"}

        # VIDEO
        elif request.type == "video":
             if not request.header_video_url:
                 raise HTTPException(status_code=400, detail="header_video_url is required for video")
             resp = send_video(request.guest_phone, request.header_video_url, request.message)
             status_label = "success" if resp else "error"
             log_notification(request.guest_phone, request.type, status_label, "Video sent")
             return {"status": status_label, "detail": "Video sent"}

        # DOCUMENT (Text + PDF)
        elif request.type == "text_document":
             if not request.invoice_url:
                 raise HTTPException(status_code=400, detail="invoice_url is required for text_document")
             
             resp = send_document(
                 wa_id=request.guest_phone,
                 link=request.invoice_url,
                 caption=request.message,
                 filename=request.filename or "Invoice.pdf"
             )
             status_label = "success" if resp else "error"
             log_notification(request.guest_phone, request.type, status_label, "Document sent")
             return {"status": status_label, "detail": "Document sent"}

        # LIST (Interactive List Message)
        elif request.type == "list":
            logger.info(f"Sending Services List to {request.guest_phone}")

            sections = [
                {
                    "title": "Hotel Services",
                    "rows": [
                        # {"id": "DEMO_SVC_FOOD", "title": "🍽️ Food Orders"},
                        {"id": "DEMO_SVC_REQ", "title": "🧹 Service Requests"},
                        {"id": "DEMO_SVC_COMP", "title": "📝 Complaints"},
                        # {"id": "DEMO_SVC_LATE", "title": "🕒 Late Checkout"}
                    ]
                }
            ]

            payload = {
                "messaging_product": "whatsapp",
                "to": request.guest_phone,
                "type": "interactive",
                "interactive": {
                    "type": "list",
                    "header": {"type": "text", "text": "Select a service you need"},
                    "body": {"text": "Please choose a service from the list below:"},
                    "footer": {"text": "Hotel Harriet"},
                    "action": {
                        "button": "View Services",
                        "sections": sections
                    }
                }
            }

            async with httpx.AsyncClient() as client:
                resp = await client.post(whatsapp_api_url, headers=headers, json=payload)

            logger.info(f"List response: {resp.status_code}, {resp.text}")
            log_notification(request.guest_phone, request.type, "success", "Service list sent")
            return {"status": "success", "detail": "Service list sent"}

        # UNKNOWN
        else:
             logger.warning(f"Unknown message type: {request.type}")
             return {"status": "skipped", "detail": f"Type '{request.type}' not implemented yet"}

    except Exception as e:
        log_notification(request.guest_phone, request.type, "error", str(e))
        logger.error(f"Notification Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sendReservationDataMeta")
async def sendReservationDataMeta(
    request: sendReservationDataMeta, 
    api_key: str = Header(..., alias="api-key")
):
    if api_key != settings.API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API Key")

    
    logger.info(f"Incoming Meta check-in for: {request.guest_phone} | ID: {request.booking_id}")

    from app.services.memory import save_reservation_meta
    
    success = save_reservation_meta(
        guest_phone=request.guest_phone,
        booking_id=request.booking_id,
        booking_code=request.booking_code
    )
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to store reservation meta")
    else:
        return {
            "status": "success", 
            "message": "Reservation meta stored in database",
            "data": {
                "phone": request.guest_phone,
                "booking_id": request.booking_id,
                "booking_code": request.booking_code
            }
        }
    
@router.get("/getReservationDataMeta")
async def getReservationDataMeta(
    guest_phone: Optional[str] = Query(None),
    api_key: str = Header(..., alias="api-key")
):
    if api_key != settings.API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API Key")

    from app.services.memory import get_reservation_meta
    
    reservation_meta = get_reservation_meta(guest_phone=guest_phone)
    
    return {
        "status": "success", 
        "message": "Reservation meta retrieved successfully",
        "data": reservation_meta
    }

    