"use strict";
(function () {
    const yo = exigirSesion({ admin: true });
    const $ = (sel) => document.querySelector(sel);
    const avisoEl = document.getElementById("aviso");
    let usuarios = [];
    let editando = null; // id de la persona cuyo nombre se está editando

    function fila(u) {
        const esYo = u.id === yo.id;
        const celdaNombre = editando === u.id
            ? `<form class="editar-nombre" data-editar="${u.id}">
                   <input type="text" name="nombre" value="${esc(u.nombre)}" maxlength="100" required aria-label="Nuevo nombre">
                   <button type="submit" class="boton boton-chico">Guardar</button>
                   <button type="button" class="enlace-boton" data-accion="cancelar-edicion">Cancelar</button>
               </form>`
            : `${esc(u.nombre)}${esYo ? ' <span class="texto-suave">(tú)</span>' : ""}`;
        return `
            <tr>
                <td>${celdaNombre}</td>
                <td>${esc(u.email)}</td>
                <td><span class="estado-usuario ${u.activo ? "estado-usuario-activo" : "estado-usuario-suspendido"}">
                    ${u.activo ? "Activo" : "Inactivo"}</span></td>
                <td>
                    <div class="acciones">
                        ${editando === u.id ? "" : `<button class="enlace-boton" data-accion="editar" data-id="${u.id}">Editar nombre</button>`}
                        <a href="agenda.html?usuario=${u.id}">Agenda</a>
                        ${esYo ? "" : `
                            <button class="enlace-boton" data-accion="activo" data-id="${u.id}" data-valor="${u.activo ? "0" : "1"}">
                                ${u.activo ? "Desactivar" : "Activar"}</button>
                            <button class="enlace-boton enlace-boton-peligro" data-accion="eliminar" data-id="${u.id}">Eliminar</button>`}
                    </div>
                </td>
            </tr>`;
    }

    function pintar() {
        $("#usuarios").innerHTML = usuarios.map(fila).join("");
        $('#usuarios form[data-editar] input')?.focus();
    }

    async function cargar() {
        usuarios = await api("/usuarios");
        pintar();
    }

    $("#form-usuario").addEventListener("submit", async (e) => {
        e.preventDefault();
        const form = new FormData(e.target);
        try {
            const u = await api("/usuarios", {
                method: "POST",
                body: JSON.stringify({
                    nombre: form.get("nombre").trim(),
                    email: form.get("email").trim(),
                    clave: form.get("clave"),
                }),
            });
            e.target.reset();
            aviso(avisoEl, `Usuario ${u.nombre} creado.`, "ok");
            await cargar();
        } catch (err) {
            aviso(avisoEl, err.message);
        }
    });

    // Guardar nombre editado
    $("#usuarios").addEventListener("submit", async (e) => {
        const form = e.target.closest("form[data-editar]");
        if (!form) return;
        e.preventDefault();
        const id = Number(form.dataset.editar);
        const nombre = new FormData(form).get("nombre").trim();
        try {
            await api(`/usuarios/${id}`, { method: "PATCH", body: JSON.stringify({ nombre }) });
            editando = null;
            aviso(avisoEl, "Nombre actualizado.", "ok");
            await cargar();
        } catch (err) {
            aviso(avisoEl, err.message);
        }
    });

    $("#usuarios").addEventListener("click", async (e) => {
        const boton = e.target.closest("button[data-accion]");
        if (!boton) return;
        const { accion } = boton.dataset;
        const id = Number(boton.dataset.id);
        if (accion === "editar") { editando = id; return pintar(); }
        if (accion === "cancelar-edicion") { editando = null; return pintar(); }
        if (accion === "eliminar" && !confirmarEnDosClics(boton)) return;
        try {
            if (accion === "eliminar") {
                await api(`/usuarios/${id}`, { method: "DELETE" });
                aviso(avisoEl, "Usuario eliminado.", "ok");
            } else if (accion === "activo") {
                await api(`/usuarios/${id}`, {
                    method: "PATCH",
                    body: JSON.stringify({ activo: boton.dataset.valor === "1" }),
                });
            }
            await cargar();
        } catch (err) {
            aviso(avisoEl, err.message);
        }
    });

    $("#usuarios").addEventListener("keydown", (e) => {
        if (e.key === "Escape" && editando !== null) { editando = null; pintar(); }
    });

    cargar().catch((err) => aviso(avisoEl, err.message));
})();
