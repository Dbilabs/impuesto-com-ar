-- Migración D1 0002: agrega pertenencia (owner_email) a estudios_contables (cierre N2 / P0-3).
-- Aplicar en producción:
--   npx wrangler d1 execute impuesto-iva --remote --file=migrations/0002_estudios_owner.sql
--
-- Nota operativa: los estudios legacy creados antes de esta migración quedan con owner_email = ''
-- y serán rechazados por assertEstudioOwner() (fail-closed) hasta re-vincularlos o asignar su
-- owner_email explícitamente mediante UPDATE estudios_contables SET owner_email = '...' WHERE id = '...'.

ALTER TABLE estudios_contables ADD COLUMN owner_email TEXT NOT NULL DEFAULT '';
CREATE INDEX IF NOT EXISTS idx_estudios_owner ON estudios_contables (owner_email);
