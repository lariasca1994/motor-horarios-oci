-- Migración: horario laboral 8:00-18:00 por defecto para personas nuevas y
-- para las que quedaron sin límites (antes se creaban con NULL = 24 horas).
ALTER TABLE reglas_usuario
    ALTER COLUMN no_antes_de SET DEFAULT 8,
    ALTER COLUMN no_despues_de SET DEFAULT 18;

UPDATE reglas_usuario SET no_antes_de = 8
 WHERE no_antes_de IS NULL AND (no_despues_de IS NULL OR no_despues_de > 8);
UPDATE reglas_usuario SET no_despues_de = 18
 WHERE no_despues_de IS NULL AND no_antes_de < 18;
