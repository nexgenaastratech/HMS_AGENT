
import os
from fastapi import FastAPI, HTTPException

from fastapi.responses import FileResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
import logging
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.v1.endpoints import webhook_router, notification_router


app = FastAPI(title=settings.PROJECT_NAME, version=settings.VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(webhook_router) 

# Notification API (v1)
app.include_router(notification_router, prefix="/api/v1") 

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    logging.error(f"Validation Error: {exc}")
    try:
        logging.error(f"Validation Details: {exc.errors()}")
        logging.error(f"Request Body: {exc.body}")
    except:
        pass
    # Return more details in the response
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "body": str(exc.body)},
    )
 

@app.on_event("startup")
async def startup_event():
    print(f"\n[INFO] {settings.PROJECT_NAME} {settings.VERSION} Started (Modular) [INFO]\n")
    try:
        from app.bot import rag_system
        # Pre-initialize knowledge base to avoid 429 errors on first message
        rag_system.initialize_knowledge_base()
    except Exception as e:
        logging.error(f"Startup RAG Initialization Failed: {e}")

@app.get("/assets/{file_path:path}")
async def serve_asset(file_path: str):
    """
    Serve static assets (images) for WhatsApp messages.
    Assumes 'assets' directory is in the project root (CWD).
    Supports nested directories (e.g. assets/image/food.png).
    """
    asset_path = os.path.join("assets", file_path)
    
    if not os.path.exists(asset_path):
        raise HTTPException(status_code=404, detail="File not found")
    
    media_type = "application/octet-stream"
    lower_path = file_path.lower()
    if lower_path.endswith('.png'):
        media_type = "image/png"
    elif lower_path.endswith('.jpg') or lower_path.endswith('.jpeg'):
        media_type = "image/jpeg"
    elif lower_path.endswith('.mp4'):
        media_type = "video/mp4"
    
    return FileResponse(asset_path, media_type=media_type)
