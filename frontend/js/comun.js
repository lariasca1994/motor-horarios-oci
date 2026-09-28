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
        throw new Error("No se pudo conectar con el servidor. Intenta de nuevo en unos segundos.");
    } finally {
        clearTimeout(temporizador);
        ocultarDespertar();
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
            irA("index.html");
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
