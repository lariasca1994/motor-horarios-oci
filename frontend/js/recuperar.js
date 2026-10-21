"use strict";
(function () {
    // Página pública: no exige sesión. La respuesta es la misma exista o no la cuenta.
    const avisoEl = document.getElementById("aviso");
    document.getElementById("form-recuperar").addEventListener("submit", async (e) => {
        e.preventDefault();
        const boton = e.target.querySelector("button");
        boton.disabled = true;
        try {
            await api("/auth/recuperar", {
                method: "POST",
                body: JSON.stringify({ email: new FormData(e.target).get("email") }),
            });
            aviso(avisoEl, "Si el correo pertenece a una cuenta, te enviamos un enlace para crear una contraseña nueva. Revisa tu bandeja (y la carpeta de spam).", "ok");
            e.target.reset();
        } catch (err) {
            aviso(avisoEl, err.message);
        } finally {
            boton.disabled = false;
        }
    });
})();
