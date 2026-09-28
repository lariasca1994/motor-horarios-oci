-- Datos de ejemplo para desarrollo local. No ejecutar en producción.

INSERT INTO usuarios (id, nombre, email) VALUES
    (1, 'Ana Gómez',    'ana@example.com'),
    (2, 'Bruno Díaz',   'bruno@example.com'),
    (3, 'Carla Ruiz',   'carla@example.com');

INSERT INTO reglas_usuario (usuario_id, no_antes_de, no_despues_de, dias_laborables) VALUES
    (1, 8,  17, '0,1,2,3,4'),
    (2, 9,  18, '0,1,2,3,4'),
    (3, 10, 16, '0,1,2,3');     -- Carla no trabaja los viernes

INSERT INTO disponibilidad (usuario_id, inicio, fin, tipo, rrule, descripcion) VALUES
    -- Daily de todo el equipo, lunes a viernes 9:00-9:30
    (1, '2026-01-05 09:00:00', '2026-01-05 09:30:00', 'ocupado', 'FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR', 'Daily'),
    (2, '2026-01-05 09:00:00', '2026-01-05 09:30:00', 'ocupado', 'FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR', 'Daily'),
    (3, '2026-01-05 09:00:00', '2026-01-05 09:30:00', 'ocupado', 'FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR', 'Daily'),
    -- Almuerzo de Bruno
    (2, '2026-01-05 12:00:00', '2026-01-05 13:00:00', 'ocupado', 'FREQ=DAILY', 'Almuerzo'),
    -- Ana prefiere reuniones los martes y jueves en la tarde
    (1, '2026-01-06 14:00:00', '2026-01-06 17:00:00', 'preferido', 'FREQ=WEEKLY;BYDAY=TU,TH', 'Bloque de reuniones'),
    -- Carla tiene clase los miércoles
    (3, '2026-01-07 10:00:00', '2026-01-07 12:00:00', 'ocupado', 'FREQ=WEEKLY;BYDAY=WE', 'Clase');
