FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 APP_ENV=production COOKIE_SECURE=true
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --create-home appuser
COPY . .
RUN mkdir -p /data && chown -R appuser:appuser /app /data
ENV DATABASE_PATH=/data/store.db UPLOAD_FOLDER=/data/uploads
USER appuser
EXPOSE 8000
CMD ["gunicorn","--workers","1","--bind","0.0.0.0:8000","wsgi:app"]
