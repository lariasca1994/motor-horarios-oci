const API = (window.APP_CONFIG?.API_URL || "").replace(/\/$/, "");

const $ = (sel) => document.querySelector(sel);
let usuarios = [];
let yo = null;

// ---------------------------------------------------------------- sesión

const sesion = {
    get token() {
        try { return sessionStorage.getItem("token"); } catch { return null; }
    },
    set token(v) {
        try { v ? sessionStorage.setItem("token", v) : sessionStorage.removeItem("token"); } catch { /* sin storage */ }
    },
};
let tokenMemoria = null; // respaldo si el navegador bloquea sessionStorage
const obtenerToken = () => sesion.token || tokenMemoria;

function esc(valor) {
    const div = document.createElement("div");
    div.textContent = valor ?? "";
    return div.innerHTML;
}

async function api(ruta, opciones = {}) {
    const headers = { "Content-Type": "application/json" };
    const token = obtenerToken();
    if (token) headers.Authorization = `Bearer ${token}`;
    const res = await fetch(`${API}${ruta}`, { ...opciones, headers });
    const datos = res.status === 204 ? null : await res.json().catch(() => null);
    if (res.status === 401 && ruta !== "/auth/login" && ruta !== "/auth/clave") {
        cerrarSesion("Tu sesión venció, ingresa de nuevo.");
        throw new Error("sesión vencida");
    }
    if (!res.ok) {
        const detalle = Array.isArray(datos?.detail)
            ? datos.detail.map((d) => d.msg).join("; ")
            : datos?.detail;
        throw new Error(detalle || `Error ${res.status}`);
    }
    return datos;
}

function mostrarMensaje(texto, tipo, selector) {
    const msg = $(selector);
    msg.textContent = texto;
    msg.className = `mensaje ${tipo}`;
    msg.hidden = false;
}

function mostrarVista(vista) {
    $("#vista-login").hidden = vista !== "login";
    $("#vista-clave").hidden = vista !== "clave";
    $("#vista-app").hidden = vista !== "app";
    $("#sesion").hidden = vista === "login";
}

function cerrarSesion(mensaje) {
    sesion.token = null;
    tokenMemoria = null;
    yo = null;
    mostrarVista("login");
    $("#msg-login").hidden = true;
    if (mensaje) mostrarMensaje(mensaje, "error", "#msg-login");
}

async function entrar(usuario) {
    yo = usuario;
    const esAdmin = yo.rol === "admin";
    $("#sesion-nombre").textContent = yo.nombre;
    $("#sesion-rol").textContent = esAdmin ? "Administrador" : "Usuario";
    $("#personas").hidden = !esAdmin;
    $("#campo-organizador").hidden = !esAdmin;
    $("#titulo-reuniones").textContent = esAdmin ? "Todas las reuniones" : "Mis reuniones";
    mostrarVista("app");
    valoresPorDefecto();
    await cargarUsuarios();
    await cargarReuniones();
}

$("#form-login").addEventListener("submit", async (e) => {
    e.preventDefault();
    const form = new FormData(e.target);
    const boton = e.target.querySelector("button");
    boton.disabled = true;
    try {
        const s = await api("/auth/login", {
            method: "POST",
            body: JSON.stringify({ email: form.get("email").trim(), clave: form.get("clave") }),
        });
        sesion.token = s.token;
        tokenMemoria = s.token;
        e.target.reset();
        $("#msg-login").hidden = true;
        await entrar(s.usuario);
    } catch (err) {
        mostrarMensaje(err.message, "error", "#msg-login");
    } finally {
        boton.disabled = false;
    }
});

$("#btn-salir").addEventListener("click", () => cerrarSesion());
$("#btn-clave").addEventListener("click", () => { $("#msg-clave").hidden = true; mostrarVista("clave"); });
$("#btn-clave-cancelar").addEventListener("click", () => mostrarVista("app"));

$("#form-clave").addEventListener("submit", async (e) => {
    e.preventDefault();
    const form = new FormData(e.target);
    try {
        await api("/auth/clave", {
            method: "POST",
            body: JSON.stringify({ actual: form.get("actual"), nueva: form.get("nueva") }),
        });
        e.target.reset();
        mostrarMensaje("Contraseña actualizada", "ok", "#msg-clave");
    } catch (err) {
        mostrarMensaje(err.message, "error", "#msg-clave");
    }
});

// ---------------------------------------------------------------- formato

const fmt = new Intl.DateTimeFormat("es-CO", {
    weekday: "short", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit",
});
const fmtHora = new Intl.DateTimeFormat("es-CO", { hour: "2-digit", minute: "2-digit" });
const fecha = (iso) => fmt.format(new Date(iso));
const hora = (iso) => fmtHora.format(new Date(iso));
const nombre = (id) => usuarios.find((u) => u.id === id)?.nombre ?? `#${id}`;

const ETIQUETAS = {
    pendiente: "Calculando",
    con_sugerencias: "Con sugerencias",
    sin_huecos: "Sin huecos",
    confirmada: "Confirmada",
    cancelada: "Cancelada",
};

// ---------------------------------------------------------------- personas

async function cargarUsuarios() {
    usuarios = await api("/usuarios");
    const activos = usuarios.filter((u) => u.activo);

    $("#sel-organizador").innerHTML = activos
        .map((u) => `<option value="${u.id}" ${u.id === yo.id ? "selected" : ""}>${esc(u.nombre)}</option>`)
        .join("");
    $("#lista-participantes").innerHTML = activos
        .filter((u) => u.id !== yo.id || yo.rol === "admin")
        .map((u) => `<label class="check"><input type="checkbox" name="participantes" value="${u.id}"> ${esc(u.nombre)}${u.id === yo.id ? " (yo)" : ""}</label>`)
        .join("") || `<p class="vacio">No hay otras personas registradas.</p>`;

    if (yo.rol !== "admin") return;
    $("#lista-personas").innerHTML = usuarios.map((u) => `
        <li class="${u.activo ? "" : "inactiva"}">
            <span class="datos">${esc(u.nombre)} ${u.rol === "admin" ? '<span class="pill">admin</span>' : ""}
                <span class="email">${esc(u.email)}${u.activo ? "" : " · inactiva"}</span></span>
            ${u.id === yo.id ? "" : `
                <button class="secundario" data-activo="${u.id}" data-valor="${u.activo ? "0" : "1"}">${u.activo ? "Desactivar" : "Activar"}</button>
                <button class="secundario" data-borrar="${u.id}">Eliminar</button>`}
        </li>`).join("");
}

$("#form-persona").addEventListener("submit", async (e) => {
    e.preventDefault();
    const form = new FormData(e.target);
    try {
        await api("/usuarios", {
            method: "POST",
            body: JSON.stringify({
                nombre: form.get("nombre").trim(),
                email: form.get("email").trim(),
                clave: form.get("clave"),
                rol: form.get("rol"),
            }),
        });
        e.target.reset();
        mostrarMensaje("Persona agregada", "ok", "#msg-persona");
        await cargarUsuarios();
    } catch (err) {
        mostrarMensaje(err.message, "error", "#msg-persona");
    }
});

$("#lista-personas").addEventListener("click", async (e) => {
    const boton = e.target.closest("button[data-borrar], button[data-activo]");
    if (!boton) return;
    const id = Number(boton.dataset.borrar || boton.dataset.activo);
    const persona = usuarios.find((u) => u.id === id);
    if (boton.dataset.borrar && boton.dataset.confirmar !== "1") {
        // Confirmación en dos clics
        boton.dataset.confirmar = "1";
        boton.textContent = "¿Seguro?";
        setTimeout(() => { boton.dataset.confirmar = ""; boton.textContent = "Eliminar"; }, 3000);
        return;
    }
    try {
        if (boton.dataset.borrar) {
            await api(`/usuarios/${id}`, { method: "DELETE" });
            mostrarMensaje(`${persona.nombre} eliminada`, "ok", "#msg-persona");
        } else {
            await api(`/usuarios/${id}`, {
                method: "PATCH",
                body: JSON.stringify({ activo: boton.dataset.valor === "1" }),
            });
        }
        await cargarUsuarios();
        await cargarReuniones();
    } catch (err) {
        mostrarMensaje(err.message, "error", "#msg-persona");
    }
});

// ---------------------------------------------------------------- reuniones

function tarjeta(r) {
    const participantes = r.participantes.map(nombre).map(esc).join(", ");
    const gestiona = yo.rol === "admin" || r.organizador_id === yo.id;
    let detalle = "";
    if (r.estado === "confirmada") {
        detalle = `<p class="confirmada">${esc(fecha(r.inicio_confirmado))}</p>`;
    } else if (r.estado === "con_sugerencias") {
        detalle = `<ol class="sugerencias">${r.sugerencias.map((s) => `
            <li>
                <span>${esc(fecha(s.inicio))} – ${esc(hora(s.fin))}</span>
                <span class="score">score ${s.score}</span>
                ${gestiona ? `<button data-accion="confirmar" data-reunion="${r.id}" data-sugerencia="${s.id}">Confirmar</button>` : ""}
            </li>`).join("")}</ol>`;
    } else if (r.estado === "sin_huecos") {
        detalle = `<p class="vacio">No hay un hueco común en la ventana.</p>`;
    }
    const acciones = !gestiona || ["confirmada", "cancelada"].includes(r.estado) ? "" : `
        <div class="acciones">
            <button class="secundario" data-accion="recalcular" data-reunion="${r.id}">Recalcular</button>
            <button class="secundario" data-accion="cancelar" data-reunion="${r.id}">Cancelar</button>
        </div>`;
    return `
        <article class="tarjeta">
            <div class="cabecera">
                <h3>${esc(r.titulo)}</h3>
                <span class="estado ${r.estado}">${ETIQUETAS[r.estado] ?? esc(r.estado)}</span>
            </div>
            <p class="meta">${r.duracion_min} min · organiza ${esc(nombre(r.organizador_id))} · ${participantes}</p>
            ${detalle}
            ${acciones}
        </article>`;
}

async function cargarReuniones() {
    const cont = $("#lista-reuniones");
    try {
        const data = await api("/reuniones");
        cont.innerHTML = data.length
            ? data.map(tarjeta).join("")
            : `<p class="vacio">Todavía no hay reuniones.</p>`;
    } catch (e) {
        cont.innerHTML = `<p class="error">${esc(e.message)}</p>`;
    }
}

$("#form-reunion").addEventListener("submit", async (e) => {
    e.preventDefault();
    const form = new FormData(e.target);
    const boton = e.target.querySelector("button[type=submit]");
    boton.disabled = true;
    try {
        const r = await api("/reuniones", {
            method: "POST",
            body: JSON.stringify({
                titulo: form.get("titulo"),
                duracion_min: Number(form.get("duracion")),
                ventana_inicio: form.get("inicio"),
                ventana_fin: form.get("fin"),
                organizador_id: yo.rol === "admin" ? Number(form.get("organizador")) : yo.id,
                participantes: form.getAll("participantes").map(Number),
            }),
        });
        mostrarMensaje(`Reunión creada: ${ETIQUETAS[r.estado] ?? r.estado}`, "ok", "#msg-form");
        e.target.reset();
        valoresPorDefecto();
        await cargarReuniones();
    } catch (err) {
        mostrarMensaje(err.message, "error", "#msg-form");
    } finally {
        boton.disabled = false;
    }
});

$("#lista-reuniones").addEventListener("click", async (e) => {
    const boton = e.target.closest("button[data-accion]");
    if (!boton) return;
    const { accion, reunion, sugerencia } = boton.dataset;
    boton.disabled = true;
    try {
        const body = accion === "confirmar" ? JSON.stringify({ sugerencia_id: Number(sugerencia) }) : undefined;
        await api(`/reuniones/${reunion}/${accion}`, { method: "POST", body });
    } catch (err) {
        mostrarMensaje(err.message, "error", "#msg-form");
    }
    await cargarReuniones();
});

function valoresPorDefecto() {
    // Ventana por defecto: desde mañana 08:00 hasta 5 días después a las 18:00.
    const aIso = (d) => new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
    const inicio = new Date();
    inicio.setDate(inicio.getDate() + 1);
    inicio.setHours(8, 0, 0, 0);
    const fin = new Date(inicio);
    fin.setDate(fin.getDate() + 5);
    fin.setHours(18, 0, 0, 0);
    $("input[name=inicio]").value = aIso(inicio);
    $("input[name=fin]").value = aIso(fin);
}

// ---------------------------------------------------------------- inicio

(async function iniciar() {
    if (!obtenerToken()) return mostrarVista("login");
    try {
        await entrar(await api("/auth/yo"));
    } catch {
        cerrarSesion();
    }
})();
