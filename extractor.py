import asyncio
from yt_dlp import YoutubeDL
from logger import setup_logger

logger = setup_logger(__name__)

class ExtractionError(Exception):
    pass

async def extract_info(url: str) -> dict:
    """
    yt-dlp ব্যবহার করে ভিডিও ও সাবটাইটেল তথ্য বের করে।
    রিয়েল-টাইম প্রগতি logger‑এ দেখায়।
    """
    def _sync_extract():
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'writesubtitles': True,
            'writeautomaticsub': True,
            'subtitleslangs': ['en', 'ko', 'ja', 'bn'],
            'skip_download': True,
            'logger': logger,
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

    # ভিডিও URL বের করা
    video_url = None
    if 'url' in info:
        video_url = info['url']
    elif 'formats' in info:
        # সেরা কোয়ালিটির mp4 খুঁজি, না পেলে প্রথম ভিডিও ফরম্যাট নিই
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

    # সাবটাইটেল URL সংগ্রহ
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