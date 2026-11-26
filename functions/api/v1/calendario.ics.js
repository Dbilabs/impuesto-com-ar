// Cloudflare Pages Function: GET /api/v1/calendario.ics?cuit=20264205825&perfil=monotributo
// Genera un archivo .ics descargable y suscribible en 1 clic para Google Calendar, Apple Calendar y Outlook.

function nextDateForDay(day, monthOverride = null) {
  const now = new Date();
  let y = now.getUTCFullYear();
  let m = monthOverride !== null ? monthOverride : now.getUTCMonth() + 1;
  if (monthOverride === null && now.getUTCDate() > day) {
    m += 1;
    if (m > 12) { m = 1; y += 1; }
  } else if (monthOverride !== null && (m < now.getUTCMonth() + 1 || (m === now.getUTCMonth() + 1 && now.getUTCDate() > day))) {
    y += 1;
  }
  const mm = String(m).padStart(2, "0");
  const dd = String(Math.min(day, 28)).padStart(2, "0");
  return `${y}${mm}${dd}T120000Z`;
}

function nextMonday() {
  const now = new Date();
  const diff = (8 - now.getUTCDay()) % 7 || 7;
  const d = new Date(now.getTime() + diff * 86400000);
  const y = d.getUTCFullYear();
  const m = String(d.getUTCMonth() + 1).padStart(2, "0");
  const day = String(d.getUTCDate()).padStart(2, "0");
  return `${y}${m}${day}T123000Z`;
}

export async function onRequestGet({ request }) {
  const url = new URL(request.url);
  const cuit = (url.searchParams.get("cuit") || "").replace(/[^0-9]/g, "");
  const perfil = (url.searchParams.get("perfil") || "monotributo").toLowerCase();
  const term = cuit ? parseInt(cuit.slice(-1), 10) : 5;

  const diaAutonomos = term <= 3 ? 5 : (term <= 6 ? 6 : 7);
  const diaF931 = term <= 3 ? 9 : (term <= 6 ? 10 : 11);
  const diaIva = 18 + Math.floor(term / 2);

  const eventos = [
    {
      uid: `apertura-mes-${cuit || "general"}`,
      summary: "[impuesto.com.ar] Apertura de mes fiscal (abrir chat nuevo)",
      desc: "Abrí un chat nuevo en tu asistente (Gemini, Claude o ChatGPT) y escribí: Arranquemos el mes.",
      dtstart: nextDateForDay(1),
      rrule: "FREQ=MONTHLY;BYMONTHDAY=1"
    },
    {
      uid: `dfe-semanal-${cuit || "general"}`,
      summary: "[ARCA] Revisión Domicilio Fiscal Electrónico (DFE)",
      desc: "Pedile a tu Contador Agéntico: Revisá si tengo notificaciones nuevas en el DFE.",
      dtstart: nextMonday(),
      rrule: "FREQ=WEEKLY;BYDAY=MO"
    },
    {
      uid: `planes-dia16-${cuit || "general"}`,
      summary: "[ARCA] Previsión débito Mis Facilidades (se debita día 16)",
      desc: "Verificá saldo en la CBU antes del débito automático del día 16.",
      dtstart: nextDateForDay(14),
      rrule: "FREQ=MONTHLY;BYMONTHDAY=14"
    }
  ];

  if (perfil.includes("mono")) {
    eventos.push(
      {
        uid: `mono-cuota-${cuit || "general"}`,
        summary: "[ARCA] Pago Cuota Monotributo (vence día 20)",
        desc: "Pedile a tu Contador Agéntico: Revisá mi cuota de Monotributo y CCMA de este mes.",
        dtstart: nextDateForDay(18),
        rrule: "FREQ=MONTHLY;BYMONTHDAY=18"
      },
      {
        uid: `mono-recat-${cuit || "general"}`,
        summary: "[ARCA] Control Recategorización Semestral Monotributo",
        desc: "Revisá facturación acumulada de los últimos 12 meses vs. tope de categoría.",
        dtstart: nextDateForDay(5, 1),
        rrule: "FREQ=MONTHLY;INTERVAL=6;BYMONTHDAY=5"
      }
    );
  }

  if (perfil.includes("inscripto") || perfil.includes("autonomo") || perfil.includes("mono")) {
    eventos.push({
      uid: `autonomos-${cuit || "general"}`,
      summary: `[ARCA] Autónomos (CUIT term. ${term} — vence día ${diaAutonomos})`,
      desc: "Revisá tu cuota mensual de Autónomos en CCMA para pagar en término sin intereses.",
      dtstart: nextDateForDay(Math.max(1, diaAutonomos - 2)),
      rrule: `FREQ=MONTHLY;BYMONTHDAY=${Math.max(1, diaAutonomos - 2)}`
    });
  }

  if (perfil.includes("inscripto") || perfil.includes("pyme") || perfil.includes("sociedad")) {
    eventos.push({
      uid: `iva-f2002-${cuit || "general"}`,
      summary: `[ARCA] Cierre IVA F. 2002 (CUIT term. ${term} — vence día ${diaIva})`,
      desc: "Pedile a tu Contador Agéntico: Armá mi cierre mensual de IVA cruzando Mis Comprobantes y retenciones.",
      dtstart: nextDateForDay(Math.max(1, diaIva - 4)),
      rrule: `FREQ=MONTHLY;BYMONTHDAY=${Math.max(1, diaIva - 4)}`
    });
  }

  if (perfil.includes("pyme") || perfil.includes("sociedad")) {
    eventos.push({
      uid: `f931-${cuit || "general"}`,
      summary: `[ARCA] Sueldos y F. 931 (CUIT term. ${term} — vence día ${diaF931})`,
      desc: "Revisá nómina, cargas sociales y saldos de Seguridad Social en SCT.",
      dtstart: nextDateForDay(Math.max(1, diaF931 - 3)),
      rrule: `FREQ=MONTHLY;BYMONTHDAY=${Math.max(1, diaF931 - 3)}`
    });
  }

  eventos.push({
    uid: `ganancias-bbpp-${cuit || "general"}`,
    summary: "[ARCA] Preparación Ganancias (F. 2711) y Bienes Personales",
    desc: "Revisión de Nuestra Parte, deducciones SiRADIG y saldos a favor antes del vencimiento de Junio.",
    dtstart: nextDateForDay(15, 5),
    rrule: "FREQ=YEARLY;BYMONTH=5;BYMONTHDAY=15"
  });

  const lines = [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//impuesto.com.ar//Calendario Fiscal ARCA//ES",
    "CALSCALE:GREGORIAN",
    "METHOD:PUBLISH",
    `X-WR-CALNAME:Impuestos ARCA${cuit ? ` (${cuit})` : ""}`,
    "X-WR-TIMEZONE:America/Argentina/Buenos_Aires"
  ];

  const stamp = new Date().toISOString().replace(/[-:]/g, "").split(".")[0] + "Z";
  for (const ev of eventos) {
    lines.push(
      "BEGIN:VEVENT",
      `UID:${ev.uid}@impuesto.com.ar`,
      `DTSTAMP:${stamp}`,
      `DTSTART:${ev.dtstart}`,
      `RRULE:${ev.rrule}`,
      `SUMMARY:${ev.summary}`,
      `DESCRIPTION:${ev.desc}`,
      "BEGIN:VALARM",
      "TRIGGER:-PT15M",
      "ACTION:DISPLAY",
      `DESCRIPTION:${ev.summary}`,
      "END:VALARM",
      "END:VEVENT"
    );
  }
  lines.push("END:VCALENDAR");

  const filename = cuit ? `vencimientos_arca_${cuit}.ics` : "vencimientos_arca.ics";
  return new Response(lines.join("\r\n") + "\r\n", {
    status: 200,
    headers: {
      "Content-Type": "text/calendar; charset=utf-8",
      "Content-Disposition": `attachment; filename="${filename}"`,
      "Cache-Control": "no-cache",
      "Access-Control-Allow-Origin": "*"
    }
  });
}
