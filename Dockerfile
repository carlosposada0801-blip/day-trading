FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY strategy.toml .
ENV DATA_DIR=/data DB_PATH=/data/signal_desk.db HOST=0.0.0.0 PORT=8000
VOLUME /data
EXPOSE 8000
CMD ["python", "-m", "app"]
