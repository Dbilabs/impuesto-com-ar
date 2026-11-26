/**
 * Recibe los leads de impuestos.com.ar y los guarda en esta planilla.
 * Instalación (5 minutos):
 * 1. Creá una planilla de Google Sheets nueva llamada "Leads impuestos.com.ar".
 * 2. Extensiones → Apps Script. Pegá este código y guardá.
 * 3. Cambiá SECRET por una clave larga (la misma que pongas en Cloudflare como SHEETS_SECRET).
 * 4. Opcional: completá NOTIFICAR con tu email para recibir un aviso por cada lead.
 * 5. Implementar → Nueva implementación → Tipo: Aplicación web.
 *    Ejecutar como: Yo. Quién tiene acceso: Cualquier usuario.
 * 6. Copiá la URL (termina en /exec) y cargala en Cloudflare como SHEETS_WEBHOOK_URL.
 */
const SECRET = '7a1f59c83de2b46014e82b3a1d9487c53018e694f5012a87';
const NOTIFICAR = 'info@impuesto.com.ar'; // avisos automáticos de cada lead
const HOJA = 'Leads';
const COLUMNAS = ['fecha', 'estado', 'destino', 'puntaje', 'motivo_ruteo', 'perfil', 'tema', 'situacion', 'nombre', 'email', 'whatsapp',
  'empresa', 'cargo', 'facturacion', 'provincia', 'mensaje', 'consentimiento', 'pagina', 'landing', 'referrer',
  'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content', 'gclid', 'pais_ip'];

function doPost(e) {
  try {
    const data = JSON.parse(e.postData.contents);
    if (data.secret !== SECRET) return out({ ok: false, error: 'secret' });
    const lead = data.lead || {};
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    let sh = ss.getSheetByName(HOJA);
    if (!sh) {
      sh = ss.insertSheet(HOJA);
      sh.appendRow(COLUMNAS);
      sh.setFrozenRows(1);
      sh.getRange(1, 1, 1, COLUMNAS.length).setFontWeight('bold');
    }
    const lock = LockService.getScriptLock();
    lock.waitLock(10000);
    sh.appendRow(COLUMNAS.map(function (c) { return lead[c] !== undefined ? lead[c] : ''; }));
    lock.releaseLock();
    if (NOTIFICAR) {
      MailApp.sendEmail(NOTIFICAR, 'Nuevo lead (' + lead.destino + ', ' + lead.puntaje + ' pts): ' + lead.nombre,
        COLUMNAS.map(function (c) { return c + ': ' + (lead[c] || ''); }).join('\n'));
    }
    return out({ ok: true });
  } catch (err) {
    return out({ ok: false, error: String(err) });
  }
}

function out(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}
