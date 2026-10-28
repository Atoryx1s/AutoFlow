import datetime
import calendar
import re
import json
import logging
from datetime import timedelta
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from config import GOOGLE_CREDENTIALS_JSON, REPORT_SPREADSHEET_NAME, GOOGLE_SHEETS_EMAIL, QUESTIONS, TIMEZONE, CHAT_ID
from database import get_sheet

logger = logging.getLogger(__name__)

async def generate_monthly_report(update, context, month_offset: int = 0, exclude_last_column: bool = True):
    try:
        sheet = get_sheet()
        if not sheet:
            msg = "❌ Nepodarilo sa pripojiť k Google Sheets"
            if update: await update.message.reply_text(msg)
            else: await context.bot.send_message(chat_id=CHAT_ID, text=msg)
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
        if len(all_rows) <= 1: raise Exception("Tabuľka je prázdna")

        headers = all_rows[0]
        while headers and headers[-1] == '': headers = headers[:-1]
        data_rows = all_rows[1:]

        num_columns = len(headers) - 1 if exclude_last_column else len(headers)
        report_headers = headers[:-1] if exclude_last_column else headers

        filtered_data = []
        for row in data_rows:
            if not row or len(row) < 2: continue
            try:
                row_date = datetime.datetime.strptime(row[0], "%d.%m.%Y")
                row_date = TIMEZONE.localize(row_date.replace(hour=12))
                if month_start <= row_date <= month_end:
                    filtered_data.append(row[:num_columns])
            except (ValueError, IndexError): continue

        if not filtered_data:
            msg = f"Pre {month_start.strftime('%B %Y')} nie sú žiadne údaje"
            if update: await update.message.reply_text(msg)
            else: await context.bot.send_message(chat_id=CHAT_ID, text=msg)
            return

        podpis_col_idx = report_headers.index('Podpis') if 'Podpis' in report_headers else None

        def extract_image_url(cell_value):
            match = re.search(r'=IMAGE\("([^"]+)"\)', str(cell_value))
            return match.group(1) if match else cell_value

        normalized_data = []
        for row in filtered_data:
            row = list(row[:len(report_headers)])
            while len(row) < len(report_headers): row.append('')
            if podpis_col_idx is not None:
                row[podpis_col_idx] = extract_image_url(row[podpis_col_idx])
            normalized_data.append(row)

        creds_dict = json.loads(GOOGLE_CREDENTIALS_JSON)
        creds = Credentials.from_service_account_info(creds_dict, scopes=["https://google.com", "https://googleapis.com"])
        client = gspread.authorize(creds)

        try:
            spreadsheet = client.open(REPORT_SPREADSHEET_NAME)
            try:
                report_sheet = spreadsheet.worksheet(REPORT_SPREADSHEET_NAME)
                sheet_id = report_sheet.id
                creds_obj = Credentials.from_service_account_info(creds_dict, scopes=["https://googleapis.com"])
                service = build('sheets', 'v4', credentials=creds_obj)
                service.spreadsheets().batchUpdate(spreadsheetId=spreadsheet.id, body={"requests": [
                    {"updateCells": {"range": {"sheetId": sheet_id}, "fields": "userEnteredValue,userEnteredFormat"}},
                    {"updateDimensionProperties": {"range": {"sheetId": sheet_id, "dimension": "ROWS", "startIndex": 0, "endIndex": 1000}, "properties": {"pixelSize": 21}, "fields": "pixelSize"}}
                ]}).execute()
            except gspread.WorksheetNotFound:
                report_sheet = spreadsheet.add_worksheet(title=REPORT_SPREADSHEET_NAME, rows=len(normalized_data) + 10, cols=len(report_headers) + 5)
        except gspread.SpreadsheetNotFound:
            spreadsheet = client.create(REPORT_SPREADSHEET_NAME)
            spreadsheet.share(GOOGLE_SHEETS_EMAIL, perm_type='user', role='writer')
            report_sheet = spreadsheet.sheet1
            report_sheet.update_title(REPORT_SPREADSHEET_NAME)

        report_sheet.append_row(report_headers)
        report_sheet.append_rows(normalized_data)

        if podpis_col_idx is not None:
            for row_idx, row in enumerate(normalized_data, start=2):
                url = row[podpis_col_idx]
                if url:
                    report_sheet.update_cell(row_idx, podpis_col_idx + 1, f'=IMAGE("{url}")')
                    report_sheet.format(f"{chr(64 + podpis_col_idx + 1)}{row_idx}", {"verticalAlignment": "MIDDLE", "horizontalAlignment": "CENTER"})

        creds_obj = Credentials.from_service_account_info(creds_dict, scopes=["https://googleapis.com"])
        service = build('sheets', 'v4', credentials=creds_obj)
        requests_body = [{"updateDimensionProperties": {"range": {"sheetId": report_sheet.id, "dimension": "ROWS", "startIndex": i + 1, "endIndex": i + 2}, "properties": {"pixelSize": 21}, "fields": "pixelSize"}} for i in range(len(normalized_data))]

        question_columns = [q["column"] for q in QUESTIONS]
        for row_idx, row in enumerate(normalized_data, start=2):
            for col_name in question_columns:
                if col_name in report_headers:
                    col_idx = report_headers.index(col_name)
                    cell_value = row[col_idx] if col_idx < len(row) else ""
                    bg_color = {"red": 0.565, "green": 0.933, "blue": 0.565} if cell_value == "OK" else ({"red": 1.0, "green": 0.78, "blue": 0.808} if cell_value == "NO" else None)
                    if bg_color:
                        requests_body.append({"repeatCell": {"range": {"sheetId": report_sheet.id, "startRowIndex": row_idx - 1, "endRowIndex": row_idx, "startColumnIndex": col_idx, "endColumnIndex": col_idx + 1}, "cell": {"userEnteredFormat": {"backgroundColor": bg_color, "horizontalAlignment": "CENTER"}}, "fields": "userEnteredFormat(backgroundColor,horizontalAlignment)"}})

        if requests_body:
            service.spreadsheets().batchUpdate(spreadsheetId=spreadsheet.id, body={"requests": requests_body}).execute()

        report_url = f"https://google.com{spreadsheet.id}"
        caption = f"Mesačný report za {month_start.strftime('%B %Y')}\nObdobie: {month_start.strftime('%d.%m.%Y')} - {month_end.strftime('%d.%m.%Y')}\nPočet záznamov: {len(normalized_data)}\n\nOtvoriť v Google Sheets:\n{report_url}"
        
        if update: await update.message.reply_text(caption)
        else: await context.bot.send_message(chat_id=CHAT_ID, text=caption)
    except Exception as e:
        logger.error(f"Chyba pri generovaní reportu: {e}")
        if context: await context.bot.send_message(chat_id=CHAT_ID, text="❌ Chyba pri generovaní reportu")
