FROM python:3.12-slim

# Instalar ffmpeg para conversión MP3 → OGG/OPUS (respuestas de voz nativas en Telegram)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instalar dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código
COPY . .

CMD ["python", "bot.py"]
