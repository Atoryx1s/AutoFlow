from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (Application, CommandHandler, CallbackQueryHandler, CallbackContext)
from datetime import datetime, timedelta
from io import BytesIO
from telegram.ext import MessageHandler, filters
from fastapi import FastAPI, Request
from fastapi import Request as FastAPIRequest
from google.auth.transport.requests import Request
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from google.oauth2.credentials import Credentials as OAuthCredentials
from google.oauth2.service_account import Credentials
from google.oauth2 import service_account
from google.auth.transport.requests import Request as GoogleRequest
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import pandas as pd
import datetime
import smtplib
import logging
import uvicorn
import requests
import calendar
import os
import io
import re
import pytz
import asyncio
import json
import gspread
import aiohttp
import pickle
import base64

# --- Configuration ---
TOKEN = os.getenv('TOKEN')
OWM_API_KEY = os.getenv('OWM_API_KEY')
CHAT_ID = int(os.getenv('CHAT_ID'))
GOOGLE_CREDENTIALS_JSON = os.getenv('GOOGLE_CREDENTIALS_JSON')
GOOGLE_SHEETS_EMAIL = os.getenv('GOOGLE_SHEETS_EMAIL')
SPREADSHEET_NAME = "Building Checklist"
REPORT_SPREADSHEET_NAME = "Building Checklist - Reports"
TIMEZONE = pytz.timezone("Europe/Bratislava")
SMTP_SERVER = os.getenv('SMTP_SERVER')
SMTP_PORT = int(os.getenv('SMTP_PORT'))
EMAIL_USER = os.getenv('EMAIL_USER')
EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD')
ADMIN_EMAIL = os.getenv('ADMIN_EMAIL')
SIGNED_BY = os.getenv('SIGNED_BY')
SIGNATURE_IMAGE_URL = os.getenv('SIGNATURE_IMAGE_URL')

# --- QUESTIONS ---
QUESTIONS = [
    {"text": "Na prvom poschodí fungujú vypínače?", "column": "Vypínače"},
    {"text": "Funguje núdzové osvetlenie na 2. poschodí?", "column": "Osvetlenie"},
    {"text": "Sú všetky hasiace prístroje v poriadku?", "column": "Hasiace prístroje"},
    {"text": "Na druhom poschodí fungujú všetky toalety?", "column": "Toalety"},
    {"text": "Je vlhkosť vzduchu v budove v norme?", "column": "Vlhkosť"}
]

# --- Logging ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Google Sheets Integration ---
def get_sheet():
    try:
        if not GOOGLE_CREDENTIALS_JSON:
            logger.warning("Google credentials not found")
            return None

        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive"
        ]

        creds_dict = json.loads(GOOGLE_CREDENTIALS_JSON)
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        client = gspread.authorize(creds)

        try:
            sheet = client.open(SPREADSHEET_NAME).sheet1
            logger.info(f"Opened existing spreadsheet: {SPREADSHEET_NAME}")
            return sheet
        except gspread.SpreadsheetNotFound:
            try:
                logger.info(f"Creating new spreadsheet: {SPREADSHEET_NAME}")
                sheet = client.create(SPREADSHEET_NAME)
                sheet.share(GOOGLE_SHEETS_EMAIL, perm_type='user', role='writer')
                sheet = sheet.sheet1

                headers = ["Dátum", "Počasie"] + [q["column"] for q in QUESTIONS] + ["Podpis", "Podpísal", "Fotografie"]
                sheet.append_row(headers)
                logger.info("Added headers to new spreadsheet")
                return sheet
            except Exception as create_error:
                logger.error(f"Error creating spreadsheet: {create_error}")
                return None
        except Exception as e:
            logger.warning(f"Error accessing spreadsheet: {e}")
            return None

    except Exception as e:
        logger.error(f"Google Sheets error: {e}")
        return None
    
# --- Signature handling ---
def add_signature_to_report(signature_url=None):
    try:
        sheet = get_sheet()
        if not sheet:
            return False

        date = datetime.date.today().strftime("%d.%m.%Y")
        all_rows = sheet.get_all_values()
        last_row = None

        for i, row in enumerate(all_rows[1:], start=2):
            if row and row[0] == date:
                last_row = i
                break

        if last_row:
            sign_col = 2 + len(QUESTIONS) + 1
            signed_by_col = sign_col + 1

            signature_url_to_use = signature_url or SIGNATURE_IMAGE_URL

            if signature_url_to_use:
                image_formula = f'=IMAGE("{signature_url_to_use}")'
                sheet.update_cell(last_row, sign_col, image_formula)

                sheet.format(f"{chr(64 + sign_col)}{last_row}", {
                    "verticalAlignment": "MIDDLE",
                    "horizontalAlignment": "CENTER"
                })
            else:
                sheet.update_cell(last_row, sign_col, "🖋️ Podpísané")

            sheet.update_cell(last_row, signed_by_col, SIGNED_BY)
            logger.info(f"Signature image added by {SIGNED_BY}")
            return True

        return False

    except Exception as e:
        logger.error(f"Error adding signature: {e}")
        return False

# --- Feedback ---
def send_feedback_email(user_name, user_id, message):
    try:
        if not all([EMAIL_USER, EMAIL_PASSWORD, ADMIN_EMAIL]):
            logger.error("Email configuration not set")
            return False

        msg = MIMEMultipart()
        msg['From'] = EMAIL_USER
        msg['To'] = ADMIN_EMAIL
        msg['Subject'] = f"📝 Spätná väzba od používateľa Telegram bota"

        local_tz = pytz.timezone("Europe/Bratislava")
        local_time = datetime.datetime.now(local_tz)

        body = f"""
        📨 Nová spätná väzba od používateľa:

        👤 Používateľ: {user_name}
        📅 Čas: {local_time.strftime('%Y-%m-%d %H:%M:%S')}

        💬 Správa:
        {message}
        
        S pozdravom
        
        {user_name}
        
        --
        Odeslané z Building Checklist Bot
        """

        msg.attach(MIMEText(body, 'plain'))

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASSWORD)
            server.send_message(msg)

        logger.info(f"Feedback email sent from user {user_id}")
        return True

    except Exception as e:
        logger.error(f"Error sending feedback email: {e}")
        return False

async def feedback_command(update: Update, context: CallbackContext):
    user = update.effective_user
    context.user_data['awaiting_feedback'] = True

    await update.message.reply_text(
        "📝 Napíšte nám svoje pripomienky alebo návrhy:\n\n"
        "Čo sa vám páči? Čo by sa dalo vylepšiť?"
        "Máte nejaké problémy s fungovaním bota?"
    )

# --- Feedback message handler ---
async def handle_feedback_message(update: Update, context: CallbackContext):
    if not context.user_data.get('awaiting_feedback'):
        return

    user = update.effective_user
    message_text = update.message.text

    success = await asyncio.to_thread(
        send_feedback_email,
        user.full_name,
        user.id,
        message_text
    )

    if success:
        await update.message.reply_text(
            "✅ Ďakujeme za vašu spätnú väzbu! Poslal som ju vývojárovi.\n\n"
            "Váš názor je pre nás veľmi dôležitý! 💙"
        )
    else:
        await update.message.reply_text(
            "❌ Pri odosielaní spätnej väzby došlo k chybe."
            "Skúste to prosím neskôr."
        )
    context.user_data['awaiting_feedback'] = False

# --- Cancel feedback ---
async def cancel_feedback(update: Update, context: CallbackContext):
    if context.user_data.get('awaiting_feedback'):
        context.user_data['awaiting_feedback'] = False
        await update.message.reply_text("❌ Odoslanie recenzie bolo zrušené.")

# --- Weather ---
def get_weather(city="Kosice"):
    try:
        url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={OWM_API_KEY}&units=metric&lang=sk"
        response = requests.get(url, timeout=10)
        data = response.json()
        if response.status_code == 200:
            temp = data["main"]["temp"]
            desc = data["weather"][0]["description"].capitalize()
            return f"{desc}, {round(temp)}°C"
        return "Neznámé"
    except Exception:
        return "Neznámé"

# --- Utility functions ---
def get_current_time():
    local_tz = pytz.timezone("Europe/Bratislava")

    local_time = datetime.datetime.now(local_tz)
    return local_time.strftime("%H:%M:%S")

def get_current_date():
    local_tz = TIMEZONE
    local_date = datetime.datetime.now(local_tz)
    return local_date.strftime("%d.%m.%Y")

# --- Data Processing ---
def log_or_update_data(chat_id, question_idx, answer, photo_urls=None):
    try:
        sheet = get_sheet()
        if not sheet:
            logger.warning("Google Sheets not available, data not saved")
            return True

        date = get_current_date()
        weather = get_weather()

        existing_row = None
        all_rows = sheet.get_all_values()
        for i, row in enumerate(all_rows[1:], start=2):
            if row and row[0] == date:
                existing_row = i
                break

        if existing_row:
            if answer is not None:
                col_index = 2 + question_idx
                sheet.update_cell(existing_row, col_index + 1, answer)

            if photo_urls:
                start_photo_col = 2 + len(QUESTIONS) + 3
                for i, url in enumerate(photo_urls):
                    photo_col = start_photo_col + i
                    sheet.update_cell(existing_row, photo_col, f"{url}")

        else:
            base_columns = 2 + len(QUESTIONS) + 3
            extra_columns = len(photo_urls) if photo_urls else 0
            total_columns = base_columns + extra_columns

            new_row = [date, weather] + [""] * len(QUESTIONS) + ["", "", ""] + [""] * extra_columns

            if answer is not None:
                new_row[2 + question_idx] = answer
            if photo_urls:
                start_photo_col = 2 + len(QUESTIONS) + 3
                for i, url in enumerate(photo_urls):
                    new_row[start_photo_col + i] = f"{url}"

            sheet.append_row(new_row)

        logger.info(f"Data saved to Google Sheets for question {question_idx}")
        return True

    except Exception as e:
        logger.error(f"Error saving to Google Sheets: {e}")
        return True

# --- Photo handling ---
async def photo_command(update: Update, context: CallbackContext):
    current_step = context.user_data.get("survey_step", 0)

    question_idx = current_step - 1
    if question_idx >= len(QUESTIONS):
        await update.message.reply_text("✅ Anketa je už ukončená!")
        return

    question = QUESTIONS[question_idx]
    current_photos = context.user_data.get("current_photos", [])

    await update.message.reply_text(
        f"📷 Pošlite fotografiu/fotografie\n\n"
        f"💡 Môžete poslať niekoľko fotografií – automaticky sa uložia.\n"
        f"📸 Už uložené: {len(current_photos)} foto\n\n"
        f"Stačí poslať fotografie jednu po druhej alebo hneď niekoľko naraz."
    )

# --- Main survey flow ---
async def send_question(chat_id, context, question_idx):
    if question_idx >= len(QUESTIONS):
        success = await asyncio.to_thread(add_signature_to_report)

        if success:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"✅ Kontrola bola dokončená. Správa bola podpísaná! Pekný deň!"
            )
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text="✅ Kontrola bola dokončená. Prajeme vám pekný deň!"
            )
        return

    question_text = QUESTIONS[question_idx]["text"]
    keyboard = [
        [InlineKeyboardButton("✅ V poriadku", callback_data=f'OK_{question_idx}')],
        [InlineKeyboardButton("❌ Nie", callback_data=f'NO_{question_idx}')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(chat_id=chat_id, text=question_text, reply_markup=reply_markup)

# --- Button handler ---
async def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    data_parts = query.data.split('_')
    answer = data_parts[0]
    question_idx = int(data_parts[1])

    success = await asyncio.to_thread(log_or_update_data, query.message.chat_id, question_idx, answer)

    if not success:
        await query.message.reply_text("❌ Chyba pri ukladaní údajov. Skúste to znovu.")
        return

    question_text = QUESTIONS[question_idx]["text"]
    await query.edit_message_text(text=f"{question_text}\nOdpoveď: {'✅' if answer == 'OK' else '❌'}")

    context.user_data["survey_step"] = question_idx + 1

    if context.user_data["survey_step"] < len(QUESTIONS):
        await send_question(query.message.chat_id, context, context.user_data["survey_step"])
    else:
        success = await asyncio.to_thread(add_signature_to_report)
        if success:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=f"✅ Kontrola bola dokončená. Správa bola podpísaná! Ďakujem 😉"
            )
        else:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="✅ Anketa je ukončená! Ďakujeme 😉"
            )
        context.user_data.pop("survey_step", None)

def is_weekday():
    today = datetime.datetime.now(TIMEZONE).weekday()
    return today < 5

# --- Daily check ---
async def send_daily_check(context: CallbackContext):
    try:
        if not is_weekday():
            logger.info("Dnes je voľný deň – oznámenie sa nezasiela")
            return

        date = datetime.date.today()
        formatted = date.strftime("%d.%m.%Y")
        await context.bot.send_message(chat_id=CHAT_ID, text=f"Ahoj, Krosavčik!")
        await context.bot.send_message(chat_id=CHAT_ID, text=f"Denná kontrola budovy bola aktivovaná.😃")
        await context.bot.send_message(chat_id=CHAT_ID, text=f"🔔 Dnes {formatted} a my máme kontrolu nad budovou!")
        weather = get_weather()
        await context.bot.send_message(chat_id=CHAT_ID, text=f"Počasie: {weather}")
        await context.bot.send_message(chat_id=CHAT_ID, text="Tak poďme na to!😊")

        await send_question(CHAT_ID, context, 0)

    except Exception as e:
        logger.error(f"Chyba je v send_daily_check: {e}")

# --- Status command ---
async def status(update: Update, context: CallbackContext):
    current_step = context.user_data.get("survey_step", 0)
    if not current_step:
        await context.bot.send_message(chat_id=CHAT_ID, text="Otázky ešte neboli zverejnené!")

    elif current_step < len(QUESTIONS):
        current_question = QUESTIONS[current_step - 1]["text"]
        await update.message.reply_text(
            f"📋 Aktuálny stav:\n"
            f"• Pokrok: {current_step}/{len(QUESTIONS)}\n"
            f"Aby ste mohli pokračovať, odpovedzte na aktuálnu otázku."
        )
    else:
        await update.message.reply_text("✅ Anketa bola ukončená! Použite /start pre novú anketu.")

# --- photo ---
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

    permanent_url = await upload_to_freeimagehost(file_path)

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

# --- Upload to FreeImage.Host ---
async def upload_to_freeimagehost(file_path: str) -> str:
    try:
        async with aiohttp.ClientSession() as session:
            telegram_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_path}"
            async with session.get(telegram_url) as resp:
                if resp.status != 200:
                    raise ValueError(f"Chyba pri načítaní: {resp.status}")

                image_data = await resp.read()

                form_data = aiohttp.FormData()
                form_data.add_field('source', image_data, filename='photo.jpg')

                async with session.post(
                        'https://freeimage.host/api/1/upload',
                        data=form_data,
                        params={'key': OWM_API_KEY}
                ) as upload_resp:
                    if upload_resp.status == 200:
                        data = await upload_resp.json()
                        return data['image']['url']

        return f"https://api.telegram.org/file/bot{TOKEN}/{file_path}"

    except Exception as e:
        logger.error(f"Error uploading to FreeImage.Host: {e}")
        return f"https://api.telegram.org/file/bot{TOKEN}/{file_path}"

async def podpis(update: Update, context: CallbackContext):
    await context.bot.send_message(chat_id=CHAT_ID, text=f"Podpisovatel: {SIGNED_BY}")

async def pocasie(update: Update, contex: CallbackContext):
    pogoda = get_weather()
    await contex.bot.send_message(chat_id=CHAT_ID, text=f"Počasie v Košiciach: {pogoda}")

# --- Monthly report generation ---
async def generate_monthly_report(update: Update, context: CallbackContext, month_offset: int = 0, exclude_last_column: bool = True):
    try:
        sheet = get_sheet()
        if not sheet:
            error_msg = "❌ Nepodarilo sa pripojiť k Google Sheets"
            if update:
                await update.message.reply_text(error_msg)
            else:
                await context.bot.send_message(chat_id=CHAT_ID, text=error_msg)
            return

        today = datetime.datetime.now(TIMEZONE)
        month_start = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        if month_offset == -1:
            last_month = month_start - timedelta(days=1)
            month_start = last_month.replace(day=1)
            month_end = last_month.replace(day=calendar.monthrange(last_month.year, last_month.month)[1])
        else:
            month_end = today.replace(hour=23, minute=59, second=59)

        all_rows = sheet.get_all_values(value_render_option='FORMULA')

        if len(all_rows) <= 1:
            raise Exception("Tabuľka je prázdna")

        headers = all_rows[0]
        while headers and headers[-1] == '':
            headers = headers[:-1]
        data_rows = all_rows[1:]

        if exclude_last_column:
            num_columns = len(headers) - 1
            report_headers = headers[:-1]
        else:
            num_columns = len(headers)
            report_headers = headers

        filtered_data = []
        for row in data_rows:
            if not row or len(row) < 2:
                continue
            try:
                row_date = datetime.datetime.strptime(row[0], "%d.%m.%Y")
                row_date = TIMEZONE.localize(row_date.replace(hour=12))
                if month_start <= row_date <= month_end:
                    filtered_data.append(row[:num_columns])
            except (ValueError, IndexError):
                continue

        if not filtered_data:
            month_name = month_start.strftime("%B %Y")
            msg = f"Pre {month_name} nie sú žiadne údaje"
            if update:
                await update.message.reply_text(msg)
            else:
                await context.bot.send_message(chat_id=CHAT_ID, text=msg)
            return

        podpis_col_idx = report_headers.index('Podpis') if 'Podpis' in report_headers else None

        def extract_image_url(cell_value):
            if not cell_value:
                return ''
            match = re.search(r'=IMAGE\("([^"]+)"\)', str(cell_value))
            if match:
                return match.group(1)
            return cell_value

        normalized_data = []
        for row in filtered_data:
            row = list(row[:len(report_headers)])
            while len(row) < len(report_headers):
                row.append('')
            if podpis_col_idx is not None:
                row[podpis_col_idx] = extract_image_url(row[podpis_col_idx])
            normalized_data.append(row)

        creds_dict = json.loads(GOOGLE_CREDENTIALS_JSON)
        creds = Credentials.from_service_account_info(creds_dict, scopes=[
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive"
        ])
        client = gspread.authorize(creds)

        report_name = f"Report_{month_start.strftime('%B_%Y')}"

        try:
            spreadsheet = client.open(REPORT_SPREADSHEET_NAME)
            logger.info(f"Opened existing reports spreadsheet")

            try:
                report_sheet = spreadsheet.worksheet(REPORT_SPREADSHEET_NAME)
                report_sheet.clear()
                logger.info(f"Cleared existing sheet: {REPORT_SPREADSHEET_NAME}")
            except gspread.WorksheetNotFound:
                report_sheet = spreadsheet.add_worksheet(
                    title=REPORT_SPREADSHEET_NAME,
                    rows=len(normalized_data) + 10,
                    cols=len(report_headers) + 5
                )
                logger.info(f"Created new sheet: {REPORT_SPREADSHEET_NAME}")

        except gspread.SpreadsheetNotFound:
            spreadsheet = client.create(REPORT_SPREADSHEET_NAME)
            spreadsheet.share(GOOGLE_SHEETS_EMAIL, perm_type='user', role='writer')
            report_sheet = spreadsheet.sheet1
            report_sheet.update_title(REPORT_SPREADSHEET_NAME)
            logger.info(f"Created new reports spreadsheet: {REPORT_SPREADSHEET_NAME}")

        report_sheet.append_row(report_headers)
        report_sheet.append_rows(normalized_data)

        if podpis_col_idx is not None:
            podpis_sheet_col = podpis_col_idx + 1
            for row_idx, row in enumerate(normalized_data, start=2):
                url = row[podpis_col_idx]
                if url:
                    report_sheet.update_cell(row_idx, podpis_sheet_col, f'=IMAGE("{url}")')
                    report_sheet.format(f"{chr(64 + podpis_sheet_col)}{row_idx}", {
                        "verticalAlignment": "MIDDLE",
                        "horizontalAlignment": "CENTER"
                    })

        spreadsheet_id = report_sheet.spreadsheet.id
        sheet_id = report_sheet.id

        creds_obj = Credentials.from_service_account_info(creds_dict, scopes=[
            "https://www.googleapis.com/auth/spreadsheets"
        ])
        service = build('sheets', 'v4', credentials=creds_obj)

        requests_body = []
        for i in range(len(normalized_data)):
            requests_body.append({
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": sheet_id,
                        "dimension": "ROWS",
                        "startIndex": i + 1,
                        "endIndex": i + 2
                    },
                    "properties": {"pixelSize": 21},
                    "fields": "pixelSize"
                }
            })

        if requests_body:
            service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"requests": requests_body}
            ).execute()

        report_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
        caption = (
            f"Mesačný report za {month_start.strftime('%B %Y')}\n"
            f"Obdobie: {month_start.strftime('%d.%m.%Y')} - {month_end.strftime('%d.%m.%Y')}\n"
            f"Počet záznamov: {len(normalized_data)}\n\n"
            f"Otvoriť v Google Sheets:\n{report_url}"
        )

        if update:
            await update.message.reply_text(caption)
        else:
            await context.bot.send_message(chat_id=CHAT_ID, text=caption)

        logger.info(f"Report {report_name} úspešne vytvorený: {report_url}")

    except Exception as e:
        error_msg = f"Chyba pri generovaní reportu: {str(e)}"
        logger.error(error_msg)

# --- Monthly auto report ---
async def monthly_auto_report(context: CallbackContext):
    try:
        today = datetime.datetime.now(TIMEZONE)

        last_day = calendar.monthrange(today.year, today.month)[1]

        if today.day == last_day:
            logger.info("Spúšťam automatický mesačný report")
            await generate_monthly_report(None, context, month_offset=0)
        else:
            logger.info(f"Dnes nie je posledný deň mesiaca ({today.day}/{last_day})")

    except Exception as e:
        logger.error(f"Chyba v monthly_auto_report: {e}")

# --- Manual report command ---
async def report_command(update: Update, context: CallbackContext):
    await context.bot.send_message(chat_id=CHAT_ID, text="Počkajte chvíľu, report sa pripravuje na odoslanie.")
    await generate_monthly_report(update, context, month_offset=0)

# --- Full report command (includes last day of month data) ---
async def full_report_command(update: Update, context: CallbackContext):
    today = datetime.datetime.now(TIMEZONE)
    last_day = calendar.monthrange(today.year, today.month)[1]

    if today.day != last_day:
        await update.message.reply_text(
            f"⚠️ Dnes nie je posledný deň mesiaca.\n"
            f"Report bude obsahovať údaje od 1.{today.month}. do {today.day}.{today.year}\n\n"
            f"Počkajte chvíľu, report sa pripravuje na odoslanie."
        )

    await generate_monthly_report(update, context, month_offset=0)

# --- Last month report command ---
async def last_month_report_command(update: Update, context: CallbackContext):
    await generate_monthly_report(update, context, month_offset=-1)

telegram_app = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global telegram_app

    logger.info("Starting bot initialization...")
    telegram_app = Application.builder().token(TOKEN).build()

    telegram_app.add_handler(CallbackQueryHandler(button_handler))
    telegram_app.add_handler(CommandHandler("photo", photo_command))
    telegram_app.add_handler(MessageHandler(filters.PHOTO, photo))
    telegram_app.add_handler(CommandHandler("feedback", feedback_command))
    telegram_app.add_handler(CommandHandler("cancel", cancel_feedback))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_feedback_message))
    telegram_app.add_handler(CommandHandler("weather", pocasie))
    telegram_app.add_handler(CommandHandler("status", status))
    telegram_app.add_handler(CommandHandler("podpisovatel", podpis))
    telegram_app.add_handler(CommandHandler("report", report_command))
    telegram_app.add_handler(CommandHandler("full_report", full_report_command))
    telegram_app.add_handler(CommandHandler("last_month", last_month_report_command))

    telegram_app.job_queue.run_daily(
        send_daily_check,
        time=datetime.time(hour=7, minute=00, tzinfo=TIMEZONE),
        name="daily_message"
    )

    telegram_app.job_queue.run_daily(
        monthly_auto_report,
        time=datetime.time(hour=12, minute=00, tzinfo=TIMEZONE),
        name="monthly_report"
    )

    await telegram_app.initialize()
    await telegram_app.start()

    logger.info("✅ Bot started successfully")

    yield

fastapi_app = FastAPI(lifespan=lifespan)

# --- Debug endpoint for Google Sheets connection ---
@fastapi_app.get("/debug/google-sheets")
async def debug_google_sheets():
    if not GOOGLE_CREDENTIALS_JSON:
        return {"status": "error", "message": "GOOGLE_CREDENTIALS_JSON not set"}

    try:
        creds_dict = json.loads(GOOGLE_CREDENTIALS_JSON)
        sheet = get_sheet()
        if sheet:
            return {
                "status": "connected",
                "spreadsheet": SPREADSHEET_NAME,
                "client_email": creds_dict.get("client_email"),
                "project_id": creds_dict.get("project_id")
            }
        else:
            return {
                "status": "error",
                "message": "Could not connect to Google Sheets",
                "client_email": creds_dict.get("client_email")
            }

    except json.JSONDecodeError:
        return {"status": "error", "message": "Invalid JSON format"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@fastapi_app.post(f"/webhook/{TOKEN}")
async def telegram_webhook(request: FastAPIRequest):
    global telegram_app
    try:
        data = await request.json()
        update = Update.de_json(data, telegram_app.bot)
        await telegram_app.process_update(update)
        return JSONResponse(content={"ok": True})
    except Exception as e:
        logger.error(f"Error in webhook: {e}")
        return JSONResponse(content={"ok": False})

@fastapi_app.get("/")
async def root():
    return {"status": "Bot is running", "timestamp": datetime.datetime.now().isoformat()}

@fastapi_app.head("/")
async def root_head():
    return JSONResponse(status_code=200, content=None)

@fastapi_app.get("/health")
async def health_check():
    return {"status": "healthy"}

# --- Run the app ---
if __name__ == "__main__":
    port = int(os.getenv('PORT', 8080))
    uvicorn.run(fastapi_app, host="0.0.0.0", port=port)