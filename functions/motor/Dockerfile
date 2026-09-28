# Imagen para OCI Functions (fn build / fn deploy). Para desarrollo local ver Dockerfile.local
FROM python:3.12-slim-bookworm
WORKDIR /function
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY *.py ./
ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["/usr/local/bin/fdk", "/function/func.py", "handler"]
