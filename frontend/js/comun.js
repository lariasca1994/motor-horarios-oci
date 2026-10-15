/* Utilidades compartidas por todas las páginas: sesión, API, navegación y formato. */
"use strict";

const API = (window.APP_CONFIG?.API_URL || "").replace(/\/$/, "");
const CLAVE_SESION = "motorhorarios-sesion";

// ---------------------------------------------------------------- sesión

const sesion = {
    leer() {
        try { return JSON.parse(localStorage.getItem(CLAVE_SESION)) || null; } catch { return null; }
    },
    guardar(datos) {
        try { localStorage.setItem(CLAVE_SESION, JSON.stringify(datos)); } catch { /* sin storage */ }
    },
    cerrar() {
        try { localStorage.removeItem(CLAVE_SESION); } catch { /* sin storage */ }
    },
    get usuario() { return this.leer()?.usuario || null; },
    get token() { return this.leer()?.token || null; },
};

function irA(pagina) {
    location.href = pagina;
}

/** Exige sesión (y opcionalmente permisos de gestión); si no, redirige. */
function exigirSesion({ admin = false } = {}) {
    const u = sesion.usuario;
    if (!u) {
        irA(`login.html?volver=${encodeURIComponent(location.pathname.split("/").pop() + location.search)}`);
        throw new Error("sin sesión");
    }
    if (admin && u.rol !== "admin") {
        irA("reuniones.html");
        throw new Error("sin permiso");
    }
    return u;
}

// ---------------------------------------------------------------- API

let avisoDespertar = null;

async function api(ruta, opciones = {}) {
    const headers = { "Content-Type": "application/json" };
    if (sesion.token) headers.Authorization = `Bearer ${sesion.token}`;

    // Render gratis se duerme: si tarda, avisamos que el servidor está despertando.
    const temporizador = setTimeout(mostrarDespertar, 3000);
    let res;
    try {
        res = await fetch(`${API}${ruta}`, { ...opciones, headers });
    } catch {
        mostrarMantenimiento();
        throw new Error("No se pudo conectar con el servidor. Intenta de nuevo en unos segundos.");
    } finally {
        clearTimeout(temporizador);
        ocultarDespertar();
    }

    // API caída (502/504 de la plataforma) o base de datos apagada (503 de la API).
    if ([502, 503, 504].includes(res.status)) {
        mostrarMantenimiento();
        throw new Error("El servicio está en mantenimiento.");
    }

    const datos = res.status === 204 ? null : await res.json().catch(() => null);
    if (res.status === 401 && !ruta.startsWith("/auth/")) {
        sesion.cerrar();
        irA("login.html?vencida=1");
        throw new Error("sesión vencida");
    }
    if (!res.ok) {
        const detalle = Array.isArray(datos?.detail)
            ? datos.detail.map((d) => traducirValidacion(d)).join("; ")
            : datos?.detail;
        throw new Error(detalle || `Error ${res.status}`);
    }
    return datos;
}

function traducirValidacion(d) {
    const campo = d.loc?.[d.loc.length - 1];
    if (d.type === "string_too_short" && campo === "clave") return "la contraseña debe tener al menos 10 caracteres";
    if (d.type === "value_error" && campo === "email") return "el correo no es válido";
    return d.msg?.replace(/^Value error, /, "") || "dato inválido";
}

function mostrarDespertar() {
    if (avisoDespertar) return;
    avisoDespertar = document.createElement("p");
    avisoDespertar.className = "aviso info";
    avisoDespertar.textContent = "Despertando el servidor… la primera carga puede tardar hasta un minuto.";
    document.querySelector("main")?.prepend(avisoDespertar);
}

/**
 * Pantalla de mantenimiento: reemplaza el contenido cuando la API no responde.
 * No reintenta la acción del usuario (podría duplicarla): consulta /health cada
 * 15 s y recarga la página sola cuando el servicio vuelve.
 */
let enMantenimiento = false;

function mostrarMantenimiento() {
    if (enMantenimiento) return;
    enMantenimiento = true;
    const main = document.querySelector("main");
    if (!main) return;
    document.title = "En mantenimiento — Motor de Horarios";
    // Se oculta el contenido en vez de borrarlo: las cargas que siguen en curso
    // encuentran sus elementos y no lanzan errores.
    for (const hijo of main.children) hijo.hidden = true;
    main.insertAdjacentHTML("afterbegin", `
        <section class="mantenimiento" role="status" aria-live="polite">
            <div class="mantenimiento-icono" aria-hidden="true"><span></span><span></span><span></span></div>
            <p class="mantenimiento-etiqueta">Motor de Horarios</p>
            <h1>Estamos en mantenimiento</h1>
            <p>El servicio no está respondiendo en este momento, así que no se pueden consultar ni proponer reuniones.</p>
            <ul>
                <li>Tus reuniones y tu agenda siguen guardadas.</li>
                <li>Ninguna acción quedó a medias: si no viste la confirmación, no se guardó.</li>
                <li>Esta página se recarga sola cuando el servicio vuelva.</li>
            </ul>
            <button type="button" class="boton" id="reintentar">Reintentar ahora</button>
        </section>`);
    document.getElementById("reintentar").addEventListener("click", () => location.reload());
    setInterval(async () => {
        try {
            const r = await fetch(`${API}/health`, { cache: "no-store" });
            if (r.ok) location.reload();
        } catch { /* sigue caído */ }
    }, 15000);
}

function ocultarDespertar() {
    avisoDespertar?.remove();
    avisoDespertar = null;
}

// ---------------------------------------------------------------- navegación

function pintarNav() {
    const nav = document.getElementById("nav");
    if (!nav) return;
    const u = sesion.usuario;
    const enlaces = u
        ? [
            ["reuniones.html", "Reuniones"],
            ["agenda.html", "Mi agenda"],
            ...(u.rol === "admin" ? [["usuarios.html", "Usuarios"]] : []),
            ["clave.html", "Contraseña"],
        ]
        : [["login.html", "Ingresar"], ["registro.html", "Registrarme"]];
    const actual = location.pathname.split("/").pop().replace(/\.html$/, "") || "index";
    nav.innerHTML = enlaces
        .map(([href, texto]) => `<a href="${href}"${href.replace(".html", "") === actual ? ' aria-current="page"' : ""}>${texto}</a>`)
        .join("");
    if (u) {
        nav.insertAdjacentHTML("beforeend", `
            <a href="#" id="salir">Salir (${esc(u.nombre)})</a>`);
        document.getElementById("salir").addEventListener("click", (e) => {
            e.preventDefault();
            sesion.cerrar();
            irA("/");
        });
    }
}

// ---------------------------------------------------------------- utilidades

function esc(valor) {
    const div = document.createElement("div");
    div.textContent = valor ?? "";
    return div.innerHTML;
}

function aviso(elemento, texto, tipo = "error") {
    elemento.textContent = texto;
    elemento.className = `aviso ${tipo}`;
    elemento.hidden = false;
}

const _fmtFecha = new Intl.DateTimeFormat("es-CO", {
    weekday: "short", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit",
});
const _fmtHora = new Intl.DateTimeFormat("es-CO", { hour: "2-digit", minute: "2-digit" });
const _fmtDia = new Intl.DateTimeFormat("es-CO", { weekday: "short", day: "2-digit", month: "short", year: "numeric" });
const fecha = (iso) => _fmtFecha.format(new Date(iso));
const hora = (iso) => _fmtHora.format(new Date(iso));
const dia = (iso) => _fmtDia.format(new Date(iso));

/** Fecha local "YYYY-MM-DDTHH:MM" para inputs datetime-local. */
function aInputLocal(d) {
    return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}

/** Confirmación en dos clics sobre el mismo botón (sin diálogos del navegador). */
function confirmarEnDosClics(boton, textoConfirmar = "¿Seguro?") {
    if (boton.dataset.confirmar === "1") return true;
    const original = boton.textContent;
    boton.dataset.confirmar = "1";
    boton.textContent = textoConfirmar;
    setTimeout(() => { boton.dataset.confirmar = ""; boton.textContent = original; }, 3000);
    return false;
}

document.addEventListener("DOMContentLoaded", pintarNav);
