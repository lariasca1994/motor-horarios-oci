"use strict";
(function () {
    exigirSesion();
    const avisoEl = document.getElementById("aviso");

    document.getElementById("form-clave").addEventListener("submit", async (e) => {
        e.preventDefault();
        const form = new FormData(e.target);
        if (form.get("nueva") !== form.get("confirmar")) {
            aviso(avisoEl, "Las contraseñas nuevas no coinciden.");
            return;
        }
        try {
            await api("/auth/clave", {
                method: "POST",
                body: JSON.stringify({ actual: form.get("actual"), nueva: form.get("nueva") }),
            });
            e.target.reset();
            aviso(avisoEl, "Contraseña actualizada.", "ok");
        } catch (err) {
            aviso(avisoEl, err.message);
        }
    });
})();
