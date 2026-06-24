FROM python:3.12-slim

WORKDIR /app

# System deps for OpenCV
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx libglib2.0-0 libsm6 libxext6 libxrender-dev \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements-snapshot.txt .
RUN pip install --no-cache-dir -r requirements-snapshot.txt

# App code
COPY app.py config.py db.py startup_check.py analytics.py health.py .
COPY snapshot_counter.py .
COPY templates/ templates/
COPY snapshot_data/ snapshot_data/

ENV CAMERA_SOURCE=""
ENV CAMERA_MODE="rtsp"
ENV SNAPSHOT_INTERVAL_S="300"
ENV FLASK_PORT="5000"

EXPOSE 5000

CMD ["python", "app.py"]
