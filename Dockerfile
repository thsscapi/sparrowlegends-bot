FROM python:3.12-slim
WORKDIR /app
ENV MPLBACKEND=Agg PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt && mkdir -p /data
COPY sparrowlegends.py .
COPY cwkpq-images/ ./cwkpq-images/
CMD ["python", "-u", "sparrowlegends.py", "--instance", "https://fluxer.com", "--database", "/data/sparrowlegends.sqlite3"]
