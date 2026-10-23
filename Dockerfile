FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 FEFFEL_DATA_DIR=/data
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home feffel && mkdir /data && chown feffel:feffel /data
COPY --chown=feffel:feffel wsgi.py ./
COPY --chown=feffel:feffel feffel ./feffel
USER feffel
EXPOSE 8000
VOLUME ["/data"]
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "4", "--timeout", "180", "--access-logfile", "-", "--error-logfile", "-", "wsgi:application"]
