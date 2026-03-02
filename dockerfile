FROM python:3.11-slim

RUN apt-get update && apt-get install -y ffmpeg fontconfig && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# ফন্ট ক্যাশ আপডেট
RUN fc-cache -fv

CMD ["python", "main.py"]