-- Esquema del Motor de Horarios (MySQL 8.0+)
-- Todas las fechas se guardan como DATETIME sin zona horaria y se interpretan
-- en la zona de la aplicación (America/Bogota por defecto).

SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS usuarios (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    nombre        VARCHAR(100) NOT NULL,
    email         VARCHAR(255) NOT NULL UNIQUE,
    rol           ENUM('admin', 'usuario') NOT NULL DEFAULT 'usuario',
    password_hash VARCHAR(255) NULL,       -- NULL = persona sin acceso a la web
    activo        BOOLEAN NOT NULL DEFAULT TRUE,
    creado_en     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Reglas personales de cada usuario (una fila por usuario).
CREATE TABLE IF NOT EXISTS reglas_usuario (
    usuario_id      INT PRIMARY KEY,
    no_antes_de     TINYINT UNSIGNED NULL DEFAULT 8,   -- hora 0-23 (NULL = sin límite)
    no_despues_de   TINYINT UNSIGNED NULL DEFAULT 18,  -- hora 1-24 (NULL = sin límite)
    dias_laborables VARCHAR(20) NOT NULL DEFAULT '0,1,2,3,4',  -- 0=lunes … 6=domingo
    CONSTRAINT fk_reglas_usuario FOREIGN KEY (usuario_id)
        REFERENCES usuarios(id) ON DELETE CASCADE,
    CONSTRAINT chk_horas CHECK (
        (no_antes_de IS NULL OR no_antes_de <= 23) AND
        (no_despues_de IS NULL OR no_despues_de <= 24)
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Bloques de calendario: 'ocupado' impide agendar, 'preferido' suma puntaje.
-- Si rrule no es NULL, inicio/fin son la primera ocurrencia (RFC 5545).
CREATE TABLE IF NOT EXISTS disponibilidad (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    usuario_id  INT NOT NULL,
    inicio      DATETIME NOT NULL,
    fin         DATETIME NOT NULL,
    tipo        ENUM('ocupado', 'preferido') NOT NULL DEFAULT 'ocupado',
    rrule       VARCHAR(255) NULL,
    descripcion VARCHAR(255) NULL,
    CONSTRAINT fk_disp_usuario FOREIGN KEY (usuario_id)
        REFERENCES usuarios(id) ON DELETE CASCADE,
    CONSTRAINT chk_disp_rango CHECK (fin > inicio),
    INDEX idx_disp_usuario_inicio (usuario_id, inicio)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS reuniones (
    id                INT AUTO_INCREMENT PRIMARY KEY,
    titulo            VARCHAR(200) NOT NULL,
    duracion_min      SMALLINT UNSIGNED NOT NULL,
    ventana_inicio    DATETIME NOT NULL,
    ventana_fin       DATETIME NOT NULL,
    organizador_id    INT NOT NULL,
    estado            ENUM('pendiente', 'con_sugerencias', 'sin_huecos',
                           'confirmada', 'cancelada') NOT NULL DEFAULT 'pendiente',
    inicio_confirmado DATETIME NULL,
    creado_en         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_reunion_organizador FOREIGN KEY (organizador_id)
        REFERENCES usuarios(id),
    CONSTRAINT chk_reunion_ventana CHECK (ventana_fin > ventana_inicio),
    INDEX idx_reuniones_estado (estado)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS reunion_participantes (
    reunion_id  INT NOT NULL,
    usuario_id  INT NOT NULL,
    PRIMARY KEY (reunion_id, usuario_id),
    CONSTRAINT fk_part_reunion FOREIGN KEY (reunion_id)
        REFERENCES reuniones(id) ON DELETE CASCADE,
    CONSTRAINT fk_part_usuario FOREIGN KEY (usuario_id)
        REFERENCES usuarios(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Resultado del motor: se reemplazan cada vez que se recalcula una reunión.
CREATE TABLE IF NOT EXISTS sugerencias (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    reunion_id  INT NOT NULL,
    inicio      DATETIME NOT NULL,
    fin         DATETIME NOT NULL,
    score       SMALLINT NOT NULL,
    creado_en   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_sug_reunion FOREIGN KEY (reunion_id)
        REFERENCES reuniones(id) ON DELETE CASCADE,
    INDEX idx_sug_reunion (reunion_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
