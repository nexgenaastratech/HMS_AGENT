import requests
import json
import logging
from app.core.config import settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_headers():
    return {'Authorization': f"Bearer {settings.WHATSAPP_TOKEN}", 'Content-Type': 'application/json'}

def get_url():
    return f"https://graph.facebook.com/{settings.VERSION}/{settings.PHONE_NUMBER_ID}/messages"

def send_text(wa_id, text):
    """
    Sends a text message to a WhatsApp user.
    """
    url = get_url()
    headers = get_headers()
    payload = {
        "messaging_product": "whatsapp",
        "to": wa_id,
        "type": "text",
        "text": {"body": text}
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        logger.info(f"Message sent to {wa_id}: {text[:50]}...")
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to send message to {wa_id}: {e}")
        if e.response:
             logger.error(f"Response: {e.response.text}")
        return None

def send_template(wa_id, template_name, language_code="en", components=None):
    """
    Sends a template message to a WhatsApp user.
    """
    url = get_url()
    headers = get_headers()
    payload = {
        "messaging_product": "whatsapp",
        "to": wa_id,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language_code},
            "components": components if components else []
        }
    }
    
    try:
        logging.info(f"Sending Template Payload to {wa_id}: {json.dumps(payload)}")
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        logger.info(f"Template {template_name} sent to {wa_id}")
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to send template {template_name} to {wa_id}: {e}")
        if e.response:
             logger.error(f"Response: {e.response.text}")
        return None

def send_image(wa_id, image_url, caption=None):
    """
    Sends an image message to a WhatsApp user.
    """
    url = get_url()
    headers = get_headers()
    payload = {
        "messaging_product": "whatsapp",
        "to": wa_id,
        "type": "image",
        "image": {"link": image_url}
    }
    
    if caption:
        payload["image"]["caption"] = caption

    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        logger.info(f"Image sent to {wa_id}")
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to send image to {wa_id}: {e}")
        if e.response:
             logger.error(f"Response: {e.response.text}")
        return None

def upload_media(file_path, mime_type):
    """
    Uploads a media file to WhatsApp API.
    """
    url = f"https://graph.facebook.com/{settings.VERSION}/{settings.PHONE_NUMBER_ID}/media"
    headers = {'Authorization': f"Bearer {settings.WHATSAPP_TOKEN}"}
    
    files = {
        'file': (file_path, open(file_path, 'rb'), mime_type)
    }
    
    data = {
        'messaging_product': 'whatsapp'
    }
    
    try:
        response = requests.post(url, headers=headers, files=files, data=data)
        response.raise_for_status()
        logger.info(f"Media uploaded successfully: {response.json()}")
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to upload media: {e}")
        if e.response:
             logger.error(f"Response: {e.response.text}")
        return None

def send_document(wa_id, document_id=None, link=None, caption=None, filename=None):
    """
    Sends a document message to a WhatsApp user.
    """
    url = get_url()
    headers = get_headers()
    payload = {
        "messaging_product": "whatsapp",
        "to": wa_id,
        "type": "document",
        "document": {}
    }

    if document_id:
        payload["document"]["id"] = document_id
    elif link:
        payload["document"]["link"] = link
    else:
        logger.error("send_document called without document_id or link")
        return None
    
    if caption:
        payload["document"]["caption"] = caption
    if filename:
        payload["document"]["filename"] = filename
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        logger.info(f"Document sent to {wa_id}")
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to send document to {wa_id}: {e}")
        if e.response:
             logger.error(f"Response: {e.response.text}")
        return None

def send_interactive_cta_url(wa_id, image_url, body_text, button_text, button_url, footer_text=None):
    """
    Sends an interactive CTA URL message with image header and button.
    No Meta template needed - works within 24-hour window.
    """
    url = get_url()
    headers = get_headers()
    payload = {
        "messaging_product": "whatsapp",
        "to": wa_id,
        "type": "interactive",
        "interactive": {
            "type": "cta_url",
            "body": {
                "text": body_text
            },
            "action": {
                "name": "cta_url",
                "parameters": {
                    "display_text": button_text,
                    "url": button_url
                }
            }
        }
    }
    
    # Add image header if provided
    if image_url:
        payload["interactive"]["header"] = {
            "type": "image",
            "image": {"link": image_url}
        }
    
    if footer_text:
        payload["interactive"]["footer"] = {"text": footer_text}
    
    try:
        logger.info(f"Sending CTA URL payload: {json.dumps(payload, indent=2)}")
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        logger.info(f"CTA URL message sent to {wa_id}")
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to send CTA URL to {wa_id}: {e}")
        if e.response:
            logger.error(f"Status Code: {e.response.status_code}")
            logger.error(f"Response Body: {e.response.text}")
            logger.error(f"Sent Payload: {json.dumps(payload, indent=2)}")
        return None


def send_video(wa_id, video_url, caption=None):
    """
    Sends a video message to a WhatsApp user.
    No Meta template needed - works within 24-hour window.
    """
    url = get_url()
    headers = get_headers()
    payload = {
        "messaging_product": "whatsapp",
        "to": wa_id,
        "type": "video",
        "video": {"link": video_url}
    }

    if caption:
        payload["video"]["caption"] = caption

    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        logger.info(f"Video sent to {wa_id}")
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to send video to {wa_id}: {e}")
        if e.response:
            logger.error(f"Response: {e.response.text}")
        return None
def send_services_request(wa_id):
    """
    Sends the hotel services menu to a WhatsApp user.
    """
    sections = [
        {
            "title": "Hotel Services",
            "rows": [
                # {"id": "DEMO_SVC_FOOD", "title": "Food Orders", "description": "In-room dining & restaurant services"},
                {"id": "DEMO_SVC_REQ", "title": "Service Requests", "description": "Housekeeping & assistance"},
                {"id": "DEMO_SVC_COMP", "title": "Complaints", "description": "We value your experience"},
                # {"id": "DEMO_SVC_LATE", "title": "Late Checkout", "description": "Subject to availability"}
            ]
        }
    ]

    return send_interactive_list(
        wa_id=wa_id,
        header_text="Select a service you need",
        body_text="Please choose a service from the list below:",
        button_text="View Services",
        sections=sections,
        footer_text="Hotel Harriet"
    )

def send_room_list(wa_id):
    send_interactive_list(
        wa_id=wa_id,
        header_text="Select Room Number",
        body_text="Tap your room number to proceed",
        button_text="Select Room",
        sections=[
            {
                "title": "First Floor",
                "rows": [
                    {"id": "ROOM_101", "title": "Room 101"},
                    {"id": "ROOM_102", "title": "Room 102"},
                    {"id": "ROOM_103", "title": "Room 103"}

                ]
            },
            
        ],
        footer_text="Hotel Harriet"
    )


def send_interactive_list(wa_id, header_text, body_text, button_text, sections, footer_text=None):
    """
    Sends an interactive list message to a WhatsApp user.
    """
    url = get_url()
    headers = get_headers()
    payload = {
        "messaging_product": "whatsapp",
        "to": wa_id,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "header": {
                "type": "text",
                "text": header_text
            },
            "body": {
                "text": body_text
            },
            "action": {
                "button": button_text,
                "sections": sections
            }
        }
    }

    if footer_text:
        payload["interactive"]["footer"] = {"text": footer_text}

    try:
        logger.info(f"Sending Interactive List payload: {json.dumps(payload, indent=2)}")
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        logger.info(f"Interactive list sent to {wa_id}")
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to send interactive list to {wa_id}: {e}")
        if e.response:
            logger.error(f"Status Code: {e.response.status_code}")
            logger.error(f"Response Body: {e.response.text}")
            logger.error(f"Sent Payload: {json.dumps(payload, indent=2)}")
        return None

def send_interactive_buttons(wa_id, body_text, buttons, footer_text=None, header_text=None):
    """
    Sends an interactive message with up to 3 reply buttons.
    buttons: List of strings (button titles)
    """
    url = get_url()
    headers = get_headers()
    
    button_objs = []
    for idx, btn_title in enumerate(buttons):
        button_objs.append({
            "type": "reply",
            "reply": {
                "id": f"btn_{idx}",
                "title": btn_title[:20] # Title limit is 20 chars
            }
        })

    payload = {
        "messaging_product": "whatsapp",
        "to": wa_id,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {
                "text": body_text
            },
            "action": {
                "buttons": button_objs
            }
        }
    }

    if footer_text:
        payload["interactive"]["footer"] = {"text": footer_text}
        
    if header_text:
        payload["interactive"]["header"] = {"type": "text", "text": header_text}
    
    try:
        logger.info(f"Sending Interactive Buttons payload: {json.dumps(payload, indent=2)}")
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        logger.info(f"Interactive buttons sent to {wa_id}")
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to send interactive buttons to {wa_id}: {e}")
        if e.response:
            logger.error(f"Response: {e.response.text}")
            logger.error(f"Sent Payload: {json.dumps(payload, indent=2)}")
        return None

def send_location(wa_id,latitude=37.4224764,longitude=-122.0842499,name="Hotel Harriet",address="123 Main St, Rameswaram"):
    url = get_url()
    headers = get_headers()
    payload = {
        "messaging_product": "whatsapp",
        "to": wa_id,
        "type": "location",
        "location": {
            "latitude": latitude,
            "longitude": longitude,
            "name": name,
            "address": address
        }
    }
    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        logger.info(f"Location sent to {wa_id}")
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to send location to {wa_id}: {e}")
        if e.response:
            logger.error(f"Response: {e.response.text}")
            logger.error(f"Sent Payload: {json.dumps(payload, indent=2)}")
        return None
