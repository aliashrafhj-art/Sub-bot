FROM python:3.11-slim

# Apt packages install
RUN apt-get update && apt-get install -y ffmpeg fontconfig && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Requirements কপি ও ইন্সটল
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# সব ফাইল কপি
COPY . .

# ফন্ট ক্যাশ আপডেট
RUN fc-cache -fv

# Start command (ঐচ্ছিক, কারণ railway.json-এ দেয়া আছে)
# CMD ["python", "main.py"]
