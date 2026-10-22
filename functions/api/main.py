import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import List

import pymysql
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import mfa
from auth import (bloqueado, crear_pase_mfa, crear_token, crear_token_recuperacion, hash_clave,
                  huella_coincide, leer_pase_mfa, leer_token_recuperacion, limpiar_fallos,
                  registrar_fallo, solo_admin, usuario_actual, verificar_clave)
from db import conexion, modo_bd
from modelos import (
    CambioClave, Confirmacion, Disponibilidad, DisponibilidadIn, EstadoMfa, Login, MfaCodigo,
    MfaMetodo, MfaPase, PasoMfa, Recuperar, Reglas, Restablecer, Reunion, ReunionIn, Sesion,
    Sugerencia, Usuario, UsuarioCambios, UsuarioIn,
)
from motor_cliente import disparar_motor

logging.basicConfig(level=logging.INFO)

_docs = os.environ.get("API_DOCS", "false").lower() == "true"
app = FastAPI(title="Motor de Horarios", version="0.4.0",
              docs_url="/docs" if _docs else None, redoc_url=None,
              openapi_url="/openapi.json" if _docs else None)

app.add_middleware(
    CORSMiddleware,
    # Tolera comillas, espacios y "/" final al pegar la variable
    allow_origins=[o.strip().strip("\"'").strip().rstrip("/")
                   for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(pymysql.err.OperationalError)
@app.exception_handler(pymysql.err.InterfaceError)
def base_no_disponible(_request: Request, error: Exception):
    """MySQL apagado o inalcanzable: 503 con marca de mantenimiento (el frontend
    muestra su pantalla de mantenimiento), no un 500 genérico."""
    logging.getLogger(__name__).warning("BD no disponible: %s", type(error).__name__)
    return JSONResponse(status_code=503, headers={"Retry-After": "300"},
                        content={"detail": "servicio en mantenimiento", "mantenimiento": True})


def _no_encontrado(que: str):
    raise HTTPException(status_code=404, detail=f"{que} no encontrado")


def _prohibido(motivo: str = "no tienes permiso para esta acción"):
    raise HTTPException(status_code=403, detail=motivo)


def _es_admin(u: dict) -> bool:
    return u["rol"] == "admin"


def _a_usuario(row: dict, visor: dict) -> Usuario:
    """El email solo lo ven los admins y la propia persona."""
    ver_email = _es_admin(visor) or row["id"] == visor["id"]
    return Usuario(id=row["id"], nombre=row["nombre"], rol=row["rol"], activo=bool(row["activo"]),
                   email=row["email"] if ver_email else None)


# ---------------------------------------------------------------- salud (público)

@app.get("/health")
def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/health/db")
def health_db():
    try:
        with conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1 AS ok")
            cur.fetchone()
        return {"status": "ok"}
    except KeyError as e:
        # Solo el nombre de la variable, nunca su valor
        raise HTTPException(status_code=503, detail=f"BD no disponible: falta la variable de entorno "
                                                    f"{e.args[0]} (DB_MODE recibido: {modo_bd()!r})")
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"BD no disponible: {type(e).__name__}")


# ---------------------------------------------------------------- sesión

@app.post("/auth/login", response_model=PasoMfa)
def login(datos: Login):
    email = datos.email.lower()
    if bloqueado(email):
        raise HTTPException(status_code=429, detail="demasiados intentos; espera 15 minutos")
    with conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, nombre, email, rol, activo, password_hash FROM usuarios "
                    "WHERE email = %s", (email,))
        u = cur.fetchone()
    if not u or not u["activo"] or not verificar_clave(datos.clave, u["password_hash"]):
        registrar_fallo(email)
        raise HTTPException(status_code=401, detail="correo o contraseña incorrectos")
    limpiar_fallos(email)
    # La contraseña sola no abre sesión: falta el segundo paso.
    return _paso_mfa(u["id"], enviar=True)


# ---------------------------------------------------------------- verificación en dos pasos

def _paso_mfa(usuario_id: int, enviar: bool = False) -> PasoMfa:
    u = mfa.cargar(usuario_id)
    metodo = mfa.preferido(u)
    if enviar and metodo == "correo":
        mfa.enviar_codigo(u)
    return PasoMfa(pase=crear_pase_mfa(u["id"]), configurado=mfa.configurado(u), metodo=metodo,
                   activos=mfa.metodos_activos(u), email=u["email"])


def _usuario_del_pase(pase: str | None) -> dict:
    usuario_id = leer_pase_mfa(pase)
    u = mfa.cargar(usuario_id) if usuario_id else None
    if not u or not u["activo"]:
        raise HTTPException(status_code=401, detail="el paso de verificación venció; vuelve a ingresar")
    return u


def _sesion(u: dict) -> Sesion:
    return Sesion(token=crear_token(u["id"]), usuario=_a_usuario(u, u))


def _iniciar_metodo(u: dict, metodo: str) -> dict:
    if metodo == "totp":
        return mfa.iniciar_totp(u)
    if not mfa.enviar_codigo(u):
        raise HTTPException(status_code=429, detail="pediste varios códigos seguidos; espera unos minutos")
    return {"enviado": True}


def _activar(u: dict, metodo: str, codigo: str) -> None:
    activado = mfa.activar_totp(u, codigo) if metodo == "totp" else mfa.activar_correo(u, codigo)
    if not activado:
        raise HTTPException(status_code=400, detail="el código no es correcto o ya venció")


@app.post("/auth/mfa/configurar")
def mfa_configurar(datos: MfaMetodo):
    """Primera vez: prepara el método elegido (QR de la app o código al correo)."""
    u = _usuario_del_pase(datos.pase)
    if mfa.configurado(u):
        raise HTTPException(status_code=409, detail="la verificación en dos pasos ya está configurada")
    return _iniciar_metodo(u, datos.metodo)


@app.post("/auth/mfa/activar", response_model=Sesion)
def mfa_activar(datos: MfaCodigo):
    u = _usuario_del_pase(datos.pase)
    if mfa.configurado(u):
        raise HTTPException(status_code=409, detail="la verificación en dos pasos ya está configurada")
    _activar(u, datos.metodo, datos.codigo)
    return _sesion(u)


@app.post("/auth/mfa/correo", status_code=202)
def mfa_reenviar(datos: MfaPase):
    u = _usuario_del_pase(datos.pase)
    if "correo" not in mfa.metodos_activos(u):
        raise HTTPException(status_code=400, detail="el código por correo no está activo en tu cuenta")
    if not mfa.enviar_codigo(u):
        raise HTTPException(status_code=429, detail="pediste varios códigos seguidos; espera unos minutos")
    return {"detail": f"te enviamos un código a {u['email']}"}


@app.post("/auth/mfa/verificar", response_model=Sesion)
def mfa_verificar(datos: MfaCodigo):
    u = _usuario_del_pase(datos.pase)
    if not mfa.verificar(u, datos.metodo, datos.codigo):
        raise HTTPException(status_code=401, detail="el código no es correcto o ya venció")
    return _sesion(u)


@app.get("/auth/mfa", response_model=EstadoMfa)
def mfa_estado(sesion: dict = Depends(usuario_actual)):
    u = mfa.cargar(sesion["id"])
    return EstadoMfa(activos=mfa.metodos_activos(u), preferido=mfa.preferido(u))


@app.post("/auth/mfa/agregar")
def mfa_agregar(datos: MfaMetodo, sesion: dict = Depends(usuario_actual)):
    """Desde el perfil: agrega el método que la cuenta todavía no tiene."""
    u = mfa.cargar(sesion["id"])
    if datos.metodo in mfa.metodos_activos(u):
        raise HTTPException(status_code=409, detail="ese método ya está activo")
    return _iniciar_metodo(u, datos.metodo)


@app.post("/auth/mfa/agregar/activar", response_model=EstadoMfa)
def mfa_agregar_activar(datos: MfaCodigo, sesion: dict = Depends(usuario_actual)):
    u = mfa.cargar(sesion["id"])
    _activar(u, datos.metodo, datos.codigo)
    return EstadoMfa(activos=mfa.metodos_activos(u), preferido=mfa.preferido(u))


@app.post("/auth/mfa/preferido", response_model=EstadoMfa)
def mfa_preferido(datos: MfaMetodo, sesion: dict = Depends(usuario_actual)):
    u = mfa.cargar(sesion["id"])
    if not mfa.elegir_preferido(u, datos.metodo):
        raise HTTPException(status_code=400, detail="ese método no está activo")
    return EstadoMfa(activos=mfa.metodos_activos(u), preferido=mfa.preferido(u))


@app.get("/auth/yo", response_model=Usuario)
def yo(u: dict = Depends(usuario_actual)):
    return _a_usuario(u, u)


@app.post("/auth/clave", status_code=204)
def cambiar_clave(datos: CambioClave, u: dict = Depends(usuario_actual)):
    with conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT password_hash FROM usuarios WHERE id = %s", (u["id"],))
        if not verificar_clave(datos.actual, cur.fetchone()["password_hash"]):
            raise HTTPException(status_code=400, detail="la contraseña actual no es correcta")
        cur.execute("UPDATE usuarios SET password_hash = %s WHERE id = %s",
                    (hash_clave(datos.nueva), u["id"]))
        conn.commit()


# ---------------------------------------------------------------- recuperación de cuenta

_RECUPERAR_ENVIOS: dict[str, list[float]] = {}
_RECUPERAR_LOCK = threading.Lock()


def _url_frontend() -> str:
    """Primera URL de CORS_ORIGINS (el frontend publicado), sin "/" final."""
    for origen in os.environ.get("CORS_ORIGINS", "").split(","):
        origen = origen.strip().strip("\"'").strip().rstrip("/")
        if origen.startswith("https://"):
            return origen
    return "http://localhost:5500"


def _correo_recuperacion(nombre: str, enlace: str):
    texto = (f"Hola {nombre},\n\nRecibimos una solicitud para restablecer la contraseña de tu cuenta "
             f"en Motor de Horarios. Crea una nueva aquí (el enlace vence en 30 minutos y sirve una vez):\n\n"
             f"{enlace}\n\nSi no fuiste tú, ignora este correo: tu contraseña no cambia.")
    html = (f"<p>Hola {nombre},</p><p>Recibimos una solicitud para restablecer la contraseña de tu "
            f"cuenta en <strong>Motor de Horarios</strong>.</p>"
            f'<p><a href="{enlace}" style="background:#00758F;color:#fff;padding:10px 18px;'
            f'border-radius:6px;text-decoration:none">Crear contraseña nueva</a></p>'
            f"<p>El enlace vence en 30 minutos y sirve una sola vez. Si no fuiste tú, ignora este "
            f"correo: tu contraseña no cambia.</p>")
    return texto, html


@app.post("/auth/recuperar", status_code=202)
def recuperar_cuenta(datos: Recuperar):
    """Envía el enlace para crear una contraseña nueva. Responde igual exista o no la cuenta
    (no revela qué correos están registrados) y comparte el freno a fuerza bruta del login."""
    email = datos.email.lower()
    respuesta = {"detail": "si el correo pertenece a una cuenta, te enviamos un enlace"}
    # Límite propio (no el del login): pedir enlaces no debe bloquear el ingreso de nadie.
    ahora = time.time()
    with _RECUPERAR_LOCK:
        recientes = [t for t in _RECUPERAR_ENVIOS.get(email, []) if ahora - t < 15 * 60]
        if len(recientes) >= 3:
            return respuesta
        _RECUPERAR_ENVIOS[email] = recientes + [ahora]
    with conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, nombre, email, activo, password_hash FROM usuarios WHERE email = %s",
                    (email,))
        u = cur.fetchone()
    if u and u["activo"]:
        enlace = f"{_url_frontend()}/restablecer#{crear_token_recuperacion(u['id'], u['password_hash'])}"
        try:
            from notificaciones import enviar_correos
            enviar_correos([(u["nombre"], u["email"])], "Restablece tu contraseña · Motor de Horarios",
                           lambda nombre: _correo_recuperacion(nombre, enlace))
        except Exception:  # el correo no debe revelar nada distinto al cliente
            logging.exception("No se pudo enviar el correo de recuperación")
    return respuesta


@app.post("/auth/restablecer", status_code=204)
def restablecer_clave(datos: Restablecer):
    leido = leer_token_recuperacion(datos.token)
    invalido = HTTPException(status_code=400, detail="el enlace no es válido o ya venció; pide uno nuevo")
    if not leido:
        raise invalido
    usuario_id, huella = leido
    with conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT email, activo, password_hash FROM usuarios WHERE id = %s", (usuario_id,))
        u = cur.fetchone()
        if not u or not u["activo"] or not huella_coincide(u["password_hash"], huella):
            raise invalido
        cur.execute("UPDATE usuarios SET password_hash = %s WHERE id = %s",
                    (hash_clave(datos.nueva), usuario_id))
        conn.commit()
    limpiar_fallos(u["email"])


# ---------------------------------------------------------------- personas

@app.get("/usuarios", response_model=List[Usuario])
def listar_usuarios(u: dict = Depends(usuario_actual)):
    with conexion() as conn, conn.cursor() as cur:
        filtro = "" if _es_admin(u) else "WHERE activo = TRUE "
        cur.execute(f"SELECT id, nombre, email, rol, activo FROM usuarios {filtro}ORDER BY nombre")
        return [_a_usuario(r, u) for r in cur.fetchall()]


def _insertar_usuario(nuevo: UsuarioIn) -> Usuario:
    """Crea una persona con rol 'usuario' y el horario laboral por defecto (8-18, L-V)."""
    nombre, email = nuevo.nombre.strip(), nuevo.email.lower()
    with conexion() as conn, conn.cursor() as cur:
        try:
            cur.execute("INSERT INTO usuarios (nombre, email, rol, password_hash) VALUES (%s, %s, 'usuario', %s)",
                        (nombre, email, hash_clave(nuevo.clave)))
            usuario_id = cur.lastrowid
            cur.execute("INSERT INTO reglas_usuario (usuario_id, no_antes_de, no_despues_de) "
                        "VALUES (%s, 8, 18)", (usuario_id,))
            conn.commit()
        except pymysql.err.IntegrityError:
            raise HTTPException(status_code=409, detail="ya existe una cuenta con ese correo")
    return Usuario(id=usuario_id, nombre=nombre, email=email, rol="usuario")


@app.post("/auth/registro", response_model=PasoMfa, status_code=201)
def registro(nuevo: UsuarioIn):
    """Registro público: las cuentas nuevas siempre son 'usuario'; los admins se asignan aparte.
    Antes de entrar, la cuenta elige su verificación en dos pasos."""
    u = _insertar_usuario(nuevo)
    return _paso_mfa(u.id)


@app.post("/usuarios", response_model=Usuario, status_code=201)
def crear_usuario(nuevo: UsuarioIn, admin: dict = Depends(solo_admin)):
    u = _insertar_usuario(nuevo)
    return _a_usuario(u.model_dump(), admin)


@app.patch("/usuarios/{usuario_id}", response_model=Usuario)
def editar_usuario(usuario_id: int, cambios: UsuarioCambios, admin: dict = Depends(solo_admin)):
    if usuario_id == admin["id"] and (cambios.rol == "usuario" or cambios.activo is False):
        raise HTTPException(status_code=400, detail="no puedes cambiar ni desactivar tu propia cuenta")
    campos, valores = [], []
    if cambios.nombre is not None:
        campos.append("nombre = %s"); valores.append(cambios.nombre.strip())
    if cambios.rol is not None:
        campos.append("rol = %s"); valores.append(cambios.rol)
    if cambios.activo is not None:
        campos.append("activo = %s"); valores.append(cambios.activo)
    if cambios.clave is not None:
        campos.append("password_hash = %s"); valores.append(hash_clave(cambios.clave))
    with conexion() as conn, conn.cursor() as cur:
        if campos:
            cur.execute(f"UPDATE usuarios SET {', '.join(campos)} WHERE id = %s", (*valores, usuario_id))
            conn.commit()
        cur.execute("SELECT id, nombre, email, rol, activo FROM usuarios WHERE id = %s", (usuario_id,))
        row = cur.fetchone()
        if not row:
            _no_encontrado("usuario")
        return _a_usuario(row, admin)


@app.delete("/usuarios/{usuario_id}", status_code=204)
def borrar_usuario(usuario_id: int, admin: dict = Depends(solo_admin)):
    if usuario_id == admin["id"]:
        raise HTTPException(status_code=400, detail="no puedes eliminar tu propia cuenta")
    with conexion() as conn, conn.cursor() as cur:
        try:
            cur.execute("DELETE FROM usuarios WHERE id = %s", (usuario_id,))
            conn.commit()
        except pymysql.err.IntegrityError:
            raise HTTPException(status_code=409,
                                detail="la persona organiza reuniones; desactívala en lugar de eliminarla")
        if cur.rowcount == 0:
            _no_encontrado("usuario")


def _existe_usuario(cur, usuario_id: int) -> bool:
    cur.execute("SELECT 1 FROM usuarios WHERE id = %s", (usuario_id,))
    return cur.fetchone() is not None


def _propio_o_admin(u: dict, usuario_id: int):
    if not _es_admin(u) and u["id"] != usuario_id:
        _prohibido("solo puedes gestionar tu propio calendario")


@app.get("/usuarios/{usuario_id}/reglas", response_model=Reglas)
def obtener_reglas(usuario_id: int, u: dict = Depends(usuario_actual)):
    _propio_o_admin(u, usuario_id)
    with conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT no_antes_de, no_despues_de, dias_laborables "
                    "FROM reglas_usuario WHERE usuario_id = %s", (usuario_id,))
        row = cur.fetchone()
        if not row:
            if not _existe_usuario(cur, usuario_id):
                _no_encontrado("usuario")
            return Reglas()
        row["dias_laborables"] = [int(d) for d in row["dias_laborables"].split(",") if d]
        return row


@app.put("/usuarios/{usuario_id}/reglas", response_model=Reglas)
def guardar_reglas(usuario_id: int, reglas: Reglas, u: dict = Depends(usuario_actual)):
    _propio_o_admin(u, usuario_id)
    with conexion() as conn, conn.cursor() as cur:
        if not _existe_usuario(cur, usuario_id):
            _no_encontrado("usuario")
        cur.execute(
            "INSERT INTO reglas_usuario (usuario_id, no_antes_de, no_despues_de, dias_laborables) "
            "VALUES (%s, %s, %s, %s) AS nuevo "
            "ON DUPLICATE KEY UPDATE no_antes_de = nuevo.no_antes_de, "
            "no_despues_de = nuevo.no_despues_de, dias_laborables = nuevo.dias_laborables",
            (usuario_id, reglas.no_antes_de, reglas.no_despues_de,
             ",".join(str(d) for d in reglas.dias_laborables)),
        )
        conn.commit()
    return reglas


@app.get("/usuarios/{usuario_id}/disponibilidad", response_model=List[Disponibilidad])
def listar_disponibilidad(usuario_id: int, u: dict = Depends(usuario_actual)):
    _propio_o_admin(u, usuario_id)
    with conexion() as conn, conn.cursor() as cur:
        if not _existe_usuario(cur, usuario_id):
            _no_encontrado("usuario")
        cur.execute(
            "SELECT id, usuario_id, inicio, fin, tipo, rrule, descripcion "
            "FROM disponibilidad WHERE usuario_id = %s ORDER BY inicio",
            (usuario_id,),
        )
        return cur.fetchall()


@app.post("/usuarios/{usuario_id}/disponibilidad", response_model=Disponibilidad, status_code=201)
def crear_disponibilidad(usuario_id: int, disp: DisponibilidadIn, u: dict = Depends(usuario_actual)):
    _propio_o_admin(u, usuario_id)
    if disp.rrule:
        _validar_rrule(disp.rrule, disp.inicio)
    with conexion() as conn, conn.cursor() as cur:
        if not _existe_usuario(cur, usuario_id):
            _no_encontrado("usuario")
        cur.execute(
            "INSERT INTO disponibilidad (usuario_id, inicio, fin, tipo, rrule, descripcion) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (usuario_id, disp.inicio, disp.fin, disp.tipo, disp.rrule, disp.descripcion),
        )
        conn.commit()
        return Disponibilidad(id=cur.lastrowid, usuario_id=usuario_id, **disp.model_dump())


@app.delete("/usuarios/{usuario_id}/disponibilidad/{disp_id}", status_code=204)
def borrar_disponibilidad(usuario_id: int, disp_id: int, u: dict = Depends(usuario_actual)):
    _propio_o_admin(u, usuario_id)
    with conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM disponibilidad WHERE id = %s AND usuario_id = %s",
                    (disp_id, usuario_id))
        conn.commit()
        if cur.rowcount == 0:
            _no_encontrado("bloque de disponibilidad")


def _validar_rrule(rrule: str, inicio: datetime):
    from dateutil.rrule import rrulestr
    try:
        rrulestr(rrule, dtstart=inicio)
    except (ValueError, TypeError) as e:
        raise HTTPException(status_code=422, detail=f"rrule inválida: {e}")


# ---------------------------------------------------------------- reuniones

def _cargar_reunion(cur, reunion_id: int, visor: dict) -> Reunion:
    cur.execute(
        "SELECT id, titulo, duracion_min, ventana_inicio, ventana_fin, organizador_id, "
        "estado, inicio_confirmado FROM reuniones WHERE id = %s",
        (reunion_id,),
    )
    row = cur.fetchone()
    if not row:
        _no_encontrado("reunión")
    cur.execute("SELECT usuario_id FROM reunion_participantes WHERE reunion_id = %s "
                "ORDER BY usuario_id", (reunion_id,))
    row["participantes"] = [r["usuario_id"] for r in cur.fetchall()]
    if not _es_admin(visor) and visor["id"] not in row["participantes"] + [row["organizador_id"]]:
        _no_encontrado("reunión")  # no se revela que existe
    cur.execute("SELECT id, inicio, fin, score FROM sugerencias WHERE reunion_id = %s "
                "ORDER BY score DESC, inicio", (reunion_id,))
    row["sugerencias"] = [Sugerencia(**r) for r in cur.fetchall()]
    return Reunion(**row)


def _puede_gestionar(r: Reunion, u: dict):
    if not _es_admin(u) and r.organizador_id != u["id"]:
        _prohibido("solo quien organiza la reunión puede modificarla")


@app.get("/reuniones", response_model=List[Reunion])
def listar_reuniones(u: dict = Depends(usuario_actual)):
    with conexion() as conn, conn.cursor() as cur:
        if _es_admin(u):
            cur.execute("SELECT id FROM reuniones WHERE estado <> 'cancelada' "
                        "ORDER BY ventana_inicio DESC LIMIT 100")
        else:
            cur.execute(
                "SELECT DISTINCT r.id, r.ventana_inicio FROM reuniones r "
                "LEFT JOIN reunion_participantes p ON p.reunion_id = r.id "
                "WHERE r.estado <> 'cancelada' AND (r.organizador_id = %s OR p.usuario_id = %s) "
                "ORDER BY r.ventana_inicio DESC LIMIT 100",
                (u["id"], u["id"]),
            )
        ids = [r["id"] for r in cur.fetchall()]
        return [_cargar_reunion(cur, i, u) for i in ids]


@app.get("/reuniones/{reunion_id}", response_model=Reunion)
def obtener_reunion(reunion_id: int, u: dict = Depends(usuario_actual)):
    with conexion() as conn, conn.cursor() as cur:
        return _cargar_reunion(cur, reunion_id, u)


@app.post("/reuniones", response_model=Reunion, status_code=201)
def crear_reunion(reunion: ReunionIn, u: dict = Depends(usuario_actual)):
    # Un usuario normal siempre organiza él mismo; un admin puede elegir organizador.
    organizador = reunion.organizador_id if _es_admin(u) and reunion.organizador_id else u["id"]
    participantes = sorted(set(reunion.participantes) | {organizador})
    with conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM usuarios WHERE activo = TRUE AND id IN %s",
                    (participantes,))
        if cur.fetchone()["n"] != len(participantes):
            raise HTTPException(status_code=422, detail="organizador o participantes inexistentes o inactivos")
        cur.execute(
            "INSERT INTO reuniones (titulo, duracion_min, ventana_inicio, ventana_fin, "
            "organizador_id) VALUES (%s, %s, %s, %s, %s)",
            (reunion.titulo, reunion.duracion_min, reunion.ventana_inicio,
             reunion.ventana_fin, organizador),
        )
        reunion_id = cur.lastrowid
        cur.executemany(
            "INSERT INTO reunion_participantes (reunion_id, usuario_id) VALUES (%s, %s)",
            [(reunion_id, p) for p in participantes],
        )
        conn.commit()

    disparar_motor(reunion_id)

    with conexion() as conn, conn.cursor() as cur:
        return _cargar_reunion(cur, reunion_id, u)


@app.post("/reuniones/{reunion_id}/recalcular", response_model=Reunion)
def recalcular(reunion_id: int, u: dict = Depends(usuario_actual)):
    with conexion() as conn, conn.cursor() as cur:
        r = _cargar_reunion(cur, reunion_id, u)
        _puede_gestionar(r, u)
        if r.estado in ("confirmada", "cancelada"):
            raise HTTPException(status_code=409, detail=f"la reunión está {r.estado}")
        cur.execute("UPDATE reuniones SET estado = 'pendiente' WHERE id = %s", (reunion_id,))
        conn.commit()
    if not disparar_motor(reunion_id):
        raise HTTPException(status_code=502, detail="no se pudo contactar al motor")
    with conexion() as conn, conn.cursor() as cur:
        return _cargar_reunion(cur, reunion_id, u)


@app.post("/reuniones/{reunion_id}/confirmar", response_model=Reunion)
def confirmar(reunion_id: int, conf: Confirmacion, u: dict = Depends(usuario_actual)):
    with conexion() as conn, conn.cursor() as cur:
        r = _cargar_reunion(cur, reunion_id, u)
        _puede_gestionar(r, u)
        if r.estado == "cancelada":
            raise HTTPException(status_code=409, detail="la reunión está cancelada")
        sug = next((s for s in r.sugerencias if s.id == conf.sugerencia_id), None)
        if not sug:
            _no_encontrado("sugerencia")
        cur.execute("UPDATE reuniones SET estado = 'confirmada', inicio_confirmado = %s "
                    "WHERE id = %s", (sug.inicio, reunion_id))
        conn.commit()
        return _cargar_reunion(cur, reunion_id, u)


@app.post("/reuniones/{reunion_id}/cancelar", response_model=Reunion)
def cancelar(reunion_id: int, u: dict = Depends(usuario_actual)):
    with conexion() as conn, conn.cursor() as cur:
        r = _cargar_reunion(cur, reunion_id, u)
        _puede_gestionar(r, u)
        cur.execute("UPDATE reuniones SET estado = 'cancelada' WHERE id = %s", (reunion_id,))
        conn.commit()
        return _cargar_reunion(cur, reunion_id, u)
