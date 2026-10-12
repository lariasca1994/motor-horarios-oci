# 📘 Manual de usuario · Motor de Horarios

Guía para usar la plataforma paso a paso: qué significa cada campo, qué datos se ingresan y qué
protege la plataforma. Para la parte técnica vuelve al [README](../README.md).

**Demo:** [motor-horarios-oci.vercel.app](https://motor-horarios-oci.vercel.app)

## Contenido

1. [En pocas palabras](#1-en-pocas-palabras)
2. [Antes de empezar](#2-antes-de-empezar)
3. [Paso a paso](#3-paso-a-paso)
4. [Qué información ingresas y dónde queda](#4-qué-información-ingresas-y-dónde-queda)
5. [Seguridad: qué se garantiza](#5-seguridad-qué-se-garantiza)
6. [Límites y recomendaciones](#6-límites-y-recomendaciones)
7. [Preguntas frecuentes](#7-preguntas-frecuentes)

---

## 1. En pocas palabras

Cada persona registra una sola vez su horario laboral y sus bloques ocupados o preferidos. Al
proponer una reunión, el motor cruza las agendas de los participantes y sugiere **los 3 mejores
horarios** en que todos están libres. Cada participante recibe las sugerencias por correo.

## 2. Antes de empezar

- Solo necesitas un navegador.
- El servidor se duerme sin uso: la primera carga puede tardar **unos 50 segundos**.
- Las cuentas nuevas empiezan con horario de **8:00 a 18:00, de lunes a viernes**.

## 3. Paso a paso

### 3.1 Crear una cuenta

![Formulario de registro con sus campos numerados](img/manual/01-registro.png)

| # | Campo | Qué escribir | Reglas |
|:-:|---|---|---|
| 1 | Nombre | Tu nombre; es lo que ven los demás al invitarte | Máximo 100 caracteres |
| 2 | Correo | Donde recibirás las invitaciones | Formato válido y único |
| 3 | Contraseña | Tu contraseña | Entre **10 y 128 caracteres** |
| 4 | Confirmar contraseña | La misma contraseña | Debe coincidir con el campo 3 |
| 5 | Crear cuenta | Botón | Crea la cuenta y te deja con la sesión iniciada |

### 3.2 Iniciar sesión

![Formulario de inicio de sesión](img/manual/02-login.png)

| # | Campo | Qué escribir |
|:-:|---|---|
| 1 | Correo | El correo de tu cuenta |
| 2 | Contraseña | Tu contraseña |
| 3 | Ingresar | Abre **Mis reuniones**. La sesión dura 12 horas |

Tras **5 intentos fallidos en 15 minutos**, ese correo queda bloqueado temporalmente.

### 3.3 Mi agenda

![Agenda con horario laboral y formulario de bloques](img/manual/03-agenda.png)

**Horario laboral:** el motor nunca propone reuniones fuera de él.

| # | Campo | Qué escribir |
|:-:|---|---|
| 1 | Desde | Hora en que empiezas a trabajar |
| 2 | Hasta | Hora en que terminas |
| 3 | Días laborables | Los días en que se te pueden agendar reuniones |
| 4 | Guardar horario | Guarda los tres campos anteriores |

**Agregar bloque:** franjas que se repiten en tu semana.

| # | Campo | Qué escribir |
|:-:|---|---|
| 5 | Descripción | Por ejemplo "Daily", "almuerzo" o "clase" |
| 6 | Tipo | **Ocupado** (nunca agendar aquí) o **Preferido** (mejor si es aquí) |
| 7 | Fecha (primera vez) | Día en que ocurre por primera vez |
| 8 | Hora inicio | Inicio de la franja (en pasos de 15 minutos) |
| 9 | Hora fin | Fin de la franja |
| 10 | Repetición | No se repite, Todos los días, Días laborables o Semanal (con los días que elijas) |
| 11 | Repetir hasta | Opcional: fecha en que deja de repetirse |
| 12 | Agregar bloque | Guarda el bloque y lo muestra en la tabla **Bloques de agenda** |

### 3.4 Proponer una reunión

![Formulario para proponer una reunión](img/manual/04-reuniones.png)

| # | Campo | Qué escribir | Reglas |
|:-:|---|---|---|
| 1 | Título | Tema de la reunión | Máximo 200 caracteres |
| 2 | Duración (minutos) | Cuánto dura | Entre 15 y 480, en pasos de 15 |
| 3 | Buscar desde | Primer momento posible | Fecha y hora |
| 4 | Hasta | Último momento posible | Fecha y hora |
| 5 | Participantes | Las personas invitadas; **recibirán el correo** | Marca una o varias |
| 6 | Buscar huecos | Botón | Cruza las agendas y propone los 3 mejores horarios |

A la derecha aparece la lista de tus reuniones (oculta en la captura para proteger los datos de
otras cuentas). En cada tarjeta, el organizador puede **confirmar** un horario, **recalcular** las
sugerencias o **cancelar** la reunión.

### 3.5 Cambiar la contraseña

![Formulario de cambio de contraseña](img/manual/05-clave.png)

| # | Campo | Qué escribir |
|:-:|---|---|
| 1 | Contraseña actual | La que usas hoy |
| 2 | Nueva contraseña | Entre 10 y 128 caracteres |
| 3 | Confirmar | La nueva contraseña otra vez |
| 4 | Guardar | Aplica el cambio |

## 4. Qué información ingresas y dónde queda

| Dato | Para qué se usa | Dónde se guarda | Quién lo ve |
|---|---|---|---|
| Nombre | Que te puedan invitar | MySQL HeatWave en Oracle Cloud | Todas las cuentas activas |
| Correo | Iniciar sesión y recibir invitaciones | MySQL HeatWave | **Solo tú y el administrador** |
| Contraseña | Iniciar sesión | MySQL HeatWave, **solo su huella scrypt** | Nadie: no se puede leer ni recuperar |
| Horario laboral y bloques | Calcular huecos libres | MySQL HeatWave | Tú y el administrador; el motor los usa sin mostrarlos a otros |
| Reuniones | Coordinar | MySQL HeatWave | El organizador, los participantes y el administrador |
| Sesión | Mantenerte conectado | `localStorage` de tu navegador | Solo tu navegador; vence a las 12 horas |

## 5. Seguridad: qué se garantiza

Comprobado en el código del proyecto (`functions/api/auth.py`, `functions/api/main.py`,
`functions/api/db.py`):

- **Contraseñas con scrypt** y sal aleatoria; la comparación se hace en tiempo constante.
- **Sesión con token firmado (HMAC-SHA256)** que vence a las 12 horas; en cada petición se revisa
  que la cuenta siga activa.
- **Bloqueo por intentos:** 5 contraseñas erradas en 15 minutos bloquean temporalmente ese correo.
- **Tu agenda es tuya:** solo tú (o el administrador) puedes ver o cambiar tu horario y tus bloques.
- **Reuniones privadas:** solo el organizador, los participantes y el administrador ven una
  reunión; solo el organizador puede confirmarla, recalcularla o cancelarla.
- **Correos ocultos:** las demás cuentas ven tu nombre, nunca tu correo.
- **Roles en el servidor:** crear, editar o borrar cuentas desde la administración es exclusivo
  del rol admin.
- **Conexión cifrada a la base** (TLS siempre activo) y consultas parametrizadas, sin concatenar
  texto del usuario en el SQL.
- **CORS restringido** a la web oficial y secretos (base, clave de firma, SMTP) en variables de
  entorno, nunca en el repositorio.

## 6. Límites y recomendaciones

Proyecto en desarrollo, pensado como demo de portafolio:

- No hay recuperación de contraseña por correo: guárdala en un gestor.
- El token vive en `localStorage`: usa **Salir** en equipos compartidos.
- Tu nombre es visible para todas las cuentas activas; usa un nombre que no te moleste mostrar.

## 7. Preguntas frecuentes

**¿Por qué el motor no encontró huecos?** No hay una franja de la duración pedida en la que todos
estén dentro de su horario laboral y sin bloques ocupados. Amplía el rango de fechas o reduce la
duración.

**¿Qué diferencia hay entre Ocupado y Preferido?** *Ocupado* descarta esa franja. *Preferido* la
hace más atractiva cuando hay varias opciones.

**¿Los participantes tienen que aceptar en la aplicación?** No. Reciben las sugerencias por correo
y el organizador confirma el horario desde la aplicación.
