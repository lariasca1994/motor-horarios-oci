# Imagen para OCI Functions (fn build / fn deploy). Para desarrollo local ver Dockerfile.local
FROM python:3.12.15-slim-bookworm
# Almacén de certificados del sistema sin las raíces que firmaron los intermedios
# comprometidos de eMudhra (octubre 2026): emSign y Comodo "AAA Certificate Services".
RUN if command -v update-ca-certificates > /dev/null; then \
        rm -f /usr/share/ca-certificates/mozilla/emSign_* /usr/share/ca-certificates/mozilla/Comodo_AAA_Services_root.crt \
        && update-ca-certificates --fresh > /dev/null 2>&1; \
    fi
WORKDIR /function
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY *.py ./
ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["/usr/local/bin/fdk", "/function/func.py", "handler"]
