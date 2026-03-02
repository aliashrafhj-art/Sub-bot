import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")  # যেমন: '@my_channel'
FONT_PATH = os.getenv("FONT_PATH", "fonts/NotoSansBengali-Regular.ttf")

# যাচাই
if not BOT_TOKEN or not CHANNEL_ID:
    raise ValueError("BOT_TOKEN and CHANNEL_ID must be set in .env")