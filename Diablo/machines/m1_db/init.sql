SET NAMES utf8mb4;
CREATE DATABASE IF NOT EXISTS corp_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER DATABASE corp_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE corp_db;

CREATE USER IF NOT EXISTS 'db_admin'@'%' IDENTIFIED BY 'SuperSecretDBPass123!';
GRANT SELECT, INSERT, UPDATE, DELETE ON corp_db.* TO 'db_admin'@'%';
FLUSH PRIVILEGES;

CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(64) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL,
    role VARCHAR(32) NOT NULL DEFAULT 'user',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO users (username, password, role)
VALUES ('db_admin', 'SuperSecretDBPass123!', 'admin')
ON DUPLICATE KEY UPDATE password = VALUES(password), role = VALUES(role);

CREATE TABLE IF NOT EXISTS tickets (
    id INT AUTO_INCREMENT PRIMARY KEY,
    ticket_id VARCHAR(32) NOT NULL UNIQUE,
    subject VARCHAR(255) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'open',
    priority VARCHAR(32) NOT NULL DEFAULT 'medium',
    opened_by VARCHAR(64) NOT NULL DEFAULT 'customer',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO tickets (ticket_id, subject, status, priority, opened_by) VALUES
    ('TCK-1001', 'No puedo acceder al portal de clientes', 'open', 'high', 'acme'),
    ('TCK-1002', 'Solicitud de factura duplicada', 'pending', 'medium', 'globex'),
    ('TCK-1003', 'Actualización de datos de contacto', 'closed', 'low', 'initech'),
    ('TCK-1004', 'Error al adjuntar documentación', 'open', 'medium', 'umbrella'),
    ('TCK-1005', 'Consulta sobre integración de API', 'pending', 'high', 'hooli')
ON DUPLICATE KEY UPDATE
    subject = VALUES(subject),
    status = VALUES(status),
    priority = VALUES(priority);

CREATE TABLE IF NOT EXISTS site_users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(64) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    display_name VARCHAR(80) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO site_users (username, password_hash, display_name)
VALUES
    (
        'demo',
        'pbkdf2_sha256$200000$6f1c9a7b2d4e8f10$06f747f11c57811ae7597f071fa7ff631ea24018fa2a429aca5de3a3e4ce1969',
        'Cliente Demo'
    ),
    (
        'ana.torres',
        'pbkdf2_sha256$200000$433964805ac0c931317655719c70d655$87529d906ba9ee2b12fbfe958413a86dd0db6123eb1a544d71bbea540356d4df',
        'Ana Torres'
    ),
    (
        'bruno.diaz',
        'pbkdf2_sha256$200000$14503bad6e0680c0190060c425a90a83$eb5b789724aa58a70d6fdd608448b1e7d21e27377760baeeb2569decc6bb1697',
        'Bruno Díaz'
    ),
    (
        'carla.mendez',
        'pbkdf2_sha256$200000$0ea16f1d5b099c882b8246a2d727b215$ec57434bb95c37174492b511396dee16f0f0e9a354f528aa66925abbe587aa4a',
        'Carla Méndez'
    ),
    (
        'diego.ruiz',
        'pbkdf2_sha256$200000$ae38da0ee37d91643e8ef8f0aa93996e$225713de37d2bea3ff4b7e7c43b26505ac39119e724b55d540b31db8e7add0b6',
        'Diego Ruiz'
    ),
    (
        'elena.vidal',
        'pbkdf2_sha256$200000$780472e5a3739a4206c2eda0562c20a6$60150285756760949f432bd8aaf5532dd0d21dcfb102d3a2f7366bbeb06bae81',
        'Elena Vidal'
    )
ON DUPLICATE KEY UPDATE display_name = VALUES(display_name);

CREATE TABLE IF NOT EXISTS account_metrics (
    id INT AUTO_INCREMENT PRIMARY KEY,
    account_id INT NOT NULL,
    metric_key VARCHAR(64) NOT NULL,
    metric_value VARCHAR(255) NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_account_metric (account_id, metric_key),
    KEY idx_account_metrics_account (account_id),
    CONSTRAINT fk_account_metrics_user FOREIGN KEY (account_id) REFERENCES site_users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO account_metrics (account_id, metric_key, metric_value)
SELECT u.id, m.metric_key, m.metric_value
FROM site_users u
JOIN (
    SELECT 'demo' AS username, 'logins_total' AS metric_key, '12' AS metric_value
    UNION ALL SELECT 'demo', 'last_login_at', '2026-10-18 09:14:00'
    UNION ALL SELECT 'demo', 'last_login_ip', '203.0.113.24'
    UNION ALL SELECT 'demo', 'messages_sent', '3'
    UNION ALL SELECT 'demo', 'messages_received', '5'
    UNION ALL SELECT 'demo', 'api_calls_30d', '184'
    UNION ALL SELECT 'demo', 'storage_used_mb', '42'
    UNION ALL SELECT 'demo', 'mfa_enabled', 'false'
    UNION ALL SELECT 'ana.torres', 'logins_total', '31'
    UNION ALL SELECT 'ana.torres', 'last_login_at', '2026-10-19 17:02:00'
    UNION ALL SELECT 'ana.torres', 'last_login_ip', '198.51.100.17'
    UNION ALL SELECT 'ana.torres', 'messages_sent', '14'
    UNION ALL SELECT 'ana.torres', 'messages_received', '9'
    UNION ALL SELECT 'ana.torres', 'api_calls_30d', '921'
    UNION ALL SELECT 'ana.torres', 'storage_used_mb', '128'
    UNION ALL SELECT 'ana.torres', 'mfa_enabled', 'true'
    UNION ALL SELECT 'bruno.diaz', 'logins_total', '8'
    UNION ALL SELECT 'bruno.diaz', 'last_login_at', '2026-10-17 11:40:00'
    UNION ALL SELECT 'bruno.diaz', 'last_login_ip', '192.0.2.88'
    UNION ALL SELECT 'bruno.diaz', 'messages_sent', '6'
    UNION ALL SELECT 'bruno.diaz', 'messages_received', '4'
    UNION ALL SELECT 'bruno.diaz', 'api_calls_30d', '77'
    UNION ALL SELECT 'bruno.diaz', 'storage_used_mb', '18'
    UNION ALL SELECT 'bruno.diaz', 'mfa_enabled', 'false'
    UNION ALL SELECT 'carla.mendez', 'logins_total', '22'
    UNION ALL SELECT 'carla.mendez', 'last_login_at', '2026-10-20 08:03:00'
    UNION ALL SELECT 'carla.mendez', 'last_login_ip', '203.0.113.91'
    UNION ALL SELECT 'carla.mendez', 'messages_sent', '11'
    UNION ALL SELECT 'carla.mendez', 'messages_received', '13'
    UNION ALL SELECT 'carla.mendez', 'api_calls_30d', '453'
    UNION ALL SELECT 'carla.mendez', 'storage_used_mb', '76'
    UNION ALL SELECT 'carla.mendez', 'mfa_enabled', 'true'
    UNION ALL SELECT 'diego.ruiz', 'logins_total', '5'
    UNION ALL SELECT 'diego.ruiz', 'last_login_at', '2026-10-14 15:22:00'
    UNION ALL SELECT 'diego.ruiz', 'last_login_ip', '198.51.100.44'
    UNION ALL SELECT 'diego.ruiz', 'messages_sent', '2'
    UNION ALL SELECT 'diego.ruiz', 'messages_received', '1'
    UNION ALL SELECT 'diego.ruiz', 'api_calls_30d', '31'
    UNION ALL SELECT 'diego.ruiz', 'storage_used_mb', '9'
    UNION ALL SELECT 'diego.ruiz', 'mfa_enabled', 'false'
    UNION ALL SELECT 'elena.vidal', 'logins_total', '19'
    UNION ALL SELECT 'elena.vidal', 'last_login_at', '2026-10-19 10:55:00'
    UNION ALL SELECT 'elena.vidal', 'last_login_ip', '192.0.2.151'
    UNION ALL SELECT 'elena.vidal', 'messages_sent', '9'
    UNION ALL SELECT 'elena.vidal', 'messages_received', '7'
    UNION ALL SELECT 'elena.vidal', 'api_calls_30d', '602'
    UNION ALL SELECT 'elena.vidal', 'storage_used_mb', '57'
    UNION ALL SELECT 'elena.vidal', 'mfa_enabled', 'true'
) m ON m.username = u.username
ON DUPLICATE KEY UPDATE metric_value = VALUES(metric_value);

ALTER TABLE account_metrics AUTO_INCREMENT = 49;

CREATE TABLE IF NOT EXISTS messages (
    id INT AUTO_INCREMENT PRIMARY KEY,
    sender_id INT NOT NULL,
    recipient_id INT NOT NULL,
    subject VARCHAR(160) NOT NULL,
    body TEXT NOT NULL,
    is_read TINYINT(1) NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_messages_recipient (recipient_id, created_at),
    KEY idx_messages_sender (sender_id, created_at),
    CONSTRAINT fk_messages_sender FOREIGN KEY (sender_id) REFERENCES site_users(id) ON DELETE CASCADE,
    CONSTRAINT fk_messages_recipient FOREIGN KEY (recipient_id) REFERENCES site_users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO messages (sender_id, recipient_id, subject, body, is_read)
SELECT s.id, r.id, m.subject, m.body, m.is_read
FROM (
    SELECT 'ana.torres' AS sender, 'demo' AS recipient, 'Bienvenida al portal' AS subject,
           'Hola, ya está disponible el nuevo panel de métricas de cuenta. Cualquier duda, escríbeme por aquí.' AS body,
           0 AS is_read
    UNION ALL
    SELECT 'bruno.diaz', 'demo', 'Revisión de factura Q3',
           'He revisado la factura del tercer trimestre y todo cuadra. Gracias por el detalle.',
           0
    UNION ALL
    SELECT 'carla.mendez', 'demo', 'Acceso a la API',
           '¿Podrías confirmarme si el token de integración sigue vigente? No quiero romper el flujo de producción.',
           1
    UNION ALL
    SELECT 'demo', 'ana.torres', 'Re: Bienvenida al portal',
           'Gracias Ana. Las métricas nuevas se ven bien; revisaré los últimos accesos esta semana.',
           1
    UNION ALL
    SELECT 'demo', 'bruno.diaz', 'Confirmación de factura',
           'Confirmado. El área financiera ya tiene la factura conciliada.',
           1
    UNION ALL
    SELECT 'elena.vidal', 'demo', 'Solicitud de soporte',
           'Hemos abierto el caso CASE-2041. Te mantendremos informado por este medio.',
           0
) m
JOIN site_users s ON s.username = m.sender
JOIN site_users r ON r.username = m.recipient;

ALTER TABLE messages AUTO_INCREMENT = 7;

CREATE TABLE IF NOT EXISTS comments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    author VARCHAR(80) NOT NULL,
    email VARCHAR(160) NULL,
    body TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO comments (author, email, body) VALUES
    ('Laura M.', 'laura@example.com', 'El nuevo portal es mucho más claro. Encontramos las facturas en menos de un minuto.'),
    ('Diego R.', NULL, 'La integración con nuestro CRM funcionó a la primera. El equipo de soporte respondió el mismo día.'),
    ('Marta S.', 'marta@example.com', 'Me gustaría poder exportar los casos en PDF, pero por lo demás la experiencia es muy buena.'),
    ('Andrés P.', NULL, 'La encuesta de satisfacción es rápida y el seguimiento de casos se entiende bien.');

CREATE TABLE IF NOT EXISTS survey_responses (
    id INT AUTO_INCREMENT PRIMARY KEY,
    satisfaction TINYINT NOT NULL,
    service VARCHAR(32) NOT NULL,
    feedback TEXT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO survey_responses (satisfaction, service, feedback) VALUES
    (5, 'portal', 'Muy fácil de usar.'),
    (4, 'soporte', 'Respuesta rápida y clara.'),
    (3, 'facturacion', 'La factura tardó un poco en aparecer.'),
    (5, 'integraciones', 'La documentación de la API fue suficiente.'),
    (4, 'portal', NULL),
    (5, 'soporte', 'Seguimiento excelente.');

CREATE TABLE IF NOT EXISTS newsletter_subscribers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(160) NOT NULL UNIQUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS kb_articles (
    id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(180) NOT NULL,
    category VARCHAR(64) NOT NULL,
    body TEXT NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO kb_articles (title, category, body) VALUES
    ('Cómo restablecer la contraseña del portal', 'cuenta', 'Acceda al portal, seleccione la opción de recuperación y siga las instrucciones enviadas a su correo corporativo.'),
    ('Consulta y descarga de facturas', 'facturacion', 'Las facturas están disponibles en la sección de cuenta. El periodo de retención estándar es de 24 meses.'),
    ('Introducción a la API de integración', 'integraciones', 'La API pública utiliza autenticación por token y devuelve respuestas JSON. Los detalles se entregan a cada cliente tras la firma del acuerdo.'),
    ('Horarios y canales de soporte', 'soporte', 'El soporte está disponible de lunes a viernes de 08:00 a 19:00 y fuera de horario para incidencias críticas.'),
    ('Configuración de notificaciones', 'cuenta', 'Las preferencias de notificación se gestionan desde el perfil del cliente y se aplican en un plazo máximo de 24 horas.'),
    ('Planes y licencias disponibles', 'facturacion', 'Los planes Starter, Business y Enterprise se adaptan al número de usuarios y al nivel de soporte contratado.');
