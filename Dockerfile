FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY strategy.toml .
RUN useradd --create-home signaldesk && mkdir /data && chown signaldesk /data
USER signaldesk
ENV DATA_DIR=/data DB_PATH=/data/signal_desk.db HOST=0.0.0.0 PORT=8000
VOLUME /data
EXPOSE 8000
HEALTHCHECK --interval=60s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4)"
CMD ["python", "-m", "app"]
