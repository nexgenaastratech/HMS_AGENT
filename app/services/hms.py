import requests
import logging
import httpx
from typing import List, Dict, Any, Optional
from app.core.config import settings

CURRENT_ACCESS_TOKEN = settings.HOTEL_HARRIET_TOKEN

def login_and_get_token() -> Optional[str]:
    """
    Logs in to HMS and retrieves a new access token.
    Updates the global CURRENT_ACCESS_TOKEN.
    """
    global CURRENT_ACCESS_TOKEN
    try:
        url = settings.HMS_LOGIN_URL
        payload = {
            "userIdentifier": settings.HMS_USERNAME,
            "password": settings.HMS_PASSWORD,
            "channelId": settings.HMS_CHANNEL_ID
        }
        headers = {'Content-Type': 'application/json'}
        
        logging.info(f" Attempting HMS Login to {url}...")
        response = requests.post(url, json=payload, headers=headers, timeout=10, verify=False)
        
        if response.status_code == 200:
            token = response.headers.get("access-token") or response.headers.get("Access-Token")
            
            if token:
                CURRENT_ACCESS_TOKEN = token
                logging.info(" HMS Login Successful. New Token Acquired.")
                return token
            else:
                logging.error(" HMS Login Failed: No 'access-token' header in response.")
                print(f"FULL DEBUG BODY: {response.text}") 
                return None
        else:
            logging.error(f" HMS Login Failed: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        logging.error(f"❌ HMS Login Error: {e}")
        return None

def make_authenticated_request(method: str, url: str, json_data: Optional[Dict[str, Any]] = None, params: Optional[Dict[str, Any]] = None) -> requests.Response:
    """
    Wrapper for requests to handle 401 Unauthorized by refreshing token and retrying.
    """
    global CURRENT_ACCESS_TOKEN
    
    headers = {'Content-Type': 'application/json'}
    if CURRENT_ACCESS_TOKEN:
        headers['Authorization'] = f"Bearer {CURRENT_ACCESS_TOKEN}"
        
    try:
        if method.upper() == "POST":
            logging.info(f"POSTing to {url}, Payload: {json_data}, Headers: {headers}")
            response = requests.post(url, headers=headers, json=json_data, params=params, timeout=10, verify=False)
        elif method.upper() == "GET":
            response = requests.get(url, headers=headers, params=params, timeout=10, verify=False)
        else:
            raise ValueError(f"Unsupported method: {method}")
            
        if response.status_code == 401:
            logging.warning(f"401 Unauthorized at {url}. Refreshing token...")
            new_token = login_and_get_token()
            
            if new_token:
                headers['Authorization'] = f"Bearer {new_token}"
                if method.upper() == "POST":
                    response = requests.post(url, headers=headers, json=json_data, params=params, timeout=10, verify=False)
                elif method.upper() == "GET":
                    response = requests.get(url, headers=headers, params=params, timeout=10, verify=False)
            else:
                logging.error(" Token Refresh Failed. Cannot retry request.")
                
        return response

    except requests.RequestException as e:
        logging.error(f" Request Error to {url}: {e}")
        mock_resp = requests.Response()
        mock_resp.status_code = 500
        mock_resp._content = str(e).encode()
        return mock_resp


def log_chat_to_server(phone_number, message_text, sender="Guest"):
    try:
        url = settings.CHAT_LOG_URL
        formatted_message = f"{sender}: {message_text}" 
        payload = { 
            "roomId": None, 
            "message": formatted_message, 
            "guestName": phone_number 
        }

        response = make_authenticated_request("POST", url, json_data=payload)
        
        if response.status_code == 200:
            print(f" DB Logged: {sender}")
        else:
            print(f" DB Log Failed: {response.status_code} - {response.text}")

    except Exception as e:
        print(f" DB Log Error: {e}")

def notify_hotel_staff(phone_number: str, user_message: str, request_type: str, room_number: Optional[str] = None):
    try:
        url = settings.NOTIFICATION_URL
        fromGuest = True 
        
        # Clean phone number: remove '91' prefix if present
        if phone_number.startswith("91") and len(phone_number) > 10:
             clean_phone = phone_number[2:]
        else:
             clean_phone = phone_number

        payload = {
            "phone": clean_phone,
            "roomNumber": room_number,
            "type": request_type,
            "queryMessage": user_message,
            "fromGuest": fromGuest
        }
        
        logging.info(f"Sending Staff Notification: {phone_number} - Room: {room_number}")
        
        response = make_authenticated_request("POST", url, json_data=payload)
        
        if response.status_code == 200:
            logging.info(f" Staff Notified successfully")
            return response.json()
        else:
            logging.warning(f" Staff Notification Failed: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        logging.error(f" Staff Notification Error: {e}")
        return None

def get_room_list(phone_number: str):
    try:
        url = settings.ROOM_LIST_URL
        
        # Phone number cleaning logic
        clean_phone = phone_number
        if phone_number.startswith("91") and len(phone_number) > 10:
             clean_phone = phone_number[2:]
             
        # API expects 'mobile' in JSON body
        payload = {
            "mobile": clean_phone
        }
        
        # Helper function expects 'json_data' argument
        response = make_authenticated_request("POST", url, json_data=payload)
        
        if response and response.status_code == 200:
             return response.json()
        else:
             logging.error(f"Get Room List Failed: {response.status_code if response else 'No Response'}")
             return None
             
    except Exception as e:
        logging.error(f"Get Room List Error: {e}")
        return None

def check_reserved_status(phone_number: str) -> bool:
    try:
        url = settings.CHECK_RESERVED_STATUS_URL
        
        # Phone number cleaning logic
        clean_phone = phone_number
        if phone_number.startswith("91") and len(phone_number) > 10:
             clean_phone = phone_number[2:]
             
        params = {"number": clean_phone}
        
        # The API is described as `/api/Booking/CheckReservedStatus?number=7904099710`
        response = make_authenticated_request("GET", url, params=params)
        
        if response and response.status_code == 200:
             data = response.json()
             return data.get("isReserved", False)
        else:
             logging.warning(f"Check Reserved Status Failed: {response.status_code if response else 'No Response'}")
             return False
             
    except Exception as e:
        logging.error(f"Check Reserved Status Error: {e}")
        return False

def get_all_query_request(phone_number: str):
    try:
        if not hasattr(settings, 'GET_ALL_QUERY_REQUEST_URL'):
            logging.error("GET_ALL_QUERY_REQUEST_URL not configured")
            return None

        url = settings.GET_ALL_QUERY_REQUEST_URL
        
        # Clean phone if needed (same logic as other funcs)
        if phone_number.startswith("91") and len(phone_number) > 10:
             clean_phone = phone_number[2:]
        else:
             clean_phone = phone_number

        payload = {
            "filter": {
                "getAll": True,
                "phone": clean_phone
            }
        }
        
        # Assuming POST for consistency with other HMS APIs that take a body
        response = make_authenticated_request("POST", url, json_data=payload)
        
        if response.status_code == 200:
             return response.json()
        else:
             logging.error(f" Get All Query Request Failed: {response.status_code} - {response.text}")
             return None
                 
    except Exception as e:
        logging.error(f" Get All Query Request Error: {e}")
        return None

def mark_request_completed(request_id_val: str, status: str = "true"):
    """
    Marks a specific query request as 'Completed' (true) or 'Open' (false).
    """
    try:
        if not hasattr(settings, 'CHANGE_TO_COMPLETED_URL'):
            logging.error("CHANGE_TO_COMPLETED_URL not configured")
            return None

        url = settings.CHANGE_TO_COMPLETED_URL
        # Using query parameters as specified
        params = {
            "QueryRequestId": request_id_val,
            "QueryStatus": status 
        }
        # Note: Sending empty json_data or None if body is not required, but POST usually expects something. 
        # API spec says 'Parameters (query)', so we use params.
        response = make_authenticated_request("POST", url, params=params)
        
        if response.status_code == 200:
             logging.info(f"Request {request_id_val} marked as completed.")
             return response.json()
        else:
             logging.error(f" Mark Request Completed Failed: {response.status_code} - {response.text}")
             return None
             
    except Exception as e:
        logging.error(f" Mark Request Completed Error: {e}")
        return None

 
def add_special_request(booking_id: str, special_request: str):
    try:
        url = settings.ADD_SPECIAL_REQUEST_URL
        
        payload = {
            "bookingId": booking_id,
            "specialRequest": special_request,
        }
        
        logging.info(f"Attempting to notify staff for Booking: {booking_id}")
        
        # Use our helper to handle the Access Token automatically
        response = make_authenticated_request("POST", url, json_data=payload)
        
        if response.status_code == 200:
            logging.info(f"Staff Notified successfully for booking {booking_id}")
            return response.json()
        else:
            logging.warning(f"Staff Notification Failed: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        logging.error(f"Staff Notification Error: {e}")
        return None
      