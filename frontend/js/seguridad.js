"use strict";
/* Perfil → Seguridad: agregar el método de verificación que falta y elegir el preferido. */
(function () {
    exigirSesion();
    pintarNav();
    const $ = (id) => document.getElementById(id);
    const avisoEl = $("aviso");
    const NOMBRES = { totp: "App autenticadora", correo: "Código por correo" };
    let agregando = null;

    function pintar(estado) {
        $("metodos").innerHTML = Object.entries(NOMBRES).map(([clave, nombre]) => {
            const activo = estado.activos.includes(clave);
            const etiqueta = activo ? `Activa${clave === estado.preferido ? " · se pide por defecto" : ""}` : "Sin configurar";
            const accion = !activo
                ? `<button type="button" class="boton" data-agregar="${clave}">Agregar</button>`
                : clave !== estado.preferido
                    ? `<button type="button" class="boton boton-secundario" data-preferido="${clave}">Pedir este por defecto</button>`
                    : "";
            return `<li><div><strong>${nombre}</strong><br><small>${etiqueta}</small></div>${accion}</li>`;
        }).join("");
    }

    async function cargar() {
        try { pintar(await api("/auth/mfa")); } catch (err) { aviso(avisoEl, err.message); }
    }

    $("metodos").addEventListener("click", async (e) => {
        const { agregar, preferido } = e.target.dataset || {};
        try {
            if (preferido) {
                pintar(await api("/auth/mfa/preferido", { method: "POST", body: JSON.stringify({ metodo: preferido }) }));
            } else if (agregar) {
                const r = await api("/auth/mfa/agregar", { method: "POST", body: JSON.stringify({ metodo: agregar }) });
                agregando = agregar;
                $("agregar-titulo").textContent = `Agregar: ${NOMBRES[agregar]}`;
                $("agregar-qr").hidden = agregar !== "totp";
                $("agregar-correo").hidden = agregar !== "correo";
                if (agregar === "totp") {
                    $("qr-imagen").innerHTML = r.qr;  // SVG generado por el servidor
                    $("qr-clave").textContent = r.secreto;
                } else {
                    $("agregar-correo").textContent = `Te enviamos un código de 6 dígitos a ${sesion.usuario.email}. Vence en 10 minutos.`;
                }
                $("agregar").hidden = false;
                $("codigo").focus();
            }
        } catch (err) { aviso(avisoEl, err.message); }
    });

    $("form-activar").addEventListener("submit", async (e) => {
        e.preventDefault();
        try {
            const estado = await api("/auth/mfa/agregar/activar", {
                method: "POST",
                body: JSON.stringify({ metodo: agregando, codigo: $("codigo").value.replace(/\D/g, "") }),
            });
            $("agregar").hidden = true;
            $("codigo").value = "";
            aviso(avisoEl, `${NOMBRES[agregando]} quedó activada como segundo paso.`, "ok");
            pintar(estado);
        } catch (err) { aviso(avisoEl, err.message); }
    });

    cargar();
})();