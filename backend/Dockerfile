FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# constraints.txt pins every package to the exact version the tests were run with (see its header)
COPY requirements.txt constraints.txt ./
RUN pip install -r requirements.txt -c constraints.txt

# Dev: source is bind-mounted by docker-compose, uvicorn reloads on change
FROM base AS dev
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# Prod
FROM base AS prod
COPY . .
RUN useradd --create-home appuser && chown -R appuser /app
USER appuser
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
