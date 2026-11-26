"""Helpers de contenido compartidos por las páginas."""
import json
import html as _html
from pathlib import Path
import config as C

MONO = json.loads((Path(__file__).parent / "data" / "monotributo.json").read_text(encoding="utf-8"))

PROVINCIAS = ["Ciudad Autónoma de Buenos Aires", "Buenos Aires", "Catamarca", "Chaco", "Chubut", "Córdoba", "Corrientes",
              "Entre Ríos", "Formosa", "Jujuy", "La Pampa", "La Rioja", "Mendoza", "Misiones", "Neuquén", "Río Negro",
              "Salta", "San Juan", "San Luis", "Santa Cruz", "Santa Fe", "Santiago del Estero", "Tierra del Fuego", "Tucumán"]

FACTURACION_EMPRESA = ["Hasta $500 millones", "Entre $500 y $3.000 millones", "Entre $3.000 y $15.000 millones",
                       "Más de $15.000 millones", "Prefiero no decirlo"]


def esc(s):
    return _html.escape(str(s), quote=True)


def money(n, dec=False):
    if dec:
        s = f"{n:,.2f}"
    else:
        s = f"{round(n):,}"
    return "$\u00a0" + s.replace(",", "X").replace(".", ",").replace("X", ".")


def aliados_txt():
    a = C.ALIADOS
    if not a:
        return "estudios contables aliados"
    return a[0] if len(a) == 1 else ", ".join(a[:-1]) + " o " + a[-1]


def cta(perfil, tema, title, text, button="Quiero mi diagnóstico gratis", inline=True, tag="h2"):
    href = f"/diagnostico/?perfil={perfil}&amp;tema={tema}" if tema else f"/diagnostico/?perfil={perfil}"
    cls = "cta inline" if inline else "cta"
    return (f'<aside class="{cls}" aria-label="Consulta gratuita"><{tag}>{title}</{tag}><p>{text}</p>'
            f'<a class="btn" href="{href}" data-cta="{tema or perfil}">{button}</a></aside>')


def _select(name, label, options, required=True):
    req = ' required' if required else ''
    opts = '<option value="">Elegí una opción</option>' + "".join(f'<option>{esc(o)}</option>' for o in options)
    return f'<label for="f-{name}">{label}</label><select id="f-{name}" name="{name}"{req}>{opts}</select>'


def _consent():
    return ('<label class="chk"><input type="checkbox" name="consentimiento" value="si" required>'
            f'<span>Acepto que {C.SITE_NAME} comparta mis datos con el estudio contable aliado más adecuado para mi caso '
            f'({aliados_txt()}) para que me contacte, según la <a href="/privacidad/">política de privacidad</a>.</span></label>')


def _field(name, label, typ="text", auto="", ph="", required=True):
    req = ' required' if required else ''
    a = f' autocomplete="{auto}"' if auto else ''
    p = f' placeholder="{ph}"' if ph else ''
    return f'<label for="f-{name}">{label}</label><input id="f-{name}" type="{typ}" name="{name}"{a}{p}{req}>'


def diag_widget():
    """Embudo de 4 pasos. Funciona con app.js; sin JS muestra un aviso."""
    honeypot = '<div class="hp" aria-hidden="true"><label>No completar<input type="text" name="web" tabindex="-1" autocomplete="off"></label></div>'
    submit = '<button class="btn" type="submit" style="width:100%;margin-top:6px">Quiero mi diagnóstico gratis</button><p class="err" role="alert"></p>'
    persona = ('<form novalidate>'
               + _field("nombre", "Nombre y apellido", auto="name")
               + '<div class="row2">' + _field("email", "Email", "email", "email") + _field("whatsapp", "WhatsApp", "tel", "tel", "11 1234 5678") + '</div>'
               + _select("provincia", "Provincia", PROVINCIAS)
               + '<label for="f-mensaje">Contanos tu caso (opcional)</label><textarea id="f-mensaje" name="mensaje" maxlength="1200"></textarea>'
               + honeypot + _consent() + submit + '</form>')
    empresa = ('<form novalidate>'
               + '<div class="row2">' + _field("nombre", "Nombre y apellido", auto="name") + _field("cargo", "Cargo", auto="organization-title") + '</div>'
               + _field("empresa", "Empresa", auto="organization")
               + '<div class="row2">' + _field("email", "Email laboral", "email", "email") + _field("whatsapp", "WhatsApp / teléfono", "tel", "tel") + '</div>'
               + '<div class="row2">' + _select("facturacion", "Facturación anual aproximada", FACTURACION_EMPRESA) + _select("provincia", "Provincia principal", PROVINCIAS) + '</div>'
               + '<label for="f-mensaje">Contanos el caso (opcional)</label><textarea id="f-mensaje" name="mensaje" maxlength="1200"></textarea>'
               + honeypot + _consent() + submit + '</form>')
    return f'''<div class="tool" id="diagnostico" data-diag data-email="{C.EMAIL_CONTACTO}">
<div class="stepinfo"><span class="d-num">Paso 1 de 4</span><span>Gratis · 2 minutos</span></div>
<div class="bar"><i></i></div>
<h2 class="d-title" style="margin:0 0 14px;font-size:24px">¿Para quién es la consulta?</h2>
<div class="d-body"><noscript><p>Para hacer el diagnóstico necesitás JavaScript activado. También podés escribirnos a <a href="mailto:{C.EMAIL_CONTACTO}">{C.EMAIL_CONTACTO}</a>.</p></noscript></div>
<button type="button" class="d-back" hidden style="background:none;border:0;padding:12px 0 0;font:inherit;color:var(--muted);cursor:pointer;min-height:44px">← Volver</button>
<template id="tpl-form-persona">{persona}</template>
<template id="tpl-form-empresa">{empresa}</template>
</div>'''


def quiz(qid, title, questions, levels, cta_href, cta_label, invert=False):
    rows = "".join(
        f'<div class="qrow" data-w="{w}"><span>{q}</span><span class="yn">'
        f'<button type="button" class="btn sm sec" data-v="1" aria-pressed="false">Sí</button>'
        f'<button type="button" class="btn sm sec" data-v="0" aria-pressed="false">No</button></span></div>'
        for q, w in questions)
    return (f'<div class="tool" id="{qid}" data-quiz data-levels=\'{esc(json.dumps(levels, ensure_ascii=False))}\' '
            f'data-cta="{cta_href}"{" data-invert" if invert else ""} data-cta-label="{esc(cta_label)}"><h2 style="margin:0 0 8px;font-size:23px">{title}</h2>{rows}'
            f'<button type="button" class="btn q-go" style="margin-top:14px">Ver mi resultado</button>'
            f'<div class="result" hidden aria-live="polite"></div></div>')


def mono_table():
    rows = "".join(
        f'<tr><th scope="row">{c["cat"]}</th><td class="num">{money(c["tope"], True)}</td>'
        f'<td class="num">{money(c["servicios"], True)}</td><td class="num">{money(c["venta"], True)}</td></tr>'
        for c in MONO["categorias"])
    return (f'<div class="tbl"><table><caption>Valores vigentes {MONO["vigencia_texto"]}. Fuente: ARCA. '
            f'La cuota incluye impuesto integrado, aporte jubilatorio (SIPA) y obra social.</caption>'
            f'<thead><tr><th>Categoría</th><th class="num">Ingresos brutos anuales hasta</th>'
            f'<th class="num">Cuota mensual servicios</th><th class="num">Cuota mensual venta de bienes</th></tr></thead>'
            f'<tbody>{rows}</tbody></table></div>')


def mono_json():
    data = {"categorias": MONO["categorias"]}
    return f'<script type="application/json" id="mono-data">{json.dumps(data)}</script>'


def mono_calc():
    opts = '<option value="">No sé / no aplica</option>' + "".join(f'<option value="{c["cat"]}">Categoría {c["cat"]}</option>' for c in MONO["categorias"])
    return f'''<form class="tool" id="calc-mono" novalidate>
<h2 style="margin:0 0 4px;font-size:23px">Calculadora: ¿qué categoría te corresponde?</h2>
<p style="margin:0;color:var(--muted)">Con la tabla vigente {MONO["vigencia_texto"]}.</p>
<label for="ingresos">Lo que facturaste en los últimos 12 meses (en pesos)</label>
<input id="ingresos" type="text" inputmode="numeric" placeholder="Ej.: 25.000.000" required>
<div class="row2"><div><label for="tipo">Actividad</label><select id="tipo"><option value="servicios">Servicios</option><option value="venta">Venta de bienes</option></select></div>
<div><label for="actual">Tu categoría actual</label><select id="actual">{opts}</select></div></div>
<button class="btn" type="submit" style="margin-top:16px">Calcular</button>
<div class="result" hidden aria-live="polite"></div>
</form>{mono_json()}'''


def table(headers, rows, caption=""):
    th = "".join(f"<th>{h}</th>" for h in headers)
    tr = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    cap = f"<caption>{caption}</caption>" if caption else ""
    return f'<div class="tbl"><table>{cap}<thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table></div>'


ARCA = ("ARCA (ex AFIP)", "https://www.arca.gob.ar/")
ARCA_MONO = ("ARCA — Monotributo", "https://www.arca.gob.ar/monotributo/")
ARCA_CAT = ("ARCA — Categorías del Monotributo", "https://www.arca.gob.ar/monotributo/categorias.asp")
ARCA_EXCL = ("ARCA — Exclusión del Monotributo", "https://www.arca.gob.ar/monotributo/ayuda/exclusion.asp")
LEY_MONO = ("Ley 24.977 (Régimen Simplificado), texto actualizado", "https://www.argentina.gob.ar/normativa/nacional/ley-24977-51609")
COMARB = ("Comisión Arbitral del Convenio Multilateral", "https://www.ca.gob.ar/")
IGJ = ("Inspección General de Justicia", "https://www.argentina.gob.ar/justicia/igj")
LGS = ("Ley General de Sociedades 19.550", "https://www.argentina.gob.ar/normativa/nacional/ley-19550-25553")
BO = ("Boletín Oficial de la República Argentina", "https://www.boletinoficial.gob.ar/")
AAIP = ("Agencia de Acceso a la Información Pública — Datos personales", "https://www.argentina.gob.ar/aaip/datospersonales")
