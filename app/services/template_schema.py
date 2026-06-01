
# Configuration defining the expected structure for each template
TEMPLATE_CONFIG = {
    # 1. checkin_welcome
    # Header: Document
    # Body: {{1}} Guest Name, {{2}} Booking Code, {{3}} Stay Duration, {{4}} Room No, {{5}} Total Amount
    # Buttons: Order Food (URL), Order Service (URL)
    "checkin_welcome": {
        "header_type": "DOCUMENT",
        "body_params": [
            "guest_name", 
            "booking_code", 
            "stay_duration", 
            "room_no", 
            "total_amount"
        ],
        "buttons": [
            {"type": "URL", "param_key": "button_order_food"},    # Index 0
            {"type": "URL", "param_key": "button_order_service"}  # Index 1
        ]
    },

    # 2. welcome_with_pdf
    # Header: Document
    # Body: {{1}} Guest Name, {{2}} Booking Code, {{3}} Stay, {{4}} Total Amount
    "welcome_with_pdf": {
        "header_type": "DOCUMENT",
        "body_params": [
            "guest_name",
            "booking_code",
            "stay_duration",
            "total_amount"
        ],
        "buttons": [] 
    },

    # 3. refund_complete
    # Body: {{1}} Guest Name, {{2}} Booking Code, {{3}} Refund Amount
    "refund_complete": {
        "header_type": None,
        "body_params": [
            "guest_name",
            "booking_code",
            "refund_amount"
        ],
        "buttons": []
    },

    # 4. refund_processed
    # Body: {{1}} Guest Name, {{2}} Booking Code, {{3}} Stay Dates, {{4}} Refund Amount, {{5}} Reason
    "refund_processed": {
        "header_type": None,
        "body_params": [
            "guest_name",
            "booking_code", 
            "stay_dates",
            "refund_amount",
            "refund_reason"
        ],
        "buttons": []
    },

    # 5. reminder_template
    # Body: {{1}} Guest name, {{2}} Check-in Date
    "reminder_template": {
        "header_type": None,
        "body_params": [
            "guest_name",
            "checkin_date"
        ],
        "buttons": []
    },

    # 6. welcome_in_checkin
    # Header: TEXT ("Document")
    # Body: {{1}} Guest Name, {{2}} Booking Code, {{3}} Stay Duration, {{4}} Room No, {{5}} Total Amount
    # Buttons: Order Food (URL), Order Service (URL)
    "welcome_in_checkin": {
        "header_type": "TEXT", # Configured as TEXT header in JSON
        "body_params": [
            "guest_name", 
            "booking_code", 
            "stay_duration", 
            "room_no", 
            "total_amount"
        ],
        "buttons": [
            {"type": "URL", "param_key": "button_order_food"},
            {"type": "URL", "param_key": "button_order_service"}
        ]
    },

    # 7. welcome_hotelharriet
    # Header: VIDEO
    # Body: {{1}} Guest Name
    "welcome_hotelharriet": {
        "header_type": "VIDEO",
        "body_params": [
            "guest_name"
        ],
        "buttons": []
    },

    # 8. food_menu_cta_v2
    # Header: IMAGE
    # Body: No params in text "Hello Welcome..."
    # Buttons: Order Menu (URL) -> {{1}}
    "food_menu_cta_v2": {
        "header_type": "IMAGE",
        "body_params": [], # No body params in text definition
        "buttons": [
            {"type": "URL", "param_key": "button_order_menu"} # Index 0
        ]
    },

    # 9. checkout
    # Header: DOCUMENT
    # Body: {{1}} Guest Name, {{2}} Total Amount
    # Buttons: Flow (Feedback Here)
    "checkout": {
        "header_type": "DOCUMENT",
        "body_params": [
            "guest_name",
            "total_amount"
        ],
        "buttons": [] 
    },
    
    # 10. hello_world
    "hello_world": {
        "header_type": "TEXT",
        "body_params": [],
        "buttons": []
    }
}

def get_template_components(template_name, data):
    """
    Generates component list based on TEMPLATE_CONFIG.
    """
    config = TEMPLATE_CONFIG.get(template_name)
    if not config:
        return [] 

    components = []

    # 1. Header
    if config["header_type"] == "DOCUMENT" and "header_document_url" in data:
         components.append({
            "type": "header",
            "parameters": [
                {
                    "type": "document",
                    "document": {
                        "link": data["header_document_url"],
                        "filename": data.get("header_filename", "Document.pdf")
                    }
                }
            ]
        })
    elif config["header_type"] == "IMAGE" and "header_image_url" in data:
        components.append({
            "type": "header",
            "parameters": [
                {
                    "type": "image",
                    "image": {
                        "link": data["header_image_url"]
                    }
                }
            ]
        })
    elif config["header_type"] == "VIDEO" and "header_video_url" in data:
        components.append({
            "type": "header",
            "parameters": [
                {
                    "type": "video",
                    "video": {
                        "link": data["header_video_url"]
                    }
                }
            ]
        })
    elif config["header_type"] == "TEXT" and "header_text" in data:
         # Variable text header
         components.append({
            "type": "header",
            "parameters": [
                {
                    "type": "text",
                    "text": data["header_text"]
                }
            ]
        })

    # 2. Body
    if config["body_params"]:
        parameters = []
        for key in config["body_params"]:
            val = data.get(key, "") 
            parameters.append({"type": "text", "text": str(val)})
        
        if parameters:
            components.append({
                "type": "body",
                "parameters": parameters
            })

    # 3. Buttons
    if config.get("buttons"):
        for idx, btn_config in enumerate(config["buttons"]):
            param_key = btn_config.get("param_key")
            if param_key and param_key in data:
                if btn_config["type"] == "URL":
                     components.append({
                        "type": "button",
                        "sub_type": "url",
                        "index": idx,
                        "parameters": [{"type": "text", "text": str(data[param_key])}]
                    })

    return components
