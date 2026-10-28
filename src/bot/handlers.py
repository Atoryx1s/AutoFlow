import logging
import asyncio
import aiohttp
import calendar
import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext
from src.config import QUESTIONS, TOKEN, SIGNED_BY, CHAT_ID, TIMEZONE, IMGBB_API_KEY
from src.database import log_or_update_data, add_signature_to_report
from src.services.email_serv import send_feedback_email
from src.services.weather import get_weather
from src.services.reports import generate_monthly_report
import base64

logger = logging.getLogger(__name__)

async def send_question_impl(chat_id, context, question_idx):
    if question_idx >= len(QUESTIONS):
        success = await asyncio.to_thread(add_signature_to_report)
        text = "✅ Kontrola bola dokončená. Správa bola podpísaná! Pekný deň!" if success else "✅ Kontrola bola dokončená. Prajeme vám pekný deň!"
        await context.bot.send_message(chat_id=chat_id, text=text)
        return

    question_text = QUESTIONS[question_idx]["text"]
    keyboard = [
        [InlineKeyboardButton("✅ V poriadku", callback_data=f'OK_{question_idx}')],
        [InlineKeyboardButton("❌ Nie", callback_data=f'NO_{question_idx}')]
    ]
    await context.bot.send_message(chat_id=chat_id, text=question_text, reply_markup=InlineKeyboardMarkup(keyboard))

async def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    answer, q_idx_str = query.data.split('_')
    question_idx = int(q_idx_str)

    success = await asyncio.to_thread(log_or_update_data, query.message.chat_id, question_idx, answer)
    if not success:
        await query.message.reply_text("❌ Chyba pri ukladaní údajov.")
        return

    await query.edit_message_text(text=f"{QUESTIONS[question_idx]['text']}\nOdpoveď: {'✅' if answer == 'OK' else '❌'}")
    context.user_data["survey_step"] = question_idx + 1

    if context.user_data["survey_step"] < len(QUESTIONS):
        await send_question_impl(query.message.chat_id, context, context.user_data["survey_step"])
    else:
        success = await asyncio.to_thread(add_signature_to_report)
        text = "✅ Kontrola bola dokončená. Správa bola podpísaná! Ďakujem 😉" if success else "✅ Anketa je ukončená! Ďakujeme 😉"
        await context.bot.send_message(chat_id=query.message.chat_id, text=text)
        context.user_data.pop("survey_step", None)

async def photo_command(update: Update, context: CallbackContext):
    current_step = context.user_data.get("survey_step", 0)
    if current_step - 1 >= len(QUESTIONS):
        await update.message.reply_text("✅ Anketa je už ukončená!")
        return
    current_photos = context.user_data.get("current_photos", [])
    await update.message.reply_text(f"📷 Pošlite fotografie jednu po druhej.\nUž uložené: {len(current_photos)} foto")

async def upload_to_freeimagehost(file_path: str, token: str, freeimage_api_key: str) -> str:
    if not freeimage_api_key:
        raise ValueError("Kritická chyba: Kľúč API pre hosting fotografií nie je nakonfigurovaný v súbore .env!")

    try:
        async with aiohttp.ClientSession() as session:
            if file_path.startswith("http://") or file_path.startswith("https://"):
                telegram_url = file_path
            else:
                telegram_url = f"https://api.telegram.org/file/bot{token}/{file_path}"

            logger.info(f"Sťahujem súbor z Telegramu cez URL: {telegram_url}")
            async with session.get(telegram_url) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise RuntimeError(
                        f"Nepodarilo sa načítať fotografiu z rozhrania Telegram API. Stav: {resp.status}, Podrobnosti: {error_text}")
                image_data = await resp.read()

            image_base64 = base64.b64encode(image_data).decode('utf-8')

            form_data = aiohttp.FormData()
            form_data.add_field('key', freeimage_api_key)
            form_data.add_field('action', 'upload')
            form_data.add_field('source', image_base64)
            form_data.add_field('format', 'json')

            async with session.post('https://freeimage.host/api/1/upload', data=form_data) as upload_resp:
                data = await upload_resp.json()

                if upload_resp.status == 200 and data.get('status_code') == 200:
                    url = data['image']['url']
                    logger.info(f"Photo successfully uploaded to FreeImage.Host: {url}")
                    return url
                else:
                    error_msg = data.get('error', {}).get('message', 'Unknown API error')
                    raise RuntimeError(f"FreeImage.Host zamietol žiadosť: {error_msg}")

    except Exception as e:
        logger.exception(f"Kritická chyba pri načítaní fotografie: {e}")
        raise
    
async def photo(update: Update, context: CallbackContext):
    current_step = context.user_data.get("survey_step", 0)

    question_idx = current_step - 1
    if question_idx >= len(QUESTIONS):
        await update.message.reply_text("✅ Anketa bola ukončená!")
        return

    question = QUESTIONS[question_idx]
    column = question["column"]

    photo = update.message.photo[-1]
    file = await photo.get_file()

    full_url = file.file_path
    if full_url and f"/bot{TOKEN}/" in full_url:
        file_path = full_url.split(f"/bot{TOKEN}/")[-1]
    else:
        file_path = full_url

    logger.info(f"Extracted file path: {file_path}")

    permanent_url = await upload_to_freeimagehost(file_path, TOKEN, IMGBB_API_KEY)

    current_photos = context.user_data.get("current_photos", [])
    current_photos.append(permanent_url)
    context.user_data["current_photos"] = current_photos

    success = await asyncio.to_thread(
        log_or_update_data,
        update.effective_chat.id,
        question_idx,
        None,
        current_photos
    )

    if success:
        await update.message.reply_text(
            f"✅ Fotografia je uložená!\n"
            f"📸 Celkom zachované: {len(current_photos)} foto\n\n"
            f"Môžete poslať ďalšie fotografie alebo odpovedať na otázky"
        )
    else:
        await update.message.reply_text("❌ Chyba pri ukladaní fotografie.")

async def feedback_command(update: Update, context: CallbackContext):
    context.user_data['awaiting_feedback'] = True
    await update.message.reply_text("📝 Napíšte nám svoje pripomienky alebo návrhy:")

async def handle_feedback_message(update: Update, context: CallbackContext):
    if not context.user_data.get('awaiting_feedback'): return
    success = await asyncio.to_thread(send_feedback_email, update.message.text)
    await update.message.reply_text("✅ Ďakujeme za vašu spätnú väzbu!" if success else "❌ Pri odosielaní došlo k chybe.")
    context.user_data['awaiting_feedback'] = False

async def cancel_feedback(update: Update, context: CallbackContext):
    if context.user_data.get('awaiting_feedback'):
        context.user_data['awaiting_feedback'] = False
        await update.message.reply_text("❌ Odoslanie recenzie bolo zrušené.")

async def status(update: Update, context: CallbackContext):
    current_step = context.user_data.get("survey_step", 0)
    if not current_step: await update.message.reply_text("Otázky ešte neboli zverejnené!")
    elif current_step < len(QUESTIONS): await update.message.reply_text(f"📋 Aktuálny stav: {current_step}/{len(QUESTIONS)}")
    else: await update.message.reply_text("✅ Anketa bola ukončená!")

async def podpis(update: Update, context: CallbackContext):
    await context.bot.send_message(chat_id=CHAT_ID, text=f"Podpisovatel: {SIGNED_BY}")

async def pocasie(update: Update, context: CallbackContext):
    await context.bot.send_message(chat_id=CHAT_ID, text=f"Počasie v Košiciach: {get_weather()}")

async def report_command(update: Update, context: CallbackContext):
    await context.bot.send_message(chat_id=CHAT_ID, text="Počkajte chvíľu, report sa pripravuje...")
    await generate_monthly_report(update, context, month_offset=0)

async def full_report_command(update: Update, context: CallbackContext):
    await context.bot.send_message(chat_id=CHAT_ID, text="Počkajte chvíľu, report sa pripravuje...")
    today = datetime.datetime.now(TIMEZONE)
    await generate_monthly_report(update, context, month_offset=0)

async def last_month_report_command(update: Update, context: CallbackContext):
    await context.bot.send_message(chat_id=CHAT_ID, text="Počkajte chvíľu, report sa pripravuje...")
    await generate_monthly_report(update, context, month_offset=-1)

async def test_check(update: Update, context: CallbackContext):
    from src.bot.jobs import send_daily_check
    await update.message.reply_text("Starting test...")
    await send_daily_check(context)
