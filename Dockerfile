FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

COPY app.py README.md TODO.md ./
COPY static ./static

EXPOSE 8080

CMD ["python3", "app.py"]
