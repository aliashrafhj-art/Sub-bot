import asyncio
import subprocess
from pathlib import Path
from tempfile import gettempdir
from logger import setup_logger

logger = setup_logger(__name__)

class BurnError(Exception):
    pass

async def burn_subtitle(video_path: str, subtitle_path: str) -> str:
    """FFmpeg ব্যবহার করে ভিডিওতে সাবটাইটেল বার্ন করে"""
    output_path = Path(gettempdir()) / f"output_{Path(video_path).stem}_sub.mp4"

    # সাবটাইটেল টাইপ অনুযায়ী ফিল্টার
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