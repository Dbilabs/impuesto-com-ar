-- Base de datos D1 del servicio "IVA automático".
-- Crear: npx wrangler d1 create impuestos-iva   (pegá el database_id en wrangler.toml)
-- Aplicar: npx wrangler d1 execute impuestos-iva --remote --file=schema.sql
CREATE TABLE IF NOT EXISTS cuentas (
  id TEXT PRIMARY KEY,
  token_hash TEXT NOT NULL UNIQUE,      -- hash del enlace privado (el enlace nunca se guarda)
  cuit TEXT NOT NULL,                   -- CUIT consultado
  nombre TEXT, email TEXT, whatsapp TEXT,
  guardar INTEGER NOT NULL DEFAULT 0,   -- 1 = el cliente autorizó guardar su acceso
  cred_ct TEXT, cred_iv TEXT,           -- usuario y clave fiscal cifrados con AES-256-GCM (NULL si no se guarda)
  autorizacion_texto TEXT, autorizacion_fecha TEXT,
  ip_hash TEXT, creada TEXT NOT NULL, ultima_consulta TEXT
);
CREATE INDEX IF NOT EXISTS idx_cuentas_ip ON cuentas (ip_hash, creada);

CREATE TABLE IF NOT EXISTS consultas (
  id TEXT PRIMARY KEY,
  cuenta_id TEXT NOT NULL REFERENCES cuentas(id) ON DELETE CASCADE,
  periodo TEXT NOT NULL,                -- AAAA-MM
  estado TEXT NOT NULL,                 -- en_proceso | lista | error
  job_e TEXT, job_r TEXT,               -- ids de los trabajos del robot (emitidos / recibidos)
  resultado TEXT,                       -- JSON con totales (sin detalle de comprobantes)
  error TEXT, creada TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_consultas_cuenta ON consultas (cuenta_id, creada);

CREATE TABLE IF NOT EXISTS perfiles_contribuyentes (
  cuit TEXT PRIMARY KEY,
  razon_social TEXT,
  rol TEXT,                             -- ej. "Socio Gerente", "Monotributista profesional", "Director"
  tipo_personeria TEXT NOT NULL,        -- monotributo | responsable_inscripto_ph | srl | sa | sas
  que_vende TEXT NOT NULL,              -- descripción de productos o servicios
  a_quien_vende TEXT NOT NULL,          -- empresas_ri | consumidor_final | exterior | mixto
  ubicacion_sede TEXT NOT NULL,         -- jurisdicción principal (CABA, PBA, etc.)
  jurisdicciones TEXT,                  -- JSON array de jurisdicciones
  cantidad_empleados INTEGER DEFAULT 0, -- 0 = sin empleados
  convenio_colectivo TEXT,
  marco_fiscal_json TEXT,               -- diagnóstico y reglas fiscales computadas
  actualizado TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conocimiento_aprendido (
  id TEXT PRIMARY KEY,
  cuit_origen TEXT,
  pregunta TEXT NOT NULL,
  contexto_cliente TEXT,
  estado TEXT NOT NULL DEFAULT 'pendiente', -- pendiente | resuelta_y_aprendida
  respuesta_clara TEXT,
  normativa_oficial TEXT,
  creada TEXT NOT NULL,
  resuelta TEXT
);
CREATE INDEX IF NOT EXISTS idx_conocimiento_estado ON conocimiento_aprendido (estado, creada);

-- Modo Estudio Contable (B2B Multi-Cliente)
CREATE TABLE IF NOT EXISTS estudios_contables (
  id TEXT PRIMARY KEY,
  owner_email TEXT NOT NULL DEFAULT '',
  nombre_estudio TEXT NOT NULL,
  cuit_estudio TEXT NOT NULL,
  socio_responsable TEXT,
  branding_pie TEXT,
  creado TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_estudios_owner ON estudios_contables (owner_email);

CREATE TABLE IF NOT EXISTS cartera_clientes (
  id TEXT PRIMARY KEY,
  estudio_id TEXT NOT NULL,
  cuit_cliente TEXT NOT NULL,
  razon_social TEXT NOT NULL,
  regimen TEXT NOT NULL,                -- monotributo | responsable_inscripto | srl | sa
  jurisdicciones TEXT,                  -- JSON array
  empleados INTEGER DEFAULT 0,
  analista_asignado TEXT,
  estado_delegacion TEXT DEFAULT 'verificado',
  actualizado TEXT NOT NULL,
  UNIQUE(estudio_id, cuit_cliente)
);
CREATE INDEX IF NOT EXISTS idx_cartera_estudio ON cartera_clientes (estudio_id, analista_asignado);

CREATE TABLE IF NOT EXISTS cierres_mensuales_estudio (
  id TEXT PRIMARY KEY,
  estudio_id TEXT NOT NULL,
  cuit_cliente TEXT NOT NULL,
  periodo TEXT NOT NULL,                -- YYYY-MM
  impuesto TEXT NOT NULL,               -- IVA | IIBB | F931 | MONOTRIBUTO | GANANCIAS | BBPP
  monto_actual REAL NOT NULL,
  monto_anterior REAL DEFAULT 0,
  desvio_pct REAL DEFAULT 0,
  alerta_anomalia INTEGER DEFAULT 0,    -- 1 si desvío > 30%
  estado_aprobacion TEXT NOT NULL DEFAULT 'pendiente_revision_socio',
  preparado_por TEXT,
  aprobado_por TEXT,
  notas TEXT,
  actualizado TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cierres_estudio ON cierres_mensuales_estudio (estudio_id, periodo, estado_aprobacion);
