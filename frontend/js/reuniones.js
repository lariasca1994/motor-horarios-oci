"use strict";
(function () {
    const yo = exigirSesion();
    const esAdmin = yo.rol === "admin";
    const avisoEl = document.getElementById("aviso");
    const $ = (sel) => document.querySelector(sel);
    let usuarios = [];

    const ETIQUETAS = {
        pendiente: "Calculando",
        con_sugerencias: "Con sugerencias",
        sin_huecos: "Sin huecos",
        confirmada: "Confirmada",
        cancelada: "Cancelada",
    };
    const nombre = (id) => usuarios.find((u) => u.id === id)?.nombre ?? `#${id}`;

    $("#titulo").textContent = esAdmin ? "Todas las reuniones" : "Mis reuniones";
    $("#campo-organizador").hidden = !esAdmin;

    function ventanaPorDefecto() {
        // Desde mañana 08:00 hasta 5 días después a las 18:00
        const inicio = new Date();
        inicio.setDate(inicio.getDate() + 1);
        inicio.setHours(8, 0, 0, 0);
        const fin = new Date(inicio);
        fin.setDate(fin.getDate() + 5);
        fin.setHours(18, 0, 0, 0);
        $("#inicio").value = aInputLocal(inicio);
        $("#fin").value = aInputLocal(fin);
    }

    async function cargarUsuarios() {
        usuarios = await api("/usuarios");
        const activos = usuarios.filter((u) => u.activo);
        $("#organizador").innerHTML = activos
            .map((u) => `<option value="${u.id}" ${u.id === yo.id ? "selected" : ""}>${esc(u.nombre)}</option>`)
            .join("");
        const otros = activos.filter((u) => u.id !== yo.id || esAdmin);
        $("#participantes").innerHTML = otros.length
            ? otros.map((u) => `
                <label class="casilla"><input type="checkbox" name="participantes" value="${u.id}">
                ${esc(u.nombre)}${u.id === yo.id ? " (yo)" : ""}</label>`).join("")
            : '<span class="vacio">No hay otras personas registradas.</span>';
    }

    function tarjeta(r) {
        const gestiona = esAdmin || r.organizador_id === yo.id;
        let detalle = "";
        if (r.estado === "confirmada") {
            detalle = `<p class="confirmada">${esc(fecha(r.inicio_confirmado))}</p>`;
        } else if (r.estado === "con_sugerencias") {
            detalle = `<ol class="sugerencias">${r.sugerencias.map((s) => `
                <li>
                    <span class="cuando">${esc(fecha(s.inicio))} – ${esc(hora(s.fin))}</span>
                    <span class="puntaje">puntaje ${s.score}</span>
                    ${gestiona ? `<button class="boton boton-chico" data-accion="confirmar" data-reunion="${r.id}" data-sugerencia="${s.id}">Confirmar</button>` : ""}
                </li>`).join("")}</ol>`;
        } else if (r.estado === "sin_huecos") {
            detalle = '<p class="vacio">No hay un hueco común en la ventana. Amplía las fechas o revisa las agendas.</p>';
        }
        const acciones = !gestiona || ["confirmada", "cancelada"].includes(r.estado) ? "" : `
            <div class="acciones" style="margin-top:0.75rem">
                <button class="enlace-boton" data-accion="recalcular" data-reunion="${r.id}">Recalcular</button>
                <button class="enlace-boton enlace-boton-peligro" data-accion="cancelar" data-reunion="${r.id}">Cancelar</button>
            </div>`;
        return `
            <article class="tarjeta">
                <div class="cabecera-tarjeta">
                    <h3>${esc(r.titulo)}</h3>
                    <span class="estado-reunion estado-${r.estado}">${ETIQUETAS[r.estado] ?? esc(r.estado)}</span>
                </div>
                <p class="meta">${r.duracion_min} min · organiza ${esc(nombre(r.organizador_id))} ·
                    ${r.participantes.map(nombre).map(esc).join(", ")}</p>
                ${detalle}
                ${acciones}
            </article>`;
    }

    /** Franja de indicadores con las reuniones ya cargadas (solo presentación). */
    function pintarResumen(data) {
        let caja = $("#resumen");
        if (!caja) {
            caja = document.createElement("dl");
            caja.id = "resumen";
            caja.className = "resumen-reuniones";
            $("#lista").before(caja);
        }
        if (!data.length) { caja.hidden = true; return; }
        caja.hidden = false;
        const contar = (estado) => data.filter((r) => r.estado === estado).length;
        const partes = [
            ["con_sugerencias", contar("con_sugerencias")],
            ["confirmada", contar("confirmada")],
            ["sin_huecos", contar("sin_huecos")],
        ];
        const otras = data.length - partes.reduce((s, [, n]) => s + n, 0);
        const celdas = [["Reuniones", data.length], ["Con sugerencias", partes[0][1]], ["Confirmadas", partes[1][1]], ["Sin huecos", partes[2][1]]];
        caja.innerHTML = celdas.map(([nombre, n]) => `<div><dt>${nombre}</dt><dd data-valor="${n}">${n}</dd></div>`).join("")
            + `<div class="resumen-barra" aria-hidden="true">${[...partes, ["otras", otras]].filter(([, n]) => n > 0)
                .map(([clase, n]) => `<i class="${clase}" style="flex-grow:${n}"></i>`).join("")}</div>`;
        // Las cifras cuentan desde cero al aparecer.
        if (!matchMedia("(prefers-reduced-motion: reduce)").matches) {
            caja.querySelectorAll("dd").forEach((dd) => {
                const destino = Number(dd.dataset.valor);
                const inicio = performance.now();
                const paso = (ahora) => {
                    const avance = Math.min(1, (ahora - inicio) / 700);
                    dd.textContent = String(Math.round(destino * (1 - (1 - avance) ** 3)));
                    if (avance < 1) requestAnimationFrame(paso);
                };
                requestAnimationFrame(paso);
            });
        }
    }

    async function cargarReuniones() {
        const lista = $("#lista");
        try {
            const data = await api("/reuniones");
            pintarResumen(data);
            lista.innerHTML = data.length
                ? data.map(tarjeta).join("")
                : '<div class="tarjeta"><p class="vacio" style="margin:0">Todavía no hay reuniones. Propón la primera.</p></div>';
        } catch (e) {
            lista.innerHTML = `<p class="aviso error">${esc(e.message)}</p>`;
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
                    // Si la lista aún no cargó (API despertando), organiza quien crea la reunión.
            organizador_id: esAdmin ? Number(form.get("organizador")) || yo.id : yo.id,
                    participantes: form.getAll("participantes").map(Number),
                }),
            });
            aviso(avisoEl, `Reunión "${r.titulo}" creada: ${ETIQUETAS[r.estado] ?? r.estado}.`, "ok");
            e.target.reset();
            ventanaPorDefecto();
            await cargarReuniones();
        } catch (err) {
            aviso(avisoEl, err.message);
        } finally {
            boton.disabled = false;
        }
    });

    $("#lista").addEventListener("click", async (e) => {
        const boton = e.target.closest("button[data-accion]");
        if (!boton) return;
        const { accion, reunion, sugerencia } = boton.dataset;
        if (accion === "cancelar" && !confirmarEnDosClics(boton, "¿Cancelar?")) return;
        boton.disabled = true;
        try {
            const body = accion === "confirmar" ? JSON.stringify({ sugerencia_id: Number(sugerencia) }) : undefined;
            await api(`/reuniones/${reunion}/${accion}`, { method: "POST", body });
        } catch (err) {
            aviso(avisoEl, err.message);
        }
        await cargarReuniones();
    });

    ventanaPorDefecto();
    cargarUsuarios().then(cargarReuniones).catch((e) => aviso(avisoEl, e.message));
})();
