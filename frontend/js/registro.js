"use strict";
(function () {
    const avisoEl = document.getElementById("aviso");
    if (sesion.usuario) irA("reuniones.html");

    document.getElementById("form-registro").addEventListener("submit", async (e) => {
        e.preventDefault();
        const form = new FormData(e.target);
        if (form.get("clave") !== form.get("confirmar")) {
            aviso(avisoEl, "Las contraseñas no coinciden.");
            return;
        }
        const boton = e.target.querySelector("button");
        boton.disabled = true;
        try {
            const s = await api("/auth/registro", {
                method: "POST",
                body: JSON.stringify({
                    nombre: form.get("nombre").trim(),
                    email: form.get("email").trim(),
                    clave: form.get("clave"),
                }),
            });
            sesion.guardar(s);
            irA("agenda.html?bienvenida=1");
        } catch (err) {
            aviso(avisoEl, err.message);
            boton.disabled = false;
        }
    });
})();
