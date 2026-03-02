FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    ffmpeg \
    fontconfig \
    && rm -rf /var/lib/apt/lists/* \
    && ffmpeg -version

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN fc-cache -fv

CMD ["gunicorn", "--worker-class", "eventlet", "-w", "1", "--bind", "0.0.0.0:5000", "app:app"]
