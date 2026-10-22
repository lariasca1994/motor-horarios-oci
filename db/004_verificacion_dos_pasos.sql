-- Verificación en dos pasos (functions/api/mfa.py): clave TOTP cifrada, código del correo
-- como huella y método preferido. Se aplica con la cuenta administradora (el usuario de la
-- app solo tiene SELECT, INSERT, UPDATE y DELETE).
ALTER TABLE usuarios ADD COLUMN mfa JSON NULL;
