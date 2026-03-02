import asyncio
from telegram import Bot
from telegram.error import TimedOut, RetryAfter
from logger import setup_logger

logger = setup_logger(__name__)

async def upload_to_telegram(bot: Bot, channel_id: str, file_path: str, caption: str = ""):
    """ভিডিও ফাইল চ্যানেলে আপলোড করে, টাইমআউট সামলায়"""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            with open(file_path, 'rb') as f:
                await bot.send_video(
                    chat_id=channel_id,
                    video=f,
                    caption=caption,
                    read_timeout=300,
                    write_timeout=300,
                    connect_timeout=300,
                    pool_timeout=300
                )
            logger.info(f"Uploaded {file_path} to {channel_id}")
            return
        except TimedOut:
            logger.warning(f"Upload timeout (attempt {attempt+1})")
            await asyncio.sleep(5)
        except RetryAfter as e:
            logger.warning(f"Rate limited, retry after {e.retry_after}s")
            await asyncio.sleep(e.retry_after)
        except Exception as e:
            logger.exception("Upload failed")
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(10)
            # uploader.py তে ডিবাগ লগ যোগ করুন
async def upload_to_telegram(bot: Bot, channel_id: str, file_path: str, caption: str = ""):
    logger.info(f"Attempting to upload to channel: {channel_id}")
    try:
        # ... existing code ...
    except Exception as e:
        logger.error(f"Channel {channel_id} upload failed: {e}")
        raise
