# Usa Python 3.11 oficial
FROM python:3.11-slim

# Directorio de trabajo
WORKDIR /app

# Instalar dependencias del sistema necesarias para compilar greenlet/eventlet
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copiar e instalar dependencias de Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto del código
COPY . .

# Puerto que usa Render
ENV PORT=10000
EXPOSE $PORT

# Comando de inicio (usa wsgi.py con monkey patch)
CMD ["gunicorn", "--worker-class", "eventlet", "-w", "1", "wsgi:app"]