FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PORT=10000
WORKDIR /app
RUN useradd --create-home --uid 10001 appuser
COPY scs-datastar-extension/ ./
RUN pip install --upgrade pip && pip install . --no-cache-dir
USER appuser
EXPOSE 10000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]