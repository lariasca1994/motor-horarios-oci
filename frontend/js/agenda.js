"use strict";
(function () {
    const yo = exigirSesion();
    const $ = (sel) => document.querySelector(sel);
    const avisoEl = document.getElementById("aviso");
    const params = new URLSearchParams(location.search);

    // Un admin puede gestionar la agenda de otra persona con ?usuario=ID
    const pedido = Number(params.get("usuario"));
    const usuarioId = yo.rol === "admin" && pedido ? pedido : yo.id;
    const base = `/usuarios/${usuarioId}`;

    const DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"];
    const DIAS_CORTOS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"];
    const BYDAY = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"];
    const dosDigitos = (n) => String(n).padStart(2, "0");

    // ------------------------------------------------------------ formularios

    function casillasDias(contenedor, nombre) {
        contenedor.innerHTML = DIAS.map((d, i) => `
            <label class="casilla"><input type="checkbox" name="${nombre}" value="${i}"> ${d}</label>`).join("");
    }
    casillasDias($("#dias-laborables"), "dias");
    casillasDias($("#dias-semana"), "dias_semana");

    const opcionesHora = (desde, hasta) => ['<option value="">Sin límite</option>']
        .concat(Array.from({ length: hasta - desde + 1 }, (_, i) => desde + i)
            .map((h) => `<option value="${h}">${dosDigitos(h)}:00</option>`)).join("");
    $("#desde").innerHTML = opcionesHora(0, 23);
    $("#hasta").innerHTML = opcionesHora(1, 24);

    $("#repeticion").addEventListener("change", () => {
        const r = $("#repeticion").value;
        $("#campo-dias-semana").hidden = r !== "semanal";
        $("#campo-hasta").hidden = r === "";
    });

    const hoy = new Date();
    $("#fecha").value = aInputLocal(hoy).slice(0, 10);

    // ------------------------------------------------------------ reglas

    async function cargarReglas() {
        const r = await api(`${base}/reglas`);
        $("#desde").value = r.no_antes_de ?? "";
        $("#hasta").value = r.no_despues_de ?? "";
        document.querySelectorAll('input[name="dias"]').forEach((c) => {
            c.checked = r.dias_laborables.includes(Number(c.value));
        });
    }

    $("#form-reglas").addEventListener("submit", async (e) => {
        e.preventDefault();
        const dias = [...document.querySelectorAll('input[name="dias"]:checked')].map((c) => Number(c.value));
        if (!dias.length) return aviso(avisoEl, "Elige al menos un día laborable.");
        const valor = (id) => ($(id).value === "" ? null : Number($(id).value));
        try {
            await api(`${base}/reglas`, {
                method: "PUT",
                body: JSON.stringify({ no_antes_de: valor("#desde"), no_despues_de: valor("#hasta"), dias_laborables: dias }),
            });
            aviso(avisoEl, "Horario guardado.", "ok");
        } catch (err) {
            aviso(avisoEl, err.message);
        }
    });

    // ------------------------------------------------------------ bloques

    function describirRepeticion(rrule) {
        if (!rrule) return "No se repite";
        const partes = Object.fromEntries(rrule.split(";").map((p) => p.split("=")));
        let texto;
        if (partes.FREQ === "DAILY") {
            texto = "Todos los días";
        } else if (partes.FREQ === "WEEKLY") {
            const dias = (partes.BYDAY || "").split(",").filter(Boolean);
            if (dias.join(",") === "MO,TU,WE,TH,FR") texto = "Lunes a viernes";
            else if (dias.length) texto = "Cada " + dias.map((d) => DIAS_CORTOS[BYDAY.indexOf(d)]).join(", ");
            else texto = "Cada semana";
        } else {
            texto = rrule;
        }
        if (partes.UNTIL) {
            const u = partes.UNTIL;
            texto += ` hasta ${dia(`${u.slice(0, 4)}-${u.slice(4, 6)}-${u.slice(6, 8)}T12:00:00`)}`;
        }
        return texto;
    }

    function describirCuando(b) {
        const rango = `${hora(b.inicio)}–${hora(b.fin)}`;
        return b.rrule ? `${rango}, desde ${dia(b.inicio)}` : `${dia(b.inicio)}, ${rango}`;
    }

    async function cargarBloques() {
        const bloques = await api(`${base}/disponibilidad`);
        $("#bloques").innerHTML = bloques.length
            ? bloques.map((b) => `
                <tr>
                    <td>${esc(b.descripcion || "—")}</td>
                    <td><span class="tipo-bloque tipo-${b.tipo}">${b.tipo === "ocupado" ? "Ocupado" : "Preferido"}</span></td>
                    <td>${esc(describirCuando(b))}</td>
                    <td>${esc(describirRepeticion(b.rrule))}</td>
                    <td><button class="enlace-boton enlace-boton-peligro" data-borrar="${b.id}">Eliminar</button></td>
                </tr>`).join("")
            : '<tr><td colspan="5" class="vacio">Sin bloques todavía. Agrega tus reuniones fijas, almuerzo o clases.</td></tr>';
    }

    $("#bloques").addEventListener("click", async (e) => {
        const boton = e.target.closest("button[data-borrar]");
        if (!boton || !confirmarEnDosClics(boton)) return;
        try {
            await api(`${base}/disponibilidad/${boton.dataset.borrar}`, { method: "DELETE" });
            await cargarBloques();
        } catch (err) {
            aviso(avisoEl, err.message);
        }
    });

    function construirRrule(form) {
        const tipo = form.get("repeticion");
        if (!tipo) return null;
        let regla;
        if (tipo === "diaria") {
            regla = "FREQ=DAILY";
        } else if (tipo === "laborables") {
            regla = "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR";
        } else {
            let dias = form.getAll("dias_semana").map(Number);
            if (!dias.length) dias = [(new Date(`${form.get("fecha")}T12:00:00`).getDay() + 6) % 7];
            regla = "FREQ=WEEKLY;BYDAY=" + dias.sort().map((d) => BYDAY[d]).join(",");
        }
        const hasta = form.get("repetir_hasta");
        if (hasta) regla += `;UNTIL=${hasta.replaceAll("-", "")}T235959`;
        return regla;
    }

    $("#form-bloque").addEventListener("submit", async (e) => {
        e.preventDefault();
        const form = new FormData(e.target);
        const inicio = `${form.get("fecha")}T${form.get("hora_inicio")}`;
        const fin = `${form.get("fecha")}T${form.get("hora_fin")}`;
        if (fin <= inicio) return aviso(avisoEl, "La hora de fin debe ser posterior a la de inicio.");
        const hasta = form.get("repetir_hasta");
        if (form.get("repeticion") && hasta && hasta < form.get("fecha")) {
            return aviso(avisoEl, "La fecha 'repetir hasta' no puede ser anterior a la primera vez.");
        }
        try {
            await api(`${base}/disponibilidad`, {
                method: "POST",
                body: JSON.stringify({
                    inicio, fin,
                    tipo: form.get("tipo"),
                    rrule: construirRrule(form),
                    descripcion: form.get("descripcion").trim() || null,
                }),
            });
            aviso(avisoEl, "Bloque agregado.", "ok");
            e.target.reset();
            $("#fecha").value = aInputLocal(new Date()).slice(0, 10);
            $("#campo-dias-semana").hidden = true;
            $("#campo-hasta").hidden = true;
            await cargarBloques();
        } catch (err) {
            aviso(avisoEl, err.message);
        }
    });

    // ------------------------------------------------------------ inicio

    (async function () {
        try {
            if (usuarioId !== yo.id) {
                const persona = (await api("/usuarios")).find((u) => u.id === usuarioId);
                $("#titulo").textContent = `Agenda de ${persona ? persona.nombre : "#" + usuarioId}`;
                $("#volver-usuarios").hidden = false;
                document.title = `${$("#titulo").textContent} — Motor de Horarios`;
            } else if (params.get("bienvenida")) {
                aviso(avisoEl, "¡Cuenta creada! Revisa tu horario laboral y agrega tus bloques ocupados para recibir mejores sugerencias.", "info");
            }
            await cargarReglas();
            await cargarBloques();
        } catch (err) {
            aviso(avisoEl, err.message);
        }
    })();
})();
