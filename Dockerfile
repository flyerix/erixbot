FROM python:3.12.9-slim-bookworm

WORKDIR /app

# Installa dipendenze di sistema per psycopg2 e altre librerie
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    python3-dev \
    build-essential \
    libpq-dev \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copia e installa requirements
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Copia tutto il codice
COPY . .

# Crea directory backup
RUN mkdir -p backups

CMD ["python", "bot.py"]
