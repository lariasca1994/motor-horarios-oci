# Motor de Horarios sobre OCI

Coordina reuniones entre varias personas: cada usuario registra sus bloques
ocupados/preferidos (con recurrencia RRULE) y sus reglas (horario y días
laborables); el motor propone los 3 mejores huecos comunes y avisa por
correo (SMTP) a cada persona seleccionada.

## Arquitectura (producción)

```
Vercel (frontend estático, HTTPS)
   │  fetch + token
   ▼
Render (Docker, plan free): API FastAPI + motor en el mismo proceso
   │  MySQL sobre TLS con certificado fijado            │ API HTTP
   ▼                                                    ▼
OCI Network Load Balancer (IP pública, 3306 solo para IPs permitidas)   Brevo (correos)
   ▼
MySQL HeatWave Free (subred privada de OCI)
```

| Carpeta | Contenido |
|---|---|
| `functions/api` | API REST (FastAPI), autenticación y permisos. |
| `functions/motor` | Cálculo de huecos (`motor.py`), RRULE, `procesamiento.py`, correos. |
| `frontend` | HTML/CSS/JS estático (Vercel). La URL de la API está en `js/config.js`. |
| `db` | `001_esquema.sql` (tablas) y `002_datos_demo.sql` (solo desarrollo). |
| `deploy` | Scripts de OCI (red, MySQL, Vault, NLB). |

Render gratis se suspende tras 15 min sin tráfico: la primera petición tarda ~50 s.
Las fechas se guardan sin zona horaria y se interpretan como hora de Bogotá.

## Acceso y roles

Todo requiere iniciar sesión (salvo `/health`). Contraseñas con scrypt; sesión con
token firmado (HMAC-SHA256, 12 h) que el frontend guarda en `sessionStorage`.

| | Administrador | Usuario |
|---|---|---|
| Personas | crea, desactiva, elimina; ve correos | solo nombres (para elegir participantes) |
| Reuniones | ve y gestiona todas; elige organizador | ve aquellas en que organiza o participa; organiza él mismo |
| Confirmar / recalcular / cancelar | todas | solo las que organiza |
| Disponibilidad y reglas | de cualquiera | solo las propias |

Las cuentas iniciales se leen de `deploy/.usuarios_iniciales` (`email|clave|rol|nombre`,
no se sube a git) y se crean en cada despliegue con `local/crear_usuarios.py`, sin
sobrescribir contraseñas que ya se hayan cambiado. Cada persona recibe por correo
(SMTP, Brevo) las sugerencias de las reuniones en que participa.

## Desarrollo local (sin Docker)

Requisitos: Python 3.12+ y un MySQL 8 local (aquí: servicio `MySQL84`, puerto 3306).

```powershell
python -m venv .venv
.venv\Scripts\pip install -r functions\api\requirements.txt -r functions\motor\requirements.txt
.venv\Scripts\python local\crear_bd.py          # pide la clave de root; crea BD, usuario y local\.env
powershell -ExecutionPolicy Bypass -File local\iniciar.ps1
```

| Servicio | URL |
|---|---|
| Frontend | http://localhost:8080 |
| API (Swagger) | http://localhost:8000/docs |
| Motor | http://localhost:8001/health |

Para recrear la base: `.venv\Scripts\python local\crear_bd.py --reset`.
`docker-compose.yml` queda como alternativa para equipos con Docker.

## Variables de entorno

| Variable | Función | Valor |
|---|---|---|
| `DB_MODE` | ambas | `env` (local) o `vault` (OCI, por defecto) |
| `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME` | ambas | solo con `DB_MODE=env` |
| `DB_SSL_CA` / `DB_SSL_CA_PEM` | ambas | ruta o contenido del certificado (CA o certificado fijado) |
| `DB_SSL_CHECK_HOSTNAME` | ambas | `false` al conectarse por IP (NLB) |
| `DB_SECRET_OCID` | ambas | OCID del secreto JSON en Vault (`host`, `port`, `user`, `password`, `database`, `ssl_ca` opcional) |
| `MOTOR_MODE` | api | `inproceso` (Render), `http` (local), `oci` (Functions) u `off` |
| `MOTOR_URL` | api | URL del motor local |
| `MOTOR_FUNCTION_OCID`, `MOTOR_INVOKE_ENDPOINT` | api | para invocar el motor en OCI |
| `API_PATH_PREFIX` | api | prefijo del deployment de API Gateway, p. ej. `/horarios` |
| `CORS_ORIGINS` | api | orígenes permitidos separados por coma (`*` por defecto) |
| `AUTH_SECRET` | api | clave para firmar sesiones (obligatoria en producción) |
| `AUTH_TTL_HORAS` | api | duración de la sesión (12 por defecto) |
| `EMAIL_MODE` | motor | `log` (por defecto), `brevo_api` o `smtp` |
| `BREVO_API_KEY`, `EMAIL_FROM`, `EMAIL_FROM_NAME` | motor | envío por la API de Brevo |
| `SMTP_SECRET_OCID` | motor | secreto JSON en Vault con `host`, `port`, `user`, `password`, `from` |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `EMAIL_FROM` | motor | SMTP sin Vault (local) |

## Infraestructura OCI (cuenta Free Tier, región sa-bogota-1)

La cuenta Free Tier no permite Functions, API Gateway ni Service/NAT Gateway, así
que el despliegue real usa una VM Always Free con el mismo código:

```
Navegador ──► VM Ampere A1 (Ubuntu 24.04, subred pública 10.0.20.0/24)
                nginx: /  → frontend estático
                       /api/ → uvicorn (functions/api)  ──► motor (local_server.py)
                                   │                            │
                                   └──── MySQL HeatWave Free (subred privada 10.0.21.0/24)
              Vault (credenciales BD y SMTP) vía instance principal; correos por SMTP (Brevo)
```

Scripts en `deploy/` (bash, OCI CLI). Los OCID quedan en `deploy/estado.env`;
la clave del admin de MySQL en `deploy/.secretos` (no se sube a git).

| Script | Crea |
|---|---|
| `01_red.sh` | Subredes, rutas y reglas dentro de `PRPagos-vnc` (límite de 2 VCN) |
| `02_mysql.sh` | MySQL HeatWave `MySQL.Free` |
| `03_iam_vault.sh` | Dynamic group + política, Vault + llave |
| `04_vm.sh` | VM A1 con reintentos por falta de capacidad; llave SSH en `~/.ssh/motor_horarios_oci` |
| `05_desplegar.sh` | Sube el código, crea BD y secreto (primera vez) y reinicia servicios. Reejecutar para desplegar cambios |
| `06_nlb_mysql.sh` | NLB Always Free que publica MySQL (3306) solo para `PERMITIR_IPS` (tu IP + IPs de salida de Render) |

La arquitectura con OCI Functions + API Gateway (`functions/*/func.py`, `Dockerfile`,
`func.yaml`) queda lista para cuando la cuenta pase a Pay As You Go.

`Dockerfile` y `render.yaml` de la raíz son opcionales (API en Render, sin motor).
