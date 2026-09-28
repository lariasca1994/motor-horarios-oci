import logging
import os
from datetime import datetime, timezone
from typing import List

import pymysql
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from auth import (bloqueado, crear_token, hash_clave, limpiar_fallos, registrar_fallo,
                  solo_admin, usuario_actual, verificar_clave)
from db import conexion, modo_bd
from modelos import (
    CambioClave, Confirmacion, Disponibilidad, DisponibilidadIn, Login, Reglas, Reunion,
    ReunionIn, Sesion, Sugerencia, Usuario, UsuarioCambios, UsuarioIn,
)
from motor_cliente import disparar_motor

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Motor de Horarios", version="0.3.0")

app.add_middleware(
    CORSMiddleware,
    # Tolera comillas, espacios y "/" final al pegar la variable
    allow_origins=[o.strip().strip("\"'").strip().rstrip("/")
                   for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)


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

@app.post("/auth/login", response_model=Sesion)
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
    return Sesion(token=crear_token(u["id"]), usuario=_a_usuario(u, u))


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


# ---------------------------------------------------------------- personas

@app.get("/usuarios", response_model=List[Usuario])
def listar_usuarios(u: dict = Depends(usuario_actual)):
    with conexion() as conn, conn.cursor() as cur:
        filtro = "" if _es_admin(u) else "WHERE activo = TRUE "
        cur.execute(f"SELECT id, nombre, email, rol, activo FROM usuarios {filtro}ORDER BY nombre")
        return [_a_usuario(r, u) for r in cur.fetchall()]


@app.post("/usuarios", response_model=Usuario, status_code=201)
def crear_usuario(nuevo: UsuarioIn, admin: dict = Depends(solo_admin)):
    with conexion() as conn, conn.cursor() as cur:
        try:
            cur.execute("INSERT INTO usuarios (nombre, email, rol, password_hash) VALUES (%s, %s, %s, %s)",
                        (nuevo.nombre.strip(), nuevo.email.lower(), nuevo.rol, hash_clave(nuevo.clave)))
            usuario_id = cur.lastrowid
            cur.execute("INSERT INTO reglas_usuario (usuario_id) VALUES (%s)", (usuario_id,))
            conn.commit()
        except pymysql.err.IntegrityError:
            raise HTTPException(status_code=409, detail="ya existe una persona con ese correo")
    return Usuario(id=usuario_id, nombre=nuevo.nombre.strip(), email=nuevo.email.lower(), rol=nuevo.rol)


@app.patch("/usuarios/{usuario_id}", response_model=Usuario)
def editar_usuario(usuario_id: int, cambios: UsuarioCambios, admin: dict = Depends(solo_admin)):
    if usuario_id == admin["id"] and (cambios.rol == "usuario" or cambios.activo is False):
        raise HTTPException(status_code=400, detail="no puedes quitarte el rol de admin ni desactivarte")
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
        _prohibido("solo el organizador o un admin puede modificar la reunión")


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
    organizador = reunion.organizador_id if _es_admin(u) else u["id"]
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
