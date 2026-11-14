/* Efectos del Coordinador de reuniones (web y PWA). Sin dependencias; si algo falla, la página
   sigue funcionando igual. No cambia ninguna llamada a la API ni la lógica de cada página:
   - onda al tocar los botones, temblor del botón de envío ante un error y barra de "enviando";
   - menú lateral (indicador con haz de luz, fondo que sigue al ratón, compacto con etiqueta) y
     hoja "Más" del teléfono;
   - dirección del cambio de página (View Transitions entre documentos);
   - segundo factor: seis casillas sobre el mismo campo #codigo, candado y anillo de tiempo;
   - registro del service worker (PWA). */
(function () {
    "use strict";
    var raiz = document.documentElement;
    var reducir = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    function leer(c) { try { return sessionStorage.getItem(c); } catch (e) { return null; } }
    function guardar(c, v) { try { sessionStorage.setItem(c, v); } catch (e) { /* sin almacenamiento */ } }

    /* ───────── Orden de las pantallas (para la dirección del deslizamiento) ───────── */
    var ORDEN = { login: 0, "": 0, index: 0, recuperar: 1, restablecer: 2, registro: 1, verificacion: 1,
        reuniones: 10, agenda: 11, usuarios: 12, clave: 13, seguridad: 14 };
    function pagina(url) {
        try { return new URL(url, location.href).pathname.split("/").pop().replace(/\.html$/, ""); } catch (e) { return ""; }
    }
    window.addEventListener("pagereveal", function (e) {
        // Si la otra página no participa, la transición se cancela: no es un error.
        if (e.viewTransition) { e.viewTransition.ready.catch(function () {}); e.viewTransition.finished.catch(function () {}); }
        if (!e.viewTransition || !window.navigation || !navigation.activation || !navigation.activation.from) return;
        var desde = ORDEN[pagina(navigation.activation.from.url)];
        var hacia = ORDEN[pagina(location.href)];
        if (desde === undefined || hacia === undefined) return;
        if (hacia < desde) e.viewTransition.types.add("atras");
    });

    /* ───────── Botones ───────── */
    function onda(e) {
        var b = e.target.closest && e.target.closest(".boton, .menu-op");
        if (!b || reducir || b.disabled) return;
        var r = b.getBoundingClientRect();
        var o = document.createElement("span");
        o.className = b.classList.contains("menu-op") || b.classList.contains("boton-secundario") ? "onda suave" : "onda";
        o.style.setProperty("--x", (e.clientX - r.left) + "px");
        o.style.setProperty("--y", (e.clientY - r.top) + "px");
        o.style.setProperty("--d", Math.max(r.width, r.height) * 2.2 + "px");
        b.appendChild(o);
        o.addEventListener("animationend", function () { o.remove(); });
    }

    function temblar(el) {
        if (!el || reducir) return;
        el.classList.remove("temblor");
        void el.offsetWidth;
        el.classList.add("temblor");
        el.addEventListener("animationend", function () { el.classList.remove("temblor"); }, { once: true });
    }

    // Los formularios se envían con fetch desde cada página: mientras su botón está
    // deshabilitado después del envío, una barra lo recorre. Se quita al habilitarse.
    function alEnviar(e) {
        var f = e.target;
        if (!(f instanceof HTMLFormElement)) return;
        f.setAttribute("data-enviando", "");
        setTimeout(function () { f.removeAttribute("data-enviando"); }, 30000);
    }
    new MutationObserver(function (cambios) {
        cambios.forEach(function (c) {
            var el = c.target;
            if (c.attributeName === "disabled" && !el.disabled && el.form) el.form.removeAttribute("data-enviando");
            // Un aviso de error que aparece hace temblar el botón de envío del formulario cercano.
            if (el.classList && el.classList.contains("aviso") && el.classList.contains("error") && !el.hidden) {
                var zona = el.closest("section, main, .tarjeta") || document;
                var f = zona.querySelector("form[data-enviando]") || zona.querySelector("form");
                if (f) { f.removeAttribute("data-enviando"); temblar(f.querySelector('[type="submit"]')); }
            }
        });
    }).observe(document.documentElement, { subtree: true, attributes: true, attributeFilter: ["disabled", "hidden", "class"] });

    /* ───────── Menú lateral y hoja "Más" ───────── */
    function ubicar(capa, op) {
        capa.style.transform = "translate(" + op.offsetLeft + "px," + op.offsetTop + "px)";
        capa.style.width = op.offsetWidth + "px";
        capa.style.height = op.offsetHeight + "px";
    }

    function iniciarMenu() {
        var nav = document.querySelector("body.con-menu .nav-principal");
        if (!nav) return;
        var ind = nav.querySelector(".menu-ind");
        var hov = nav.querySelector(".menu-hov");
        var etiqueta = document.querySelector(".menu-etiqueta");
        var ops = Array.prototype.slice.call(nav.querySelectorAll(".menu-op"));
        var activa = nav.querySelector('.menu-op[aria-current="page"]');

        try { raiz.setAttribute("data-menu", localStorage.getItem("motorhorarios-menu") === "compacto" ? "compacto" : "extendido"); } catch (e) { /* nada */ }

        function visible(op) { return op && op.offsetParent !== null; }
        function colocar(sinAnim) {
            var a = nav.querySelector('.menu-op[aria-current="page"]');
            if (!visible(a)) a = nav.querySelector(".menu-mas.contiene-actual");
            if (!visible(a)) { ind.style.opacity = "0"; return; }
            ind.style.opacity = "1";
            if (sinAnim) nav.classList.add("menu-sin-anim");
            ubicar(ind, a);
            if (sinAnim) requestAnimationFrame(function () { requestAnimationFrame(function () { nav.classList.remove("menu-sin-anim"); }); });
        }

        // El indicador parte de la opción de la pantalla anterior y se desliza a la actual.
        var previo = leer("motorhorarios-menu-op");
        var origen = previo && ops.filter(function (o) { return o.getAttribute("href") === previo; })[0];
        if (!reducir && visible(origen) && origen !== activa && visible(activa)) {
            nav.classList.add("menu-sin-anim");
            ubicar(ind, origen);
            requestAnimationFrame(function () { requestAnimationFrame(function () { nav.classList.remove("menu-sin-anim"); colocar(false); }); });
        } else {
            colocar(true);
        }
        if (activa) guardar("motorhorarios-menu-op", activa.getAttribute("href"));
        if (!leer("motorhorarios-menu-visto")) {
            raiz.classList.add("menu-primera");
            guardar("motorhorarios-menu-visto", "1");
            setTimeout(function () { raiz.classList.remove("menu-primera"); }, 1200);
        }

        nav.addEventListener("mouseover", function (e) {
            var op = e.target.closest(".menu-op");
            if (!op || !nav.contains(op) || op.closest(".menu-pie")) return;
            if (!hov.classList.contains("listo")) {
                nav.classList.add("menu-sin-anim");
                ubicar(hov, op);
                void hov.offsetWidth;
                nav.classList.remove("menu-sin-anim");
                hov.classList.add("listo");
            }
            ubicar(hov, op);
        });
        nav.addEventListener("mouseleave", function () { hov.classList.remove("listo"); });

        // Etiqueta con el nombre de la opción cuando el menú está compacto.
        if (etiqueta) {
            nav.addEventListener("mouseover", function (e) {
                var op = e.target.closest(".menu-op");
                if (!op) return;
                var r = op.getBoundingClientRect();
                etiqueta.textContent = (op.querySelector(".texto-largo") || op.querySelector(".menu-texto") || op).textContent.trim();
                etiqueta.style.top = (r.top + r.height / 2 - etiqueta.offsetHeight / 2) + "px";
                etiqueta.classList.add("visible");
            });
            nav.addEventListener("mouseleave", function () { etiqueta.classList.remove("visible"); });
        }

        var alternar = nav.querySelector(".menu-alternar");
        function textoAlternar() {
            var compacto = raiz.getAttribute("data-menu") === "compacto";
            alternar.setAttribute("aria-expanded", String(!compacto));
            alternar.querySelector(".menu-texto").textContent = compacto ? "Extender menú" : "Compactar menú";
        }
        if (alternar) {
            textoAlternar();
            alternar.addEventListener("click", function () {
                var compacto = raiz.getAttribute("data-menu") !== "compacto";
                raiz.setAttribute("data-menu", compacto ? "compacto" : "extendido");
                textoAlternar();
                try { localStorage.setItem("motorhorarios-menu", compacto ? "compacto" : "extendido"); } catch (e) { /* nada */ }
            });
        }
        if (window.ResizeObserver) new ResizeObserver(function () { colocar(true); }).observe(nav);
        window.addEventListener("resize", function () { colocar(true); });
        requestAnimationFrame(function () { raiz.classList.add("menu-listo"); });

        // Al elegir otra sección, el haz se desliza antes de cambiar de página.
        ops.forEach(function (op) {
            if (op.tagName !== "A" || op.getAttribute("href") === "#") return;
            op.addEventListener("click", function (e) {
                if (e.ctrlKey || e.metaKey || e.shiftKey || e.button !== 0 || op === activa) return;
                nav.querySelectorAll('[aria-current="page"]').forEach(function (x) { x.removeAttribute("aria-current"); });
                op.setAttribute("aria-current", "page");
                colocar(false);
            });
        });

        // Hoja "Más" del teléfono. Elegir una opción la cierra en el acto (la hoja modal deja
        // inerte el resto de la página mientras baja).
        var hoja = document.querySelector(".hoja-mas");
        var mas = nav.querySelector(".menu-mas");
        if (hoja && mas && typeof hoja.showModal === "function") {
            var cerrar = function () {
                if (reducir) { hoja.close(); return; }
                hoja.classList.add("cerrando");
                setTimeout(function () { hoja.classList.remove("cerrando"); hoja.close(); }, 200);
            };
            mas.addEventListener("click", function () { hoja.showModal(); mas.setAttribute("aria-expanded", "true"); });
            hoja.addEventListener("close", function () { mas.setAttribute("aria-expanded", "false"); });
            hoja.addEventListener("click", function (e) {
                if (e.target === hoja) cerrar();
                else if (e.target.closest("a")) hoja.close();
            });
            hoja.addEventListener("cancel", function (e) { e.preventDefault(); cerrar(); });
        }
    }

    /* ───────── Segundo factor: casillas, candado y anillo ───────── */
    var SVG_CANDADO = '<svg viewBox="0 0 48 48" aria-hidden="true"><path class="arco" d="M15 22v-7a9 9 0 0 1 18 0v7"/><rect class="cuerpo" x="9" y="21" width="30" height="21" rx="6"/><circle class="ojo" cx="24" cy="31.5" r="3.4"/></svg>';

    function iniciarCodigo() {
        var input = document.getElementById("codigo");
        if (!input || input.closest(".casillas-codigo")) return;
        var caja = document.createElement("div");
        caja.className = "casillas-codigo";
        input.parentNode.insertBefore(caja, input);
        caja.appendChild(input);
        var vista = document.createElement("div");
        vista.className = "casillas-vista";
        vista.setAttribute("aria-hidden", "true");
        vista.innerHTML = "<span></span><span></span><span></span><span></span><span></span><span></span>";
        caja.appendChild(vista);
        var casillas = vista.children;
        var anterior = "";
        function pintar() {
            var digitos = input.value.replace(/\D/g, "").slice(0, 6);
            var foco = document.activeElement === input;
            for (var i = 0; i < 6; i++) {
                var c = casillas[i];
                c.textContent = digitos[i] || "";
                c.classList.toggle("llena", !!digitos[i]);
                c.classList.toggle("activa", foco && i === Math.min(digitos.length, 5));
                if (digitos.length > anterior.length && i === digitos.length - 1 && !reducir) {
                    c.classList.remove("pulso"); void c.offsetWidth; c.classList.add("pulso");
                }
            }
            anterior = digitos;
        }
        ["input", "focus", "blur", "keyup"].forEach(function (ev) { input.addEventListener(ev, pintar); });
        // La página vacía el campo por código al cambiar de paso: se revisa con frecuencia.
        setInterval(function () { if (input.value.replace(/\D/g, "").slice(0, 6) !== anterior) pintar(); }, 250);
        pintar();

        // Anillo: con la app, cuándo muestra un código nuevo (cada 30 s); con el correo, cuánto
        // le queda al código según el texto de la página ("Vence en N minutos").
        var anillo = document.createElement("p");
        anillo.className = "anillo";
        anillo.hidden = true;
        anillo.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><circle class="anillo-fondo" cx="12" cy="12" r="9"/><circle class="anillo-valor" cx="12" cy="12" r="9" pathLength="1"/></svg><span></span>';
        caja.parentNode.insertBefore(anillo, caja.nextSibling);
        var valor = anillo.querySelector(".anillo-valor");
        var texto = anillo.querySelector("span");
        var subtitulo = document.getElementById("subtitulo");
        var modo = null, inicio = 0, minutos = 0;
        function leerModo() {
            var s = subtitulo ? subtitulo.textContent : "";
            var m = s.match(/Vence en (\d+) minutos/);
            if (m) { modo = "correo"; minutos = parseInt(m[1], 10); inicio = Date.now(); }
            else if (/app autenticadora/i.test(s) && !/Configura/i.test(s)) { modo = "app"; }
            else modo = null;
        }
        function tic() {
            if (!modo) { anillo.hidden = true; return; }
            anillo.hidden = false;
            var resto, total;
            if (modo === "app") {
                total = 30;
                resto = 30 - (Math.floor(Date.now() / 1000) % 30);
                texto.textContent = "Tu app muestra un código nuevo en " + resto + " s";
            } else {
                total = minutos * 60;
                resto = Math.max(0, Math.round((inicio + total * 1000 - Date.now()) / 1000));
                texto.textContent = resto ? "El código vence en " + Math.floor(resto / 60) + ":" + String(resto % 60).padStart(2, "0") : "El código venció. Pide otro.";
            }
            valor.style.strokeDashoffset = 1 - resto / total;
            anillo.classList.toggle("urgente", resto <= (modo === "app" ? 5 : 60));
        }
        if (subtitulo) new MutationObserver(function () { leerModo(); tic(); }).observe(subtitulo, { childList: true, characterData: true, subtree: true });
        leerModo();
        tic();
        setInterval(tic, 1000);

        // Candado sobre el título: se abre con el código correcto y se sacude con uno equivocado.
        var tarjeta = input.closest(".tarjeta-acceso");
        if (!tarjeta) return;
        var candado = document.createElement("span");
        candado.className = "candado";
        candado.setAttribute("aria-hidden", "true");
        candado.setAttribute("data-estado", "normal");
        candado.innerHTML = SVG_CANDADO;
        tarjeta.insertBefore(candado, tarjeta.firstChild);
        var form = input.form;
        var aviso = document.getElementById("aviso");
        if (form) form.addEventListener("submit", function () { candado.setAttribute("data-estado", "verificando"); });
        if (aviso) {
            new MutationObserver(function () {
                if (candado.getAttribute("data-estado") !== "verificando") return;
                if (aviso.hidden || !aviso.classList.contains("error")) return;
                candado.setAttribute("data-estado", "error");
                caja.classList.remove("error"); void caja.offsetWidth; caja.classList.add("error");
                setTimeout(function () { candado.setAttribute("data-estado", "normal"); caja.classList.remove("error"); }, 700);
            }).observe(aviso, { attributes: true, childList: true, characterData: true, subtree: true });
        }
        // Al terminar con éxito la página llama a irA(): el candado se abre un momento antes.
        if (typeof window.irA === "function") {
            var irOriginal = window.irA;
            window.irA = function (destino) {
                if (candado.getAttribute("data-estado") === "verificando" && !reducir) {
                    candado.setAttribute("data-estado", "abierto");
                    setTimeout(function () { irOriginal(destino); }, 450);
                    return;
                }
                irOriginal(destino);
            };
        }
    }

    /* ───────── Bloques escalonados ───────── */
    function escalonar() {
        document.querySelectorAll(".lista-tarjetas").forEach(function (lista) {
            var poner = function () {
                Array.prototype.forEach.call(lista.children, function (h, i) { h.style.setProperty("--i", Math.min(i, 8)); });
            };
            poner();
            new MutationObserver(poner).observe(lista, { childList: true });
        });
    }

    function iniciar() {
        iniciarMenu();
        iniciarCodigo();
        escalonar();
    }

    document.addEventListener("pointerdown", onda, { passive: true });
    document.addEventListener("submit", alEnviar, true);
    // pintarNav (comun.js) también corre en DOMContentLoaded y se registró antes que este archivo.
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", iniciar);
    else iniciar();

    /* ───────── PWA ───────── */
    if ("serviceWorker" in navigator && window.isSecureContext) {
        window.addEventListener("load", function () { navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(function () {}); });
    }
})();
