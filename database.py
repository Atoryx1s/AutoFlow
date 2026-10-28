import json
import logging
import datetime
import gspread
from google.oauth2.service_account import Credentials
from config import GOOGLE_CREDENTIALS_JSON, SPREADSHEET_NAME, GOOGLE_SHEETS_EMAIL, QUESTIONS, SIGNATURE_IMAGE_URL, SIGNED_BY, TIMEZONE
from services.weather import get_weather

logger = logging.getLogger(__name__)

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

def get_current_date():
    return datetime.datetime.now(TIMEZONE).strftime("%d.%m.%Y")

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

        def apply_color(row_num, col_num, answer_value):
            cell_address = f"{chr(64 + col_num)}{row_num}"

            if answer_value == "OK":
                bg_color = {"red": 0.565, "green": 0.933, "blue": 0.565}
            else:
                bg_color = {"red": 1.0, "green": 0.78, "blue": 0.808}

            sheet.format(cell_address, {
                "backgroundColor": bg_color,
                "horizontalAlignment": "CENTER"
            })

        if existing_row:
            if answer is not None:
                col_index = 2 + question_idx
                sheet.update_cell(existing_row, col_index + 1, answer)
                apply_color(existing_row, col_index + 1, answer)

            if photo_urls:
                start_photo_col = 2 + len(QUESTIONS) + 3
                for i, url in enumerate(photo_urls):
                    photo_col = start_photo_col + i
                    sheet.update_cell(existing_row, photo_col, f"{url}")

        else:
            base_columns = 2 + len(QUESTIONS) + 3
            extra_columns = len(photo_urls) if photo_urls else 0

            new_row = [date, weather] + [""] * len(QUESTIONS) + ["", "", ""] + [""] * extra_columns

            if answer is not None:
                new_row[2 + question_idx] = answer
            if photo_urls:
                start_photo_col = 2 + len(QUESTIONS) + 3
                for i, url in enumerate(photo_urls):
                    new_row[start_photo_col + i] = f"{url}"

            sheet.append_row(new_row)

            new_row_num = len(sheet.get_all_values())
            if answer is not None:
                col_index = 2 + question_idx
                apply_color(new_row_num, col_index + 1, answer)

        logger.info(f"Data saved to Google Sheets for question {question_idx}")
        return True

    except Exception as e:
        logger.error(f"Error saving to Google Sheets: {e}")
        return True

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

