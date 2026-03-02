import logging
import sys
from pathlib import Path

def setup_logger(name: str = __name__) -> logging.Logger:
    """কনসোল ও ফাইল (ঐচ্ছিক) লগার সেটআপ করে"""
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # কনসোল হ্যান্ডলার (রিয়েল-টাইম আউটপুট)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # ফাইল হ্যান্ডলার (ডিস্কে লগ সংরক্ষণ, Railway‑এ কাজ নাও করতে পারে)
    # log_file = Path('/tmp/bot.log')
    # file_handler = logging.FileHandler(log_file)
    # file_handler.setLevel(logging.DEBUG)
    # file_handler.setFormatter(formatter)
    # logger.addHandler(file_handler)

    return logger