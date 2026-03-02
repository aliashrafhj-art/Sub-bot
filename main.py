import os
import asyncio
from pathlib import Path
from tempfile import gettempdir
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ConversationHandler, filters, ContextTypes
)
from config import BOT_TOKEN, CHANNEL_ID, FONT_PATH
from logger import setup_logger
from extractor import extract_info, ExtractionError
from downloader import download_video, download_subtitle, DownloadError
from subtitle import style_subtitle
from burner import burn_subtitle, BurnError
from uploader import upload_to_telegram

logger = setup_logger(__name__)

# কনভার্সন স্টেপ
WAITING_SUBTITLE = 1

# ইউজার সেশন ডেটা (Railway‑এ সিম্পল ইন-মেমরি, প্রোডাকশনে ডাটাবেস ভালো)
user_sessions = {}

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
        # ১. তথ্য এক্সট্র্যাক্ট
        info = await extract_info(url)
        await msg.edit_text("✅ ভিডিও তথ্য পাওয়া গেছে। ডাউনলোড শুরু...")

        # ২. ভিডিও ডাউনলোড (প্রগতি আপডেট সহ)
        async def progress(downloaded, total):
            percent = (downloaded / total) * 100
            await msg.edit_text(f"📥 ডাউনলোড: {percent:.1f}%")

        video_path = await download_video(info['video_url'], chat_id, progress)

        # ৩. সাবটাইটেল হ্যান্ডলিং
        subtitle_path = None
        if info['subtitles']:
            # প্রথম সাবটাইটেল ট্র্যাকটি নিই (ইংরেজি/কোরিয়ান/জাপানি)
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
            return  # কনভার্সেশন ক্যালব্যাকে চলে যাবে
        else:
            # কোনো সাবটাইটেল পাওয়া যায়নি
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

    # ফাইল ডাউনলোড
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
    """মূল প্রসেসিং চেইন"""
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
            # সাবটাইটেল স্টাইলাইজ
            await status_msg.edit_text("🎨 সাবটাইটেল স্টাইল করা হচ্ছে...")
            styled_sub = await style_subtitle(subtitle_path, FONT_PATH)

            # হার্ডসাব বার্ন
            await status_msg.edit_text("🔥 ভিডিওতে সাবটাইটেল বসানো হচ্ছে...")
            output_path = await burn_subtitle(video_path, styled_sub)
        else:
            # কোনো সাবটাইটেল নেই
            output_path = video_path
            await status_msg.edit_text("📤 ভিডিও আপলোডের জন্য প্রস্তুত (সাবটাইটেল ছাড়া)...")

        # টেলিগ্রামে আপলোড
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
        # ক্লিনআপ (টেম্প ফাইল ডিলিট)
        for path in [video_path, subtitle_path, styled_sub if 'styled_sub' in locals() else None, output_path if 'output_path' in locals() else None]:
            if path and os.path.exists(path):
                os.remove(path)
        if chat_id in user_sessions:
            del user_sessions[chat_id]

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("প্রক্রিয়া বাতিল করা হয়েছে।")
    return ConversationHandler.END

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