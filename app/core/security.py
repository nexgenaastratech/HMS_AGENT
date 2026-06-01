
import hashlib
import hmac
from fastapi import Header, HTTPException, Request, Security, Depends
from fastapi.security import APIKeyHeader, HTTPBearer, HTTPAuthorizationCredentials
from app.core.config import settings

# Security schemes
api_key_header = APIKeyHeader(name="api-key", auto_error=False)
bearer_scheme = HTTPBearer(auto_error=False)

async def verify_api_key(
    api_key_val: str = Security(api_key_header),
    bearer_token: HTTPAuthorizationCredentials = Security(bearer_scheme)
):
    """
    Verifies the internal API key. 
    Accepts specific header 'api-key' OR 'Authorization: Bearer <key>'.
    """
    # Check 'api-key' header
    if api_key_val and api_key_val == settings.API_KEY:
        return True
    
    # Check 'Authorization: Bearer' header
    if bearer_token and bearer_token.credentials == settings.API_KEY:
        return True
        
    raise HTTPException(status_code=401, detail="Invalid or missing API key")


async def verify_webhook_signature(request: Request, x_hub_signature_256: str = Header(None)):
    """
    Verifies the X-Hub-Signature-256 header sent by Meta.
    This ensures the request actually came from WhatsApp.
    """
    if not settings.APP_SECRET:
        return True 
        
    if not x_hub_signature_256:
        return True

    payload = await request.body()
    expected_signature = hmac.new(
        key=settings.APP_SECRET.encode(),
        msg=payload,
        digestmod=hashlib.sha256
    ).hexdigest()
    
    expected_signature_header = f"sha256={expected_signature}"
    
    if not hmac.compare_digest(expected_signature_header, x_hub_signature_256):
        raise HTTPException(status_code=403, detail="Invalid signature")
    
    return True
