"use strict";
// Con sesión iniciada, el botón principal lleva directo a las reuniones.
if (sesion.usuario) {
    document.getElementById("cta").innerHTML = '<a class="boton" href="reuniones.html">Ir a mis reuniones</a>';
}
