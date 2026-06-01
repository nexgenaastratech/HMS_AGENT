
from fastapi import APIRouter, Query, Request, HTTPException, BackgroundTasks, Depends
from fastapi.responses import PlainTextResponse, JSONResponse
from app.core.config import settings
from app.core.security import verify_webhook_signature
from app.bot import process_message

router = APIRouter()

@router.get("/webhook")
async def verify_webhook(
    mode: str = Query(None, alias="hub.mode"),
    token: str = Query(None, alias="hub.verify_token"),
    challenge: str = Query(None, alias="hub.challenge")
):
    if mode == "subscribe" and token == settings.VERIFY_TOKEN:
        return PlainTextResponse(challenge)
    raise HTTPException(status_code=403, detail="Invalid verification token")

@router.post("/webhook", dependencies=[Depends(verify_webhook_signature)])
async def webhook_handler(request: Request, background_tasks: BackgroundTasks):
    payload = await request.json()
    # Process message in background to avoid timeouts
    background_tasks.add_task(process_message, payload)
    return JSONResponse({"status": "ok"})
