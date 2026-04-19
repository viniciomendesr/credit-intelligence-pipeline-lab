FROM python:3.11-slim
WORKDIR /app

# Dependências primeiro — invalidado só quando requirements.txt muda
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Código — o parquet é baixado do GCS no startup pela api/main.py
COPY api/ ./api/
COPY src/ ./src/

EXPOSE 8080
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
