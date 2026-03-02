import pysubs2
from pathlib import Path
from logger import setup_logger

logger = setup_logger(__name__)

async def style_subtitle(subtitle_path: str, font_path: str) -> str:
    """
    সাবটাইটেলকে ASS‑এ রূপান্তর করে নেটফ্লিক্স স্টাইল দেয়।
    font_path: .ttf ফাইলের সম্পূর্ণ পাথ।
    """
    subs = pysubs2.load(subtitle_path, encoding="utf-8")
    logger.info(f"Loaded subtitle: {subtitle_path}")

    # স্টাইল ডিফাইন
    style = pysubs2.SSAStyle()
    style.fontname = font_path  # ফন্ট ফাইলের পাথ
    style.fontsize = 24
    style.primarycolor = pysubs2.Color(255, 255, 255, 0)    # সাদা
    style.outlinecolor = pysubs2.Color(0, 0, 0, 100)        # কালো আউটলাইন
    style.backcolor = pysubs2.Color(0, 0, 0, 80)            # স্বচ্ছ ব্যাকগ্রাউন্ড
    style.bold = True
    style.outline = 2
    style.shadow = 1
    style.alignment = 2  # নিচে মাঝখানে
    style.marginv = 30
    style.encoding = 1

    subs.styles["Netflix"] = style
    for line in subs.events:
        line.style = "Netflix"

    output_path = subtitle_path.replace('.srt', '_styled.ass')
    subs.save(output_path, format_="ass")
    logger.info(f"Styled subtitle saved: {output_path}")
    return output_path