FROM python:3.11-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 DOCURISK_DATA_DIR=/app/data
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN pip install --no-cache-dir '.[docling]'
RUN mkdir -p /app/data && chown -R 10001:10001 /app/data
USER 10001
EXPOSE 8000
CMD ["uvicorn", "docurisk.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
