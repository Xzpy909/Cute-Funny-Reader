FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LIBRARY_DIR=/data \
    CONFIG_DIR=/config \
    SCAN_INTERVAL=600

WORKDIR /app
# unar unpacks .cbr (RAR) uploads, which are converted to .cbz · ffmpeg grabs cover frames for video sets
RUN apt-get update && apt-get install -y --no-install-recommends unar ffmpeg && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app

VOLUME ["/config"]
EXPOSE 9001
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:9001/api/auth/state', timeout=4)" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9001", "--proxy-headers", "--forwarded-allow-ips", "*"]
