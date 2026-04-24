FROM python:3.12-slim

# Paquets nécessaires pour pypsrp (Kerberos/GSSAPI optionnel, NTLM fallback natif)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libkrb5-3 \
        libgssapi-krb5-2 \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Dossier data persisté par volume
RUN mkdir -p /data

ENV PYTHONUNBUFFERED=1
ENV GALINETTE_DATA_DIR=/data

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
