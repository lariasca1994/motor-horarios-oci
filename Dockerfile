# Backend en Render: API (FastAPI) + motor en el mismo proceso (MOTOR_MODE=inproceso).
FROM python:3.12-slim-bookworm
WORKDIR /app
COPY functions/api/requirements.txt requirements-api.txt
COPY functions/motor/requirements.txt requirements-motor.txt
RUN pip install --no-cache-dir -r requirements-api.txt -r requirements-motor.txt
COPY functions/api/*.py ./
COPY functions/motor/motor.py functions/motor/recurrencia.py functions/motor/notificaciones.py functions/motor/procesamiento.py ./
RUN useradd --system --uid 10001 app && chown -R app /app
USER app
ENV PYTHONUNBUFFERED=1 PORT=8000 MOTOR_MODE=inproceso
EXPOSE 8000
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
