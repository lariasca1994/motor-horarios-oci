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

// Paso intermedio del ingreso (verificación en dos pasos): solo dura la pestaña.
const CLAVE_MFA = "motorhorarios-mfa";
const mfa = {
    leer() {
        try { return JSON.parse(sessionStorage.getItem(CLAVE_MFA)) || null; } catch { return null; }
    },
    guardar(datos) {
        try { sessionStorage.setItem(CLAVE_MFA, JSON.stringify(datos)); } catch { /* sin storage */ }
    },
    limpiar() {
        try { sessionStorage.removeItem(CLAVE_MFA); } catch { /* sin storage */ }
    },
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
    document.title = "En mantenimiento — Coordinador de reuniones";
    // Se oculta el contenido en vez de borrarlo: las cargas que siguen en curso
    // encuentran sus elementos y no lanzan errores.
    for (const hijo of main.children) hijo.hidden = true;
    main.insertAdjacentHTML("afterbegin", `
        <section class="mantenimiento" role="status" aria-live="polite">
            <div class="mant-orbe" aria-hidden="true"><span></span><span></span><span></span>
                <b><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18M12 14v3l2 1"/></svg></b>
            </div>
            <p class="mantenimiento-etiqueta">Coordinador de reuniones</p>
            <h1>Estamos en mantenimiento</h1>
            <p>El servicio no está respondiendo en este momento, así que no se pueden consultar ni proponer reuniones.</p>
            <ul>
                <li>Tus reuniones y tu agenda siguen guardadas.</li>
                <li>Ninguna acción quedó a medias: si no viste la confirmación, no se guardó.</li>
                <li>Esta página se recarga sola cuando el servicio vuelva.</li>
            </ul>
            <div class="mant-pie">
                <span class="mant-cuenta">
                    <svg viewBox="0 0 24 24" aria-hidden="true"><circle class="anillo-fondo" cx="12" cy="12" r="9"/><circle class="anillo-valor" id="mant-anillo" cx="12" cy="12" r="9" pathLength="1"/></svg>
                    <span id="mant-texto">Reintento automático en 15 s</span>
                </span>
                <button type="button" class="boton" id="reintentar">Reintentar ahora</button>
            </div>
        </section>`);
    document.getElementById("reintentar").addEventListener("click", () => location.reload());
    // Cada 15 s consulta /health (con cuenta regresiva visible) y recarga cuando responde.
    const TOTAL = 15;
    let resto = TOTAL;
    let revisando = false;
    const anillo = document.getElementById("mant-anillo");
    const texto = document.getElementById("mant-texto");
    const pintar = () => {
        anillo.style.strokeDashoffset = revisando ? 0 : 1 - resto / TOTAL;
        texto.textContent = revisando ? "Comprobando…" : `Reintento automático en ${resto} s`;
    };
    pintar();
    setInterval(async () => {
        if (revisando) return;
        resto -= 1;
        if (resto > 0) { pintar(); return; }
        revisando = true;
        pintar();
        try {
            const r = await fetch(`${API}/health`, { cache: "no-store" });
            if (r.ok) { location.reload(); return; }
        } catch { /* sigue caído */ }
        revisando = false;
        resto = TOTAL;
        pintar();
    }, 1000);
}

function ocultarDespertar() {
    avisoDespertar?.remove();
    avisoDespertar = null;
}

// ---------------------------------------------------------------- navegación

const ICONOS = {
    reuniones: '<path d="M8 2v4M16 2v4"/><rect x="3" y="4" width="18" height="18" rx="2"/><path d="M3 10h18M9 16l2 2 4-4"/>',
    agenda: '<path d="M8 2v4M16 2v4"/><rect x="3" y="4" width="18" height="18" rx="2"/><path d="M3 10h18M8 14h.01M12 14h.01M16 14h.01M8 18h.01M12 18h.01"/>',
    usuarios: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
    clave: '<circle cx="7.5" cy="15.5" r="5.5"/><path d="m21 2-9.6 9.6M15.5 7.5l3 3L22 7l-3-3"/>',
    seguridad: '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m9 12 2 2 4-4"/>',
    salir: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/>',
    mas: '<circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/><circle cx="5" cy="12" r="1"/>',
    alternar: '<path d="m11 17-5-5 5-5M18 17l-5-5 5-5"/>',
};
const icono = (nombre) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONOS[nombre]}</svg>`;

function pintarNav() {
    const nav = document.getElementById("nav");
    if (!nav) return;
    const u = sesion.usuario;
    const actual = location.pathname.split("/").pop().replace(/\.html$/, "") || "index";
    if (!u) {
        nav.innerHTML = [["login.html", "Ingresar"], ["registro.html", "Registrarme"]]
            .map(([href, texto]) => `<a href="${href}"${href.replace(".html", "") === actual ? ' aria-current="page"' : ""}>${texto}</a>`)
            .join("");
        return;
    }
    // Con sesión: menú lateral (extendido o compacto). En el teléfono, barra inferior con
    // Reuniones, Mi agenda y Usuarios; Contraseña, Seguridad y Salir van en la hoja "Más".
    document.body.classList.add("con-menu");
    const marca = document.querySelector(".barra .marca");
    if (marca && !marca.querySelector(".marca-texto")) {
        const nodo = [...marca.childNodes].find((n) => n.nodeType === 3 && n.textContent.trim());
        if (nodo) {
            const span = document.createElement("span");
            span.className = "marca-texto";
            span.textContent = nodo.textContent.trim();
            nodo.replaceWith(span);
        }
    }
    const principales = [
        ["reuniones.html", "Reuniones", "Reuniones", "reuniones"],
        ["agenda.html", "Mi agenda", "Agenda", "agenda"],
        ...(u.rol === "admin" ? [["usuarios.html", "Usuarios", "Usuarios", "usuarios"]] : []),
    ];
    const secundarios = [
        ["clave.html", "Contraseña", "clave"],
        ["seguridad.html", "Seguridad", "seguridad"],
    ];
    const marcar = (href) => (href.replace(".html", "") === actual ? ' aria-current="page"' : "");
    const enMas = secundarios.some(([href]) => href.replace(".html", "") === actual);
    let k = 0;
    nav.innerHTML = `
        <span class="menu-ind" aria-hidden="true"></span><span class="menu-hov" aria-hidden="true"></span>
        ${principales.map(([href, largo, corto, ic]) => `
            <a class="menu-op" href="${href}" style="--k:${k++}"${marcar(href)}>${icono(ic)}<span class="menu-texto"><span class="texto-largo">${largo}</span><span class="texto-corto">${corto}</span></span></a>`).join("")}
        ${secundarios.map(([href, texto, ic]) => `
            <a class="menu-op solo-amplio" href="${href}" style="--k:${k++}"${marcar(href)}>${icono(ic)}<span class="menu-texto">${texto}</span></a>`).join("")}
        <button type="button" class="menu-op menu-mas solo-movil${enMas ? " contiene-actual" : ""}" aria-haspopup="dialog" aria-expanded="false">${icono("mas")}<span class="menu-texto">Más</span></button>
        <div class="menu-pie">
            <button type="button" class="menu-op menu-alternar" aria-expanded="true">${icono("alternar")}<span class="menu-texto texto-largo">Compactar menú</span></button>
            <a class="menu-op" href="#" id="salir" style="--k:${k++}">${icono("salir")}<span class="menu-texto">Salir (${esc(u.nombre)})</span></a>
        </div>`;
    document.body.insertAdjacentHTML("beforeend", `
        <span class="menu-etiqueta" aria-hidden="true"></span>
        <dialog class="hoja-mas" aria-label="Más opciones">
            ${secundarios.map(([href, texto, ic], i) => `<a href="${href}" style="--k:${i}"${marcar(href)}>${icono(ic)}${texto}</a>`).join("")}
            <a href="#" id="salir-hoja" style="--k:${secundarios.length}">${icono("salir")}Salir (${esc(u.nombre)})</a>
        </dialog>`);
    for (const id of ["salir", "salir-hoja"]) {
        document.getElementById(id).addEventListener("click", (e) => {
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
