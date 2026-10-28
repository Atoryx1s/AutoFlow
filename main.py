import os
import logging
import datetime
import uvicorn
from fastapi import FastAPI
from contextlib import asynccontextmanager
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters
from src.config import TOKEN, TIMEZONE
import src.bot.handlers as handlers
from src.bot.jobs import send_daily_check, monthly_auto_report
from src.api import router as api_router, set_telegram_app

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting bot initialization...")
    telegram_app = Application.builder().token(TOKEN).build()

    telegram_app.add_handler(CallbackQueryHandler(handlers.button_handler))
    telegram_app.add_handler(CommandHandler("photo", handlers.photo_command))
    telegram_app.add_handler(MessageHandler(filters.PHOTO, handlers.photo))
    telegram_app.add_handler(CommandHandler("feedback", handlers.feedback_command))
    telegram_app.add_handler(CommandHandler("cancel", handlers.cancel_feedback))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.handle_feedback_message))
    telegram_app.add_handler(CommandHandler("weather", handlers.pocasie))
    telegram_app.add_handler(CommandHandler("status", handlers.status))
    telegram_app.add_handler(CommandHandler("podpisovatel", handlers.podpis))
    telegram_app.add_handler(CommandHandler("report", handlers.report_command))
    telegram_app.add_handler(CommandHandler("full_report", handlers.full_report_command))
    telegram_app.add_handler(CommandHandler("last_month", handlers.last_month_report_command))
    telegram_app.add_handler(CommandHandler("test", handlers.test_check))

    telegram_app.job_queue.run_daily(send_daily_check, time=datetime.time(hour=7, minute=0, tzinfo=TIMEZONE), name="daily_message")
    telegram_app.job_queue.run_daily(monthly_auto_report, time=datetime.time(hour=12, minute=0, tzinfo=TIMEZONE), name="monthly_report")

    await telegram_app.initialize()
    await telegram_app.start()
    set_telegram_app(telegram_app)
    logger.info("✅ Bot started successfully")
    yield
    await telegram_app.stop()
    await telegram_app.shutdown()

fastapi_app = FastAPI(lifespan=lifespan)
fastapi_app.include_router(api_router)

if __name__ == "__main__":
    port = int(os.getenv('PORT', 8080))
    uvicorn.run("main:fastapi_app", host="0.0.0.0", port=port, reload=True)
