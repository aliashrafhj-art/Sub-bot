import os
import logging
import asyncio
import subprocess
import shutil
from pathlib import Path
from tempfile import gettempdir
from flask import Flask, render_template, request, jsonify, send_file, url_for
from flask_socketio import SocketIO, emit
import aiohttp
import aiofiles
from yt_dlp import YoutubeDL
import pysubs2
from werkzeug.utils import secure_filename
import time
import threading
import uuid

# ================== কনফিগারেশন ==================
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'
app.config['UPLOAD_FOLDER'] = 'downloads'
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024 * 1024  # 2GB
socketio = SocketIO(app, cors_allowed_origins="*")

# ফোল্ডার তৈরি
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# লগিং
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ================== ইউটিলিটি ফাংশন ==================
def clean_filename(filename):
    """ফাইল নাম পরিষ্কার করে"""
    return secure_filename(filename)

def get_temp_path(prefix, ext):
    """টেম্প ফাইল পাথ জেনারেট করে"""
    return Path(app.config['UPLOAD_FOLDER']) / f"{prefix}_{uuid.uuid4().hex[:8]}.{ext}"

# ================== ভিডিও এক্সট্র্যাক্টর ==================
async def extract_video_info(url):
    """yt-dlp দিয়ে ভিডিও তথ্য বের করে"""
    def sync_extract():
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'writesubtitles': True,
            'writeautomaticsub': True,
            'subtitleslangs': ['en', 'ko', 'ja', 'bn'],
            'skip_download': True,
        }
        with YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=False)

    loop = asyncio.get_event_loop()
    try:
        info = await loop.run_in_executor(None, sync_extract)
        
        # ভিডিও URL বের করা
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
        
        # সাবটাইটেল URL
        subtitles = {}
        if 'subtitles' in info:
            subtitles = info['subtitles']
        elif 'automatic_captions' in info:
            subtitles = info['automatic_captions']
        
        return {
            'success': True,
            'video_url': video_url,
            'subtitles': subtitles,
            'title': info.get('title', 'video'),
            'thumbnail': info.get('thumbnail', '')
        }
    except Exception as e:
        logger.exception("Extraction failed")
        return {'success': False, 'error': str(e)}

# ================== ডাউনলোডার ==================
async def download_video(url, task_id, referer=None):
    """ভিডিও ডাউনলোড করে"""
    output_path = get_temp_path(f"video_{task_id}", "mp4")
    
    if '.m3u8' in url:
        headers = {
            'Referer': referer or 'https://dramacool9.com.ro/',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        header_args = []
        for key, value in headers.items():
            header_args.extend(['-headers', f'{key}: {value}'])
        
        cmd = [
            'ffmpeg',
            '-i', url,
            *header_args,
            '-c', 'copy',
            '-bsf:a', 'aac_adtstoasc',
            '-y',
            str(output_path)
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        await process.communicate()
        
        if process.returncode != 0:
            raise Exception("FFmpeg download failed")
    else:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                resp.raise_for_status()
                total = int(resp.headers.get('content-length', 0))
                downloaded = 0
                async with aiofiles.open(output_path, 'wb') as f:
                    async for chunk in resp.content.iter_chunked(8192):
                        await f.write(chunk)
                        downloaded += len(chunk)
                        if total:
                            progress = (downloaded / total) * 100
                            socketio.emit('progress', {
                                'task_id': task_id,
                                'stage': 'download',
                                'progress': progress
                            })
    
    return str(output_path)

async def download_subtitle(url, task_id):
    """সাবটাইটেল ডাউনলোড করে"""
    output_path = get_temp_path(f"sub_{task_id}", "srt")
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            resp.raise_for_status()
            async with aiofiles.open(output_path, 'wb') as f:
                async for chunk in resp.content.iter_chunked(8192):
                    await f.write(chunk)
    return str(output_path)

# ================== সাবটাইটেল স্টাইলার ==================
async def style_subtitle(subtitle_path, task_id):
    """বাংলা সাবটাইটেল স্টাইল করে"""
    subs = pysubs2.load(subtitle_path, encoding="utf-8")
    
    style = pysubs2.SSAStyle()
    style.fontname = "fonts/NotoSansBengali-Regular.ttf"
    style.fontsize = 24
    style.primarycolor = pysubs2.Color(255, 255, 255, 0)
    style.outlinecolor = pysubs2.Color(0, 0, 0, 100)
    style.backcolor = pysubs2.Color(0, 0, 0, 80)
    style.bold = True
    style.outline = 2
    style.shadow = 1
    style.alignment = 2
    style.marginv = 30
    
    subs.styles["Netflix"] = style
    for line in subs.events:
        line.style = "Netflix"
    
    output_path = get_temp_path(f"styled_{task_id}", "ass")
    subs.save(output_path, format_="ass")
    return str(output_path)

# ================== সাবটাইটেল বার্নার ==================
async def burn_subtitle(video_path, subtitle_path, task_id):
    """ভিডিওতে সাবটাইটেল বার্ন করে"""
    output_path = get_temp_path(f"final_{task_id}", "mp4")
    
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
    
    process = await asyncio.create_subprocess_exec(
        *cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    await process.communicate()
    
    if process.returncode != 0:
        raise Exception("Burning failed")
    
    return str(output_path)

# ================== টেলিগ্রাম আপলোডার ==================
async def upload_to_telegram(file_path, caption, bot_token, channel_id):
    """টেলিগ্রাম চ্যানেলে আপলোড করে"""
    import httpx
    
    url = f"https://api.telegram.org/bot{bot_token}/sendVideo"
    
    async with httpx.AsyncClient(timeout=300.0) as client:
        with open(file_path, 'rb') as f:
            files = {'video': f}
            data = {'chat_id': channel_id, 'caption': caption}
            response = await client.post(url, data=data, files=files)
            return response.json()

# ================== টাস্ক প্রসেসর ==================
async def process_video_task(url, task_id, bot_token=None, channel_id=None):
    """পুরো ভিডিও প্রসেসিং পাইপলাইন"""
    try:
        socketio.emit('status', {'task_id': task_id, 'message': 'ভিডিও তথ্য সংগ্রহ করা হচ্ছে...'})
        
        # ১. ভিডিও তথ্য এক্সট্র্যাক্ট
        info = await extract_video_info(url)
        if not info['success']:
            socketio.emit('error', {'task_id': task_id, 'error': info['error']})
            return
        
        # ২. ভিডিও ডাউনলোড
        socketio.emit('status', {'task_id': task_id, 'message': 'ভিডিও ডাউনলোড হচ্ছে...'})
        video_path = await download_video(info['video_url'], task_id)
        
        subtitle_path = None
        if info['subtitles']:
            # ৩. সাবটাইটেল ডাউনলোড
            lang = list(info['subtitles'].keys())[0]
            sub_url = info['subtitles'][lang][0]['url']
            subtitle_path = await download_subtitle(sub_url, task_id)
            
            socketio.emit('status', {'task_id': task_id, 'message': 'সাবটাইটেল স্টাইল করা হচ্ছে...'})
            
            # ৪. সাবটাইটেল স্টাইল
            styled_sub = await style_subtitle(subtitle_path, task_id)
            
            socketio.emit('status', {'task_id': task_id, 'message': 'ভিডিওতে সাবটাইটেল বসানো হচ্ছে...'})
            
            # ৫. সাবটাইটেল বার্ন
            final_path = await burn_subtitle(video_path, styled_sub, task_id)
        else:
            final_path = video_path
        
        # ৬. প্রিভিউ URL
        preview_url = url_for('download_file', filename=Path(final_path).name, _external=True)
        socketio.emit('preview', {
            'task_id': task_id,
            'video_url': preview_url,
            'title': info['title'],
            'thumbnail': info.get('thumbnail', '')
        })
        
        # ৭. টেলিগ্রাম আপলোড (যদি টোকেন দেওয়া থাকে)
        if bot_token and channel_id:
            socketio.emit('status', {'task_id': task_id, 'message': 'টেলিগ্রামে আপলোড হচ্ছে...'})
            await upload_to_telegram(final_path, info['title'], bot_token, channel_id)
            socketio.emit('done', {'task_id': task_id, 'message': 'টেলিগ্রামে আপলোড সম্পন্ন!'})
        
    except Exception as e:
        logger.exception("Processing failed")
        socketio.emit('error', {'task_id': task_id, 'error': str(e)})

# ================== ফ্লাস্ক রুট ==================
@app.route('/')
def index():
    """হোম পেজ"""
    return render_template('index.html')

@app.route('/process', methods=['POST'])
def process():
    """ভিডিও প্রসেসিং শুরু করে"""
    url = request.json.get('url')
    bot_token = request.json.get('bot_token')
    channel_id = request.json.get('channel_id')
    
    if not url:
        return jsonify({'error': 'URL is required'}), 400
    
    task_id = uuid.uuid4().hex[:8]
    
    # ব্যাকগ্রাউন্ড টাস্ক শুরু
    threading.Thread(
        target=lambda: asyncio.run(process_video_task(url, task_id, bot_token, channel_id))
    ).start()
    
    return jsonify({'task_id': task_id})

@app.route('/download/<filename>')
def download_file(filename):
    """ডাউনলোড ফাইল"""
    return send_file(
        Path(app.config['UPLOAD_FOLDER']) / filename,
        as_attachment=True,
        download_name=filename
    )

@app.route('/cleanup', methods=['POST'])
def cleanup():
    """পুরোনো ফাইল মুছে ফেলে"""
    task_id = request.json.get('task_id')
    if task_id:
        for f in Path(app.config['UPLOAD_FOLDER']).glob(f'*_{task_id}*'):
            f.unlink()
    return jsonify({'success': True})

# ================== মেইন ==================
if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=True)
