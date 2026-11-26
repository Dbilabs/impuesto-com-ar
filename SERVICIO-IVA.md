# Servicio "IVA automático": cómo funciona y cómo ponerlo en marcha

El cliente carga **una sola vez** su CUIT, su usuario y su clave fiscal. Desde ese momento, cuando lo pide (desde su panel privado), un robot entra a ARCA, consulta **Mis Comprobantes** (emitidos y recibidos) y le muestra cuánto IVA viene en el mes. No sube archivos ni llama a su contador.

## Flujo

```
/iva/  → formulario: CUIT, usuario, clave fiscal, autorización expresa, "guardar acceso"
          │ POST /api/iva/conectar
          ▼
   Cloudflare Pages Function ── cifra usuario y clave (AES-256-GCM, llave CRED_KEY) ──► D1 (tabla cuentas)
          │ lanza 2 trabajos del robot: Emitidos (E) y Recibidos (R) del mes
          ▼
   Proveedor del robot (Afip SDK, automatización "mis-comprobantes")
          │ POST /api/iva/estado cada 5 s
          ▼
   Suma el IVA (notas de crédito restan, moneda extranjera × tipo de cambio) → guarda SOLO totales
          ▼
   Resultado en pantalla + enlace privado → /iva/mi-cuenta/  (consultar mes en curso o anterior, historial, borrar cuenta)
```

## Seguridad implementada

- La clave fiscal se cifra con **AES-256-GCM**, usando el ID de la cuenta como dato asociado. La llave maestra (`CRED_KEY`) es un secreto de Cloudflare, separado de la base.
- **Probado:** en la base solo queda el texto cifrado; la clave no aparece en texto plano en ningún archivo.
- Si el cliente no marca "guardar acceso", la clave se usa para esa consulta y se descarta.
- El enlace privado no se guarda: la base solo tiene su hash (SHA-256). Además, el token va en el `#` de la URL, que no viaja al servidor ni queda en logs, y la página lo borra de la barra de direcciones apenas carga.
- Límites de uso: 5 conexiones por IP por hora y 5 minutos entre consultas de una misma cuenta.
- De los comprobantes se guardan solo los totales mensuales y los 5 principales clientes y proveedores, nunca el detalle.
- Política de seguridad de contenido (CSP) estricta: sin scripts de terceros en las páginas donde se carga la clave.
- El cliente puede **borrar todo en un clic**: cuenta, acceso cifrado y consultas.
- Hay una página pública `/iva/seguridad/` que lo explica, y los textos del sitio se ajustaron: el diagnóstico sigue sin pedir la clave y solo este servicio la usa.

## Puesta en marcha

1. **Robot:** creá una cuenta en Afip SDK y obtené el access token de su API de automatizaciones (automatización `mis-comprobantes`). Revisá precios y límites de su plan. Para cambiar de proveedor o usar un robot propio (por ejemplo, Playwright con Cloudflare Browser Rendering), agregá un proveedor en `server/bot.js` con las funciones `start` y `status`.
2. **Base de datos:**
   ```
   npx wrangler d1 create impuestos-iva            # copiá el database_id en wrangler.toml
   npx wrangler d1 execute impuestos-iva --remote --file=schema.sql
   ```
   En Cloudflare Pages → Settings → Bindings, verificá que exista el binding D1 `DB`.
3. **Secretos** (Pages → Settings → Variables and secrets, en Production):
   - `CRED_KEY`: generala con `openssl rand -base64 32` y **guardá una copia offline**. Si se pierde, los accesos guardados no se pueden descifrar y los clientes tienen que reconectarse.
   - `AFIPSDK_TOKEN`
   - `SHEETS_WEBHOOK_URL` y `SHEETS_SECRET` (cada conexión también entra como lead en la planilla, sin la clave).
   - `BOT_PROVIDER=afipsdk` (ya viene en `wrangler.toml`).
4. **Prueba real:** conectá tu propio CUIT y compará el débito y el crédito con lo que muestra Mis Comprobantes.

Para probar en tu compu sin tocar ARCA: poné `BOT_PROVIDER = "mock"` en `wrangler.toml`, creá un archivo `.dev.vars` con `CRED_KEY=...` y corré `npx wrangler pages dev dist`.

## Antes de abrirlo al público (riesgos que conviene cubrir)

1. **Revisión legal.** ARCA define la clave fiscal como personal e intransferible. Hay servicios en el mercado que operan con este modelo, pero que el cliente la comparta con un tercero queda bajo su responsabilidad y la tuya. Que un abogado revise el texto de autorización (ya incluido en el formulario y guardado con fecha), los términos del servicio y la política de privacidad.
2. **Datos personales:** registrá la base ante la AAIP y nombrá a Afip SDK (o al proveedor que uses) como encargado del tratamiento, con un contrato que lo cubra.
3. **Seguridad operativa:** activá el doble factor en Cloudflare, en Afip SDK y en GitHub, limitá quién tiene acceso a los secretos y armá un plan de respuesta ante incidentes. Este servicio pasa a ser el activo más sensible del proyecto.
4. **Opción para empresas grandes:** algunos CFOs no van a dar la clave. Para ellos conviene ofrecer la alternativa de **delegar el servicio Mis Comprobantes** a un CUIT tuyo o del estudio aliado. El robot funciona igual, usando la clave del representante; solo hay que agregar ese modo en el formulario. La calculadora manual (sin clave) sigue disponible en la misma página.
5. **Qué no cubre:** Mis Comprobantes no informa retenciones, percepciones ni el saldo técnico anterior. Por eso el panel deja cargarlos a mano y aclara que el resultado es una estimación: la declaración jurada la confirma el contador en IVA Simple.

## Ideas para la próxima versión

- Avisos automáticos por WhatsApp o email los días 10 y 17 de cada mes (un Cron Trigger de Cloudflare que recorre las cuentas con acceso guardado).
- Login por email (enlace mágico), en lugar de depender solo del enlace privado.
- Traer también "Mis Retenciones" para incluir retenciones y percepciones sin carga manual.
- Ofrecer un plan pago, o dárselo gratis a quien contrate al estudio aliado.
