"use strict";
/* Segundo paso del ingreso (obligatorio): primera vez se elige el método; después se pide su código.
   El "pase" del login vive en sessionStorage y vence a los 10 minutos en el servidor. */
(function () {
    const paso = mfa.leer();
    if (!paso) { irA("login.html"); return; }
    const $ = (id) => document.getElementById(id);
    const avisoEl = $("aviso");
    const NOMBRES = { totp: "app autenticadora", correo: "código por correo" };
    let metodo = paso.metodo;
    let modo = paso.configurado ? "verificar" : "elegir";

    function terminar(s) {
        sesion.guardar(s);
        mfa.limpiar();
        irA(paso.volver || "reuniones.html");
    }

    function pedirCodigo(texto) {
        $("subtitulo").textContent = texto;
        $("form-codigo").hidden = false;
        $("codigo").value = "";
        $("codigo").focus();
    }

    function pintarVerificar() {
        $("elegir").hidden = true;
        $("qr").hidden = true;
        $("boton-codigo").textContent = "Verificar";
        pedirCodigo(metodo === "totp"
            ? "Abre tu app autenticadora y escribe el código de 6 dígitos."
            : `Te enviamos un código de 6 dígitos a ${paso.email}. Vence en 10 minutos.`);
        const otro = (paso.activos || []).find((m) => m !== metodo);
        const enlaces = [];
        if (metodo === "correo") enlaces.push('<a href="#" data-accion="reenviar">Enviar otro código</a>');
        if (otro) enlaces.push(`<a href="#" data-accion="cambiar">Usar ${NOMBRES[otro]}</a>`);
        $("otros").innerHTML = enlaces.join(" · ");
        $("otros").hidden = enlaces.length === 0;
    }

    async function reenviar() {
        try {
            const r = await api("/auth/mfa/correo", { method: "POST", body: JSON.stringify({ pase: paso.pase }) });
            aviso(avisoEl, r.detail, "ok");
        } catch (err) { aviso(avisoEl, err.message); }
    }

    $("otros").addEventListener("click", async (e) => {
        const accion = e.target.dataset?.accion;
        if (!accion) return;
        e.preventDefault();
        if (accion === "reenviar") return reenviar();
        metodo = (paso.activos || []).find((m) => m !== metodo);
        pintarVerificar();
        if (metodo === "correo") reenviar();
    });

    $("elegir").addEventListener("click", async (e) => {
        const elegido = e.target.dataset?.metodo;
        if (!elegido) return;
        try {
            const r = await api("/auth/mfa/configurar", { method: "POST", body: JSON.stringify({ pase: paso.pase, metodo: elegido }) });
            metodo = elegido;
            modo = "activar";
            $("elegir").hidden = true;
            $("boton-codigo").textContent = "Activar";
            if (elegido === "totp") {
                $("qr-imagen").innerHTML = r.qr;  // SVG generado por el servidor
                $("qr-clave").textContent = r.secreto;
                $("qr").hidden = false;
                pedirCodigo("Configura tu app autenticadora.");
            } else {
                pedirCodigo(`Te enviamos un código de 6 dígitos a ${paso.email}. Vence en 10 minutos.`);
            }
            $("otros").innerHTML = '<a href="verificacion.html">Elegir otro método</a>';
            $("otros").hidden = false;
        } catch (err) { aviso(avisoEl, err.message); }
    });

    $("form-codigo").addEventListener("submit", async (e) => {
        e.preventDefault();
        const boton = $("boton-codigo");
        boton.disabled = true;
        try {
            const ruta = modo === "activar" ? "/auth/mfa/activar" : "/auth/mfa/verificar";
            const s = await api(ruta, {
                method: "POST",
                body: JSON.stringify({ pase: paso.pase, metodo, codigo: $("codigo").value.replace(/\D/g, "") }),
            });
            terminar(s);
        } catch (err) {
            aviso(avisoEl, err.message);
            boton.disabled = false;
        }
    });

    if (modo === "elegir") {
        $("subtitulo").textContent = "Además de la contraseña, cada ingreso pedirá un código. Elige cómo recibirlo; después puedes agregar el otro en Seguridad.";
        $("elegir").hidden = false;
    } else {
        pintarVerificar();
    }
})();