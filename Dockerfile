FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PORT=10000
WORKDIR /app
RUN useradd --create-home --uid 10001 appuser

# Copy from scs-datastar-extension subfolder (where the actual code lives)
COPY scs-datastar-extension/pyproject.toml scs-datastar-extension/README.md ./
COPY scs-datastar-extension/app ./app
COPY scs-datastar-extension/extension ./extension

RUN pip install --upgrade pip && pip install .

USER appuser
EXPOSE 10000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
