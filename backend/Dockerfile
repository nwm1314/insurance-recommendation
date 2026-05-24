FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir playwright && playwright install --with-deps chromium
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
