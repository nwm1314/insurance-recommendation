# Pin the Debian release used by Playwright's dependency installer.  The
# floating slim tag moved to Debian trixie, where the installer still asks
# for packages removed from the repository (ttf-unifont and
# ttf-ubuntu-font-family), making production builds fail before the app is
# copied into the image.
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /srv

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt \
    && playwright install --with-deps chromium

COPY backend backend

WORKDIR /srv/backend

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
