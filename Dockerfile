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
# Valores no secretos por defecto (una variable en Render con el mismo nombre los reemplaza).
# En Render solo hacen falta los secretos: DB_HOST, DB_USER, DB_PASSWORD, DB_SSL_CA_PEM,
# AUTH_SECRET, BREVO_API_KEY y EMAIL_FROM.
ENV PYTHONUNBUFFERED=1 PORT=8000     MOTOR_MODE=inproceso     DB_MODE=env DB_PORT=3306 DB_NAME=motor_horarios DB_SSL_CHECK_HOSTNAME=false     EMAIL_MODE=brevo_api EMAIL_FROM_NAME="Reservas Corferias"     CORS_ORIGINS=https://motor-horarios-oci.vercel.app
EXPOSE 8000
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
