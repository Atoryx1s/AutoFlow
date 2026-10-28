import json
import logging
import datetime
from fastapi import APIRouter, Request, status as fastapi_status
from fastapi.responses import JSONResponse
from telegram import Update
from src.config import TOKEN, GOOGLE_CREDENTIALS_JSON, SPREADSHEET_NAME
from src.database import get_sheet

logger = logging.getLogger(__name__)
router = APIRouter()
telegram_app_ref = None

def set_telegram_app(app):
    global telegram_app_ref
    telegram_app_ref = app

@router.get("/debug/google-sheets")
async def debug_google_sheets():
    if not GOOGLE_CREDENTIALS_JSON:
        return {"status": "error", "message": "GOOGLE_CREDENTIALS_JSON not set"}
    try:
        creds_dict = json.loads(GOOGLE_CREDENTIALS_JSON)
        sheet = get_sheet()
        if sheet:
            return {"status": "connected", "spreadsheet": SPREADSHEET_NAME, "project_id": creds_dict.get("project_id")}
        return {"status": "error", "message": "Could not connect to Google Sheets"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@router.post(f"/webhook/{TOKEN}")
async def telegram_webhook(request: Request):
    global telegram_app_ref
    try:
        data = await request.json()
        update = Update.de_json(data, telegram_app_ref.bot)
        await telegram_app_ref.process_update(update)
        return JSONResponse(content={"ok": True})
    except Exception as e:
        logger.error(f"Error in webhook: {e}")
        return JSONResponse(content={"ok": False}, status_code=500)

@router.get("/")
async def root():
    return {"status": "Bot is running", "timestamp": datetime.datetime.now().isoformat()}

@router.get("/health")
async def health_check():
    return {"status": "healthy"}
