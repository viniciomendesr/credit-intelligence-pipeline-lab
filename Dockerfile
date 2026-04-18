FROM python:3.11-slim
WORKDIR /app

# Dependências primeiro — invalidado só quando requirements.txt muda
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Código e dados
COPY api/ ./api/
COPY src/ ./src/
COPY data/marts/ ./data/marts/

EXPOSE 8080
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
