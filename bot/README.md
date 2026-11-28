# Bot Propio de ARCA (Mis Comprobantes)

Microservicio en Python + Playwright que automatiza el ingreso a ARCA (AFIP) con CUIT y Clave Fiscal, consulta "Mis Comprobantes" (Emitidos y Recibidos) para el período solicitado y descarga y parsea directamente el CSV oficial.

Reemplaza servicios pagos de terceros como Afip SDK con un formato de API 100% compatible.

## Características
- **100% compatible con la API de Afip SDK**: Expone `POST /api/v1/automations` y `GET /api/v1/automations/{id}`.
- **Soporte de selector de empresas**: Si el CUIT tiene asignadas varias razones sociales, selecciona automáticamente el CUIT solicitado.
- **Manejo de archivos comprimidos**: Descarga y descomprime los archivos ZIP/CSV emitidos por ARCA en memoria.
- **Formato listo para `server/iva.js`**: Devuelve los registros normalizados con todas las columnas de IVA y contrapartes.

## Ejecución Local
```bash
cd bot
pip install -r requirements.txt
playwright install chromium
export IMPUESTO_ENV=development
uvicorn bot.main:app --host 0.0.0.0 --port 8000
```

## Despliegue con Docker (Oracle Cloud OCI / VPS)
```bash
docker build -t arca-bot -f bot/Dockerfile .
docker run -d --restart unless-stopped -p 8000:8000 \
  -v /var/lib/impuesto/boveda:/app/data/boveda \
  -e ORACLE_CLOUD=1 -e IMPUESTO_VAULT_KEY=... -e BOT_API_SECRET=... \
  --name arca-bot arca-bot
```

### Migración de bóveda desde `.vault_key` a `IMPUESTO_VAULT_KEY` (O2)
Si la VM venía corriendo con `.vault_key` generada localmente y vas a pasar a `IMPUESTO_VAULT_KEY`:
1. **Pará el contenedor actual** (`docker stop arca-bot`) para evitar que escriba archivos con otra clave durante la migración.
2. **Hacé un backup en el host:**
   ```bash
   sudo tar czf boveda-backup-$(date +%F).tgz -C /var/lib/impuesto boveda
   ```
3. **Corré primero `--dry-run` y luego `--aplicar`** pasando `IMPUESTO_VAULT_KEY` vía `--env-file /etc/impuesto/env` (permisos `0600`) o `-e IMPUESTO_VAULT_KEY` (heredada del entorno; **nunca** pegues la clave literal en la línea de comandos):
   ```bash
   docker run --rm --env-file /etc/impuesto/env \
     -v /var/lib/impuesto/boveda:/app/data/boveda arca-bot \
     python3 -m bot.migrar_clave_boveda --vault-dir /app/data/boveda
   docker run --rm --env-file /etc/impuesto/env \
     -v /var/lib/impuesto/boveda:/app/data/boveda arca-bot \
     python3 -m bot.migrar_clave_boveda --vault-dir /app/data/boveda --aplicar
   ```
4. **Levantá el contenedor nuevo** con `--env-file /etc/impuesto/env` (`IMPUESTO_VAULT_KEY`, `BOT_API_SECRET`) y el volumen `/app/data/boveda`.
5. **Retención (limpieza tras verificar operación):** después de 7 días de operación verificada en producción, eliminá `/var/lib/impuesto/boveda/_backups_o2/` y `/var/lib/impuesto/boveda/.vault_key.migrada` (mientras existan, la clave vieja sigue descifrando esas copias).

## Configuración en Cloudflare Pages
En las variables de entorno de Cloudflare Pages:
- `BOT_PROVIDER`: `propio` (o `afipsdk` para usar Afip SDK como secundario).
- `BOT_API_URL`: URL pública de este microservicio (ej. `https://bot.impuesto.com.ar/api/v1/automations`).
- `BOT_API_TOKEN` (opcional): Token de seguridad si se agrega autenticación.
