"use strict";
(function () {
    const params = new URLSearchParams(location.search);
    const avisoEl = document.getElementById("aviso");
    if (sesion.usuario) irA("reuniones.html");
    if (params.get("vencida")) aviso(avisoEl, "Tu sesión venció, ingresa de nuevo.");

    document.getElementById("form-login").addEventListener("submit", async (e) => {
        e.preventDefault();
        const form = new FormData(e.target);
        const boton = e.target.querySelector("button");
        boton.disabled = true;
        try {
            const s = await api("/auth/login", {
                method: "POST",
                body: JSON.stringify({ email: form.get("email").trim(), clave: form.get("clave") }),
            });
            sesion.guardar(s);
            // Solo se vuelve a páginas propias (evita redirecciones abiertas)
            const volver = params.get("volver");
            irA(volver && /^[a-z]+\.html(\?[\w=&%-]*)?$/.test(volver) ? volver : "reuniones.html");
        } catch (err) {
            aviso(avisoEl, err.message);
            boton.disabled = false;
        }
    });
})();
