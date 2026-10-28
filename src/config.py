import os
import pytz

TOKEN = os.getenv('TOKEN')
OWM_API_KEY = os.getenv('OWM_API_KEY')
CHAT_ID = int(os.getenv('CHAT_ID')) if os.getenv('CHAT_ID') else None
GOOGLE_CREDENTIALS_JSON = os.getenv('GOOGLE_CREDENTIALS_JSON')
GOOGLE_SHEETS_EMAIL = os.getenv('GOOGLE_SHEETS_EMAIL')
SPREADSHEET_NAME = "Building Checklist"
REPORT_SPREADSHEET_NAME = "Building Reports"
TIMEZONE = pytz.timezone("Europe/Bratislava")
SMTP_SERVER = os.getenv('SMTP_SERVER')
SMTP_PORT = int(os.getenv('SMTP_PORT'))
EMAIL_USER = os.getenv('EMAIL_USER')
EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD')
ADMIN_EMAIL = os.getenv('ADMIN_EMAIL')
SIGNED_BY = os.getenv('SIGNED_BY')
IMGBB_API_KEY = os.getenv('IMGBB_API_KEY')
SIGNATURE_IMAGE_URL = os.getenv('SIGNATURE_IMAGE_URL')
RESEND_API_KEY = os.getenv("RESEND_API_KEY")

QUESTIONS = [
    {"text": "Na prvom poschodí fungujú vypínače?", "column": "Vypínače"},
    {"text": "Funguje núdzové osvetlenie na 2. poschodí?", "column": "Osvetlenie"},
    {"text": "Sú všetky hasiace prístroje v poriadku?", "column": "Hasiace prístroje"},
    {"text": "Na druhom poschodí fungujú všetky toalety?", "column": "Toalety"},
    {"text": "Je vlhkosť vzduchu v budove v norme?", "column": "Vlhkosť"}
]
