"""
Store and retrieve URL button parameter keys for each user
Allows reusing guest-specific URL parameters across multiple templates
"""
from typing import Dict, Optional
import logging

USER_BUTTON_KEYS = {}

def store_button_keys(wa_id: str, keys: Dict[str, str]):
    """
    Store button parameter keys for a user
    
    Args:
        wa_id: WhatsApp ID
        keys: Dict like {"food": "?guest_id=ABC123&type=food", "service": "?guest_id=ABC123&type=service"}
    """
    USER_BUTTON_KEYS[wa_id] = keys
    logging.info(f"✅ Stored button keys for {wa_id}: {keys}")

def get_button_key(wa_id: str, button_type: str) -> Optional[str]:
    """
    Get button parameter key for a user
    
    Args:
        wa_id: WhatsApp ID
        button_type: "food" or "service"
    
    Returns:
        Button parameter key or None
    """
    keys = USER_BUTTON_KEYS.get(wa_id, {})
    key = keys.get(button_type)
    
    if key:
        logging.info(f"🔑 Retrieved {button_type} key for {wa_id}: {key}")
    else:
        logging.warning(f"⚠️ No {button_type} key found for {wa_id}")
    
    return key

def get_all_button_keys(wa_id: str) -> Dict[str, str]:
    """
    Get all button keys for a user
    
    Args:
        wa_id: WhatsApp ID
    
    Returns:
        Dict of all button keys
    """
    return USER_BUTTON_KEYS.get(wa_id, {})

def has_button_keys(wa_id: str) -> bool:
    """Check if user has any stored button keys"""
    return wa_id in USER_BUTTON_KEYS

def clear_button_keys(wa_id: str):
    """Clear all button keys for a user (e.g., after checkout)"""
    if wa_id in USER_BUTTON_KEYS:
        del USER_BUTTON_KEYS[wa_id]
        logging.info(f"🗑️ Cleared button keys for {wa_id}")
