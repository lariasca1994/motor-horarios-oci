"use strict";
(function () {
    // El token llega en el fragmento (#...): no viaja al servidor de la página ni queda en registros.
    const token = decodeURIComponent(location.hash.slice(1));
    history.replaceState(null, "", location.pathname);
    const avisoEl = document.getElementById("aviso");
    const form = document.getElementById("form-restablecer");
    if (!token) {
        aviso(avisoEl, "El enlace no es válido. Pide uno nuevo desde «¿Olvidaste tu contraseña?».");
        form.hidden = true;
        return;
    }
    form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const datos = new FormData(form);
        if (datos.get("nueva") !== datos.get("confirmar")) {
            aviso(avisoEl, "Las contraseñas nuevas no coinciden.");
            return;
        }
        try {
            await api("/auth/restablecer", {
                method: "POST",
                body: JSON.stringify({ token, nueva: datos.get("nueva") }),
            });
            form.hidden = true;
            aviso(avisoEl, "Tu contraseña quedó actualizada. Ya puedes ingresar.", "ok");
        } catch (err) {
            aviso(avisoEl, err.message);
        }
    });
})();
