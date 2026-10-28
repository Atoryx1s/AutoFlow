import datetime
import calendar
import logging
from telegram.ext import CallbackContext
from src.config import CHAT_ID, TIMEZONE
from src.services.weather import get_weather
from src.services.reports import generate_monthly_report

logger = logging.getLogger(__name__)

def is_weekday():
    return datetime.datetime.now(TIMEZONE).weekday() < 5

async def send_question(chat_id, context, question_idx):
    from src.bot.handlers import send_question_impl
    await send_question_impl(chat_id, context, question_idx)

async def send_daily_check(context: CallbackContext):
    try:
        if not is_weekday():
            logger.info("Dnes je voľný deň – oznámenie sa nezasiela")
            return

        date = datetime.date.today().strftime("%d.%m.%Y")
        await context.bot.send_message(chat_id=CHAT_ID, text="Dobrý deň!🌞")
        await context.bot.send_message(chat_id=CHAT_ID, text="Denná kontrola budova bola aktivovaná.😃")
        await context.bot.send_message(chat_id=CHAT_ID, text=f"🔔 Dnes {date} a my máme kontrolu nad budovou!")
        await context.bot.send_message(chat_id=CHAT_ID, text=f"Počasie: {get_weather()}")
        await context.bot.send_message(chat_id=CHAT_ID, text="Tak poďme na to!😊")

        await send_question(CHAT_ID, context, 0)
    except Exception as e:
        logger.error(f"Chyba v send_daily_check: {e}")

async def monthly_auto_report(context: CallbackContext):
    try:
        today = datetime.datetime.now(TIMEZONE)
        last_day = calendar.monthrange(today.year, today.month)[1]
        if today.day == last_day:
            await generate_monthly_report(None, context, month_offset=0)
    except Exception as e:
        logger.error(f"Chyba v monthly_auto_report: {e}")
