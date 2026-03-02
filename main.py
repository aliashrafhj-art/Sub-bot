# single_bot.py - পুরো বট এক ফাইলে

import os
import logging
import asyncio
import subprocess
import aiohttp
import aiofiles
from pathlib import Path
from tempfile import gettempdir
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ConversationHandler, filters, ContextTypes
from yt_dlp import YoutubeDL
import pysubs2

# ================== কনফিগারেশন ==================
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
FONT_PATH = os.getenv("FONT_PATH", "fonts/NotoSansBengali-Regular.ttf")

if not BOT_TOKEN or not CHANNEL_ID:
    raise ValueError("BOT_TOKEN and CHANNEL_ID must be set in .env")

# ================== লগিং ==================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# ================== কনভার্সেশন স্টেট ==================
WAITING_SUBTITLE = 1
user_sessions = {}

# ================== কাস্টম এক্সেপশন ==================
class ExtractionError(Exception):
    pass

class DownloadError(Exception):
    pass

class BurnError(Exception):
    pass

# ================== এক্সট্র্যাক্টর ==================
async def extract_info(url: str) -> dict:
    def _sync_extract():
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'writesubtitles': True,
            'writeautomaticsub': True,
            'subtitleslangs': ['en', 'ko', 'ja', 'bn'],
            'skip_download': True,
        }
        with YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(url, download=False)
                logger.info(f"Extraction successful for {url}")
                return info
            except Exception as e:
                logger.exception(f"yt-dlp extraction failed for {url}")
                raise ExtractionError(f"yt-dlp error: {e}")

    loop = asyncio.get_event_loop()
    info = await loop.run_in_executor(None, _sync_extract)

    video_url = None
    if 'url' in info:
        video_url = info['url']
    elif 'formats' in info:
        formats = info['formats']
        for f in formats:
            if f.get('ext') == 'mp4' and f.get('vcodec') != 'none' and f.get('acodec') != 'none':
                video_url = f['url']
                break
        if not video_url:
            for f in formats:
                if f.get('vcodec') != 'none':
                    video_url = f['url']
                    break

    if not video_url:
        raise ExtractionError("No video URL found")

    subtitles = {}
    if 'subtitles' in info and info['subtitles']:
        subtitles = info['subtitles']
    elif 'automatic_captions' in info and info['automatic_captions']:
        subtitles = info['automatic_captions']

    return {
        'video_url': video_url,
        'subtitles': subtitles,
        'title': info.get('title', 'video'),
        'ext': info.get('ext', 'mp4')
    }

# ================== ডাউনলোডার ==================
async def download_video(url: str, chat_id: int, progress_callback=None) -> str:
    output_path = Path(gettempdir()) / f"video_{chat_id}.mp4"

    if url.endswith('.m3u8'):
        cmd = ['ffmpeg', '-i', url, '-c', 'copy', '-bsf:a', 'aac_adtstoasc', str(output_path)]
        logger.info(f"Downloading HLS stream: {url}")
        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            logger.error(f"FFmpeg error: {stderr.decode()}")
            raise DownloadError("FFmpeg HLS download failed")
        logger.info(f"HLS download completed: {output_path}")
    else:
        logger.info(f"Downloading direct video: {url}")
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                resp.raise_for_status()
                total_size = int(resp.headers.get('content-length', 0))
                downloaded = 0
                async with aiofiles.open(output_path, 'wb') as f:
                    async for chunk in resp.content.iter_chunked(8192):
                        await f.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback and total_size:
                            await progress_callback(downloaded, total_size)
        logger.info(f"Direct download completed: {output_path}")

    return str(output_path)

async def download_video(url: str, chat_id: int, progress_callback=None) -> str:
    output_path = Path(gettempdir()) / f"video_{chat_id}.mp4"
    
    # m3u8 লিংক হলে
    if '.m3u8' in url:
    headers = {
        'Referer': 'https://dramacool9.com.ro/',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    header_args = []
    for key, value in headers.items():
        header_args.extend(['-headers', f'{key}: {value}'])
    cmd = ['ffmpeg', '-i', url, *header_args, '-c', 'copy', '-bsf:a', 'aac_adtstoasc', '-y', str(output_path)]
     
        logger.info(f"Downloading HLS stream with referer: {url}")
        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            logger.error(f"FFmpeg error: {stderr.decode()}")
            raise DownloadError("FFmpeg HLS download failed")
    else:
        # সরাসরি HTTP ডাউনলোড
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                resp.raise_for_status()
                async with aiofiles.open(output_path, 'wb') as f:
                    async for chunk in resp.content.iter_chunked(8192):
                        await f.write(chunk)
    
    logger.info(f"Download completed: {output_path}")
    return str(output_path)
======== সাবটাইটেল স্টাইলার ==================
async def style_subtitle(subtitle_path: str, font_path: str) -> str:
    subs = pysubs2.load(subtitle_path, encoding="utf-8")
    logger.info(f"Loaded subtitle: {subtitle_path}")

    style = pysubs2.SSAStyle()
    style.fontname = font_path
    style.fontsize = 24
    style.primarycolor = pysubs2.Color(255, 255, 255, 0)
    style.outlinecolor = pysubs2.Color(0, 0, 0, 100)
    style.backcolor = pysubs2.Color(0, 0, 0, 80)
    style.bold = True
    style.outline = 2
    style.shadow = 1
    style.alignment = 2
    style.marginv = 30
    style.encoding = 1

    subs.styles["Netflix"] = style
    for line in subs.events:
        line.style = "Netflix"

    output_path = subtitle_path.replace('.srt', '_styled.ass')
    subs.save(output_path, format_="ass")
    logger.info(f"Styled subtitle saved: {output_path}")
    return output_path

# ================== বার্নার ==================
async def burn_subtitle(video_path: str, subtitle_path: str) -> str:
    output_path = Path(gettempdir()) / f"output_{Path(video_path).stem}_sub.mp4"

    if subtitle_path.endswith('.ass'):
        vf = f"ass='{subtitle_path}'"
    else:
        vf = f"subtitles='{subtitle_path}'"

    cmd = [
        'ffmpeg',
        '-i', video_path,
        '-vf', vf,
        '-c:a', 'copy',
        '-preset', 'ultrafast',
        '-y',
        str(output_path)
    ]

    logger.info(f"Burning subtitles with command: {' '.join(cmd)}")
    process = await asyncio.create_subprocess_exec(
        *cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        logger.error(f"FFmpeg burn error: {stderr.decode()}")
        raise BurnError("Subtitle burning failed")
    logger.info(f"Burned video saved: {output_path}")
    return str(output_path)

# ================== আপলোডার ==================
async def upload_to_telegram(bot, channel_id: str, file_path: str, caption: str = ""):
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
        except Exception as e:
            logger.warning(f"Upload attempt {attempt+1} failed: {e}")
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(5)

# ================== বট হ্যান্ডলার ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "স্বাগতম! ভিডিও প্রসেস করতে একটি এপিসোড লিংক পাঠান।\n"
        "উদাহরণ: https://example.com/episode-123"
    )

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    chat_id = update.effective_chat.id

    msg = await update.message.reply_text("⏳ লিংক প্রসেস করা হচ্ছে...")

    try:
        info = await extract_info(url)
        await msg.edit_text("✅ ভিডিও তথ্য পাওয়া গেছে। ডাউনলোড শুরু...")

        async def progress(downloaded, total):
            percent = (downloaded / total) * 100
            await msg.edit_text(f"📥 ডাউনলোড: {percent:.1f}%")

        video_path = await download_video(info['video_url'], chat_id, progress)

        if info['subtitles']:
            lang = list(info['subtitles'].keys())[0]
            sub_url = info['subtitles'][lang][0]['url']
            subtitle_path = await download_subtitle(sub_url, chat_id)

            user_sessions[chat_id] = {
                'video_path': video_path,
                'subtitle_path': subtitle_path,
                'title': info['title']
            }

            keyboard = [
                [InlineKeyboardButton("✅ এই সাবটাইটেল ব্যবহার করি", callback_data='use_extracted')],
                [InlineKeyboardButton("📂 নিজের সাবটাইটেল আপলোড করব", callback_data='upload_own')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await msg.edit_text(
                f"ভিডিও ডাউনলোড সম্পন্ন!\n"
                f"এক্সট্র্যাক্ট করা সাবটাইটেল ভাষা: {lang}\n"
                f"আপনি কি এই সাবটাইটেল ব্যবহার করতে চান?",
                reply_markup=reply_markup
            )
            return
        else:
            user_sessions[chat_id] = {'video_path': video_path, 'title': info['title']}
            await msg.edit_text("কোনো সাবটাইটেল পাওয়া যায়নি। অনুগ্রহ করে আপনার বাংলা সাবটাইটেল ফাইল (.srt বা .ass) আপলোড করুন।")
            return WAITING_SUBTITLE

    except ExtractionError as e:
        logger.error(f"Extraction error: {e}")
        await msg.edit_text(f"❌ ভিডিও তথ্য সংগ্রহ ব্যর্থ: {e}")
    except DownloadError as e:
        logger.error(f"Download error: {e}")
        await msg.edit_text(f"❌ ডাউনলোড ব্যর্থ: {e}")
    except Exception as e:
        logger.exception("Unexpected error in handle_link")
        await msg.edit_text(f"❌ অজানা ত্রুটি: {e}")

    return ConversationHandler.END

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    data = query.data

    if data == 'use_extracted':
        await query.edit_message_text("⏳ সাবটাইটেল প্রস্তুত করা হচ্ছে...")
        await process_video(chat_id, context)
    elif data == 'upload_own':
        await query.edit_message_text("📂 অনুগ্রহ করে আপনার বাংলা সাবটাইটেল ফাইল আপলোড করুন।")
        return WAITING_SUBTITLE

async def handle_subtitle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    document = update.message.document

    if not document.file_name.endswith(('.srt', '.ass')):
        await update.message.reply_text("❌ শুধু .srt বা .ass ফাইল গ্রহণযোগ্য। আবার চেষ্টা করুন।")
        return WAITING_SUBTITLE

    file = await document.get_file()
    file_path = Path(gettempdir()) / f"sub_{chat_id}_{document.file_name}"
    await file.download_to_drive(file_path)

    if chat_id in user_sessions:
        user_sessions[chat_id]['subtitle_path'] = str(file_path)
    else:
        await update.message.reply_text("প্রথমে একটি ভিডিও লিংক দিন। /start")
        return ConversationHandler.END

    await update.message.reply_text("✅ সাবটাইটেল গৃহীত হয়েছে। ভিডিও প্রসেস করা শুরু হচ্ছে...")
    await process_video(chat_id, context)
    return ConversationHandler.END

async def process_video(chat_id, context: ContextTypes.DEFAULT_TYPE):
    session = user_sessions.get(chat_id)
    if not session:
        await context.bot.send_message(chat_id, "সেশন তথ্য পাওয়া যায়নি। আবার লিংক দিন।")
        return

    video_path = session['video_path']
    subtitle_path = session.get('subtitle_path')
    title = session.get('title', 'video')

    status_msg = await context.bot.send_message(chat_id, "⏳ ভিডিও প্রসেস করা হচ্ছে...")

    try:
        if subtitle_path:
            await status_msg.edit_text("🎨 সাবটাইটেল স্টাইল করা হচ্ছে...")
            styled_sub = await style_subtitle(subtitle_path, FONT_PATH)

            await status_msg.edit_text("🔥 ভিডিওতে সাবটাইটেল বসানো হচ্ছে...")
            output_path = await burn_subtitle(video_path, styled_sub)
        else:
            output_path = video_path
            await status_msg.edit_text("📤 ভিডিও আপলোডের জন্য প্রস্তুত (সাবটাইটেল ছাড়া)...")

        await status_msg.edit_text("📤 টেলিগ্রাম চ্যানেলে আপলোড করা হচ্ছে...")
        await upload_to_telegram(context.bot, CHANNEL_ID, output_path, caption=title)

        await context.bot.send_message(chat_id, f"✅ ভিডিও চ্যানেলে আপলোড সম্পন্ন: {CHANNEL_ID}")

    except BurnError as e:
        logger.error(f"Burn error: {e}")
        await context.bot.send_message(chat_id, f"❌ সাবটাইটেল বসাতে ব্যর্থ: {e}")
    except Exception as e:
        logger.exception("Error in process_video")
        await context.bot.send_message(chat_id, f"❌ প্রসেসিংয়ে ত্রুটি: {e}")
    finally:
        for path in [video_path, subtitle_path, 'styled_sub' in locals() and styled_sub, 'output_path' in locals() and output_path]:
            if path and os.path.exists(str(path)):
                os.remove(str(path))
        if chat_id in user_sessions:
            del user_sessions[chat_id]

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("প্রক্রিয়া বাতিল করা হয়েছে।")
    return ConversationHandler.END

# ================== মেইন ==================
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link)],
        states={
            WAITING_SUBTITLE: [MessageHandler(filters.Document.ALL, handle_subtitle_file)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(CommandHandler('start', start))

    logger.info("Bot started polling...")
    app.run_polling()

if __name__ == "__main__":
    main()
