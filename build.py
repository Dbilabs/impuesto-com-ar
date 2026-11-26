#!/usr/bin/env python3
"""Genera el sitio estático en ./dist. Uso: python3 build.py"""
import hashlib
import html as H
import json
import re
import shutil
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).parent
SRC = ROOT / "src"
DIST = ROOT / "dist"
sys.path.insert(0, str(SRC))

import config as C  # noqa: E402
from lib import esc  # noqa: E402
from pages import general, personas, empresas, ri, secciones, integraciones  # noqa: E402

PAGES = general.PAGES + ri.PAGES + secciones.PAGES + empresas.PAGES + personas.PAGES + integraciones.PAGES
BY_PATH = {p["path"]: p for p in PAGES}
CSS = (SRC / "assets" / "style.css").read_text(encoding="utf-8")
CSS = re.sub(r"\s*\n\s*", "", CSS)
JS = (SRC / "assets" / "app.js").read_text(encoding="utf-8")
JS_NAME = "app." + hashlib.sha1(JS.encode()).hexdigest()[:10] + ".js"
EXTRA_JS = {}
for f in ["iva.js", "iva-cuenta.js"]:
    t = (SRC / "assets" / f).read_text(encoding="utf-8")
    EXTRA_JS[f] = (f.replace(".js", "." + hashlib.sha1(t.encode()).hexdigest()[:10] + ".js"), t)
ORG_ID = C.SITE_URL + "/#org"
SITE_ID = C.SITE_URL + "/#website"

LOGO_SVG = ('<svg width="30" height="30" viewBox="0 0 32 32" aria-hidden="true"><rect width="32" height="32" rx="8" fill="#0B6E4F"/>'
            '<path d="M9 17l4 4 10-10" stroke="#fff" stroke-width="3" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>')
FAVICON = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="8" fill="#0B6E4F"/>'
           '<path d="M9 17l4 4 10-10" stroke="#fff" stroke-width="3" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>')


def url(path):
    return C.SITE_URL + path


def slug(s):
    s = unicodedata.normalize("NFKD", re.sub(r"<[^>]+>", "", s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:60]


def strip_tags(s):
    s = re.sub(r"<(script|style|template|noscript)[^>]*>.*?</\1>", " ", s, flags=re.S)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", H.unescape(s)).strip()


def human_date(iso):
    meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
    y, m, d = iso.split("-")
    return f"{int(d)} de {meses[int(m) - 1]} de {y}"


# ---------------------------------------------------------------- schema
def org_schema():
    o = {"@type": "Organization", "@id": ORG_ID, "name": C.SITE_NAME, "url": C.SITE_URL + "/",
         "logo": {"@type": "ImageObject", "url": url("/logo-512.png"), "width": 512, "height": 512},
         "email": C.EMAIL_CONTACTO, "areaServed": {"@type": "Country", "name": "Argentina"},
         "description": "Sitio informativo sobre impuestos en Argentina que conecta personas y empresas con estudios contables aliados."}
    if C.SAME_AS:
        o["sameAs"] = C.SAME_AS
    return o


def person_schema():
    r = C.REVISOR
    if not r:
        return None
    p = {"@type": "Person", "@id": C.SITE_URL + "/quienes-somos/#revisor", "name": r["nombre"], "jobTitle": r.get("titulo", "Contador Público"),
         "description": r.get("bio", ""), "url": url("/quienes-somos/"),
         "hasCredential": {"@type": "EducationalOccupationalCredential", "credentialCategory": "Matrícula profesional", "name": r.get("matricula", "")}}
    if r.get("linkedin"):
        p["sameAs"] = [r["linkedin"]]
    return p


def page_schema(p):
    graph = []
    canonical = url(p["path"])
    crumbs = p.get("crumbs", [])
    if p["path"] == "/":
        graph.append(org_schema())
        graph.append({"@type": "WebSite", "@id": SITE_ID, "url": C.SITE_URL + "/", "name": C.SITE_NAME, "inLanguage": C.LANG,
                      "publisher": {"@id": ORG_ID}, "description": p["description"]})
    kind = p.get("kind", "article")
    base = {"@id": canonical + "#page", "url": canonical, "name": p["title"], "description": p["description"], "inLanguage": C.LANG,
            "isPartOf": {"@id": SITE_ID}, "dateModified": p.get("updated", C.UPDATED)}
    if kind == "article":
        author = person_schema() or {"@id": ORG_ID}
        art = dict(base, **{"@type": "Article", "headline": p["h1"][:110], "datePublished": p.get("published", C.UPDATED),
                            "author": author, "publisher": {"@id": ORG_ID}, "mainEntityOfPage": canonical,
                            "image": url("/og/default.png")})
        if C.REVISOR:
            art["reviewedBy"] = {"@id": C.SITE_URL + "/quienes-somos/#revisor"}
        if p.get("about"):
            art["about"] = [{"@type": "Thing", "name": a} for a in p["about"]]
        graph.append(art)
    else:
        graph.append(dict(base, **{"@type": "WebPage" if kind != "about" else "AboutPage"}))
    if crumbs:
        items = [{"@type": "ListItem", "position": 1, "name": "Inicio", "item": C.SITE_URL + "/"}]
        for i, (n, path) in enumerate(crumbs, start=2):
            items.append({"@type": "ListItem", "position": i, "name": n, "item": url(path)})
        graph.append({"@type": "BreadcrumbList", "itemListElement": items})
    if p.get("faqs"):
        graph.append({"@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": strip_tags(a)}} for q, a in p["faqs"]]})
    graph += p.get("schema", [])
    return json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


# ---------------------------------------------------------------- layout
NAV = [("/iva/", "IVA"), ("/iibb/", "Ingresos Brutos"), ("/ganancias/", "Ganancias"), ("/retenciones/", "Retenciones"),
       ("/empresas/", "Empresas"), ("/integraciones/", "Integraciones"), ("/herramientas/", "Herramientas")]


def head(p):
    full = f'{p["title"]} | {C.SITE_NAME}'
    title = p["title"] if p["path"] == "/" or len(full) > 65 else full
    canonical = url(p["path"])
    robots = "noindex, follow" if p.get("noindex") else "index, follow, max-image-preview:large, max-snippet:-1, max-video-preview:-1"
    og_type = "article" if p.get("kind", "article") == "article" else "website"
    extra = ""
    if C.GOOGLE_SITE_VERIFICATION:
        extra += f'<meta name="google-site-verification" content="{C.GOOGLE_SITE_VERIFICATION}">'
    if C.BING_SITE_VERIFICATION:
        extra += f'<meta name="msvalidate.01" content="{C.BING_SITE_VERIFICATION}">'
    if og_type == "article":
        extra += f'<meta property="article:modified_time" content="{p.get("updated", C.UPDATED)}T09:00:00-03:00">'
    return f'''<!doctype html>
<html lang="{C.LANG}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(p["description"])}">
<link rel="canonical" href="{canonical}">
<meta name="robots" content="{robots}">
<link rel="alternate" hreflang="es-AR" href="{canonical}">
<link rel="alternate" hreflang="x-default" href="{canonical}">
<meta property="og:locale" content="{C.LOCALE}">
<meta property="og:site_name" content="{C.SITE_NAME}">
<meta property="og:type" content="{og_type}">
<meta property="og:title" content="{esc(p.get("og_title", p["title"]))}">
<meta property="og:description" content="{esc(p["description"])}">
<meta property="og:url" content="{canonical}">
<meta property="og:image" content="{url("/og/default.png")}">
<meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="#0B6E4F">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="manifest" href="/site.webmanifest">
{extra}
<style>{CSS}</style>
<script type="application/ld+json">{page_schema(p)}</script>
</head>'''


def header():
    nav = "".join(f'<a href="{h}">{t}</a>' for h, t in NAV)
    name_prefix, _, name_suffix = C.SITE_NAME.partition(".")
    suffix_html = f"<span>.{name_suffix}</span>" if name_suffix else ""
    return f'''<body>
<a class="skip" href="#contenido">Saltar al contenido</a>
<header class="hdr"><div class="wrap">
<a class="logo" href="/" aria-label="{C.SITE_NAME}, inicio">{LOGO_SVG}<span style="color:var(--ink)">{name_prefix}{suffix_html}</span></a>
<nav class="nav" aria-label="Principal">{nav}</nav>
<a class="btn sm" href="/diagnostico/">Diagnóstico gratis</a>
</div></header>'''


def footer(p=None):
    cols = [
        ("Impuestos", [("/iva/", "IVA del mes (automático)"), ("/iibb/", "Ingresos Brutos y Convenio"), ("/ganancias/", "Ganancias y anticipos"),
                       ("/retenciones/", "Retenciones y percepciones"), ("/calendario-fiscal/", "Vencimientos")]),
        ("Responsables inscriptos", [ ("/responsables-inscriptos/", "Guía del responsable inscripto"),
                      ("/monotributo/monotributo-o-responsable-inscripto/", "Pasar de monotributo a RI"), ("/contador/cuanto-cobra-un-contador/", "Cuánto cobra un contador")]),
        ("Monotributo", [("/monotributo/categorias/", "Categorías del monotributo"), ("/monotributo/recategorizacion/", "Recategorización"),
                      ("/monotributo/exclusion/", "Exclusión del monotributo"), ("/contador/tu-contador-lo-hace-bien/", "¿Tu contador lo hace bien?"),
                      ("/contador/cuanto-cobra-un-contador/", "Cuánto cobra un contador")]),
        ("Empresas", [("/empresas/saldos-a-favor/", "Saldos a favor"), ("/empresas/auditoria-de-estados-contables/", "Auditoría de estados contables"),
                      ("/empresas/fiscalizacion-arca/", "Fiscalización de ARCA"), ("/empresas/convenio-multilateral/", "Convenio Multilateral"),
                      ("/empresas/precios-de-transferencia/", "Precios de transferencia")]),
        ("El sitio", [("/estudios/", "Para Estudios Contables"), ("/whatsapp/", "Conectar WhatsApp"),
                      ("/quienes-somos/", "Quiénes somos"), ("/metodologia-editorial/", "Metodología editorial"),
                      ("/privacidad/", "Política de privacidad"), ("/terminos/", "Términos y condiciones")]),
    ]
    html = "".join(f'<div><h4>{t}</h4><ul>' + "".join(f'<li><a href="{h}">{n}</a></li>' for h, n in links) + '</ul></div>' for t, links in cols)
    extra = "".join(f'<script src="/assets/{EXTRA_JS[x][0]}" defer></script>' for x in (p or {}).get("scripts", []))
    analytics = ""
    if C.CF_ANALYTICS_TOKEN:
        analytics = (f'<script defer src="https://static.cloudflareinsights.com/beacon.min.js" '
                     f'data-cf-beacon=\'{{"token": "{C.CF_ANALYTICS_TOKEN}"}}\'></script>')
    return f'''<footer class="ftr"><div class="wrap">
<div class="fcols">{html}</div>
<p>El contenido es informativo y cuenta con opción de revisión por contador público matriculado (Human-in-the-Loop). El diagnóstico no te pide la clave fiscal; el <a href="/iva/seguridad/">IVA automático</a> la usa solo con tu autorización y cifrada. Tus datos se tratan según la Ley 25.326.</p>
<p>© 2026 {C.SITE_NAME} · <a href="mailto:{C.EMAIL_CONTACTO}">{C.EMAIL_CONTACTO}</a></p>
</div></footer>
<script src="/assets/{JS_NAME}" defer></script>{extra}{analytics}
</body></html>'''


def crumbs_html(p):
    if not p.get("crumbs"):
        return ""
    items = '<li><a href="/">Inicio</a></li>'
    for i, (n, path) in enumerate(p["crumbs"]):
        last = i == len(p["crumbs"]) - 1
        items += f'<li aria-current="page">{n}</li>' if last else f'<li><a href="{path}">{n}</a></li>'
    return f'<nav class="crumbs wrap" aria-label="Ruta de navegación"><ol>{items}</ol></nav>'


def add_ids(body):
    toc = []

    def rep(m):
        attrs, inner = m.group(1), m.group(2)
        if "id=" in attrs:
            return m.group(0)
        i = slug(inner)
        toc.append((i, strip_tags(inner)))
        return f'<h2{attrs} id="{i}">{inner}</h2>'
    body = re.sub(r"<h2([^>]*)>(.*?)</h2>", rep, body, flags=re.S)
    return body, toc


def byline(p):
    r = C.REVISOR
    upd = human_date(p.get("updated", C.UPDATED))
    if r:
        who = (f'<strong>Revisado por {esc(r["nombre"])}</strong>, {esc(r.get("titulo", "Contador Público"))} · {esc(r.get("matricula", ""))}'
               f'<br><span class="src">Última revisión: {upd}. <a href="/metodologia-editorial/">Cómo revisamos el contenido</a>.</span>')
        ini = "".join(w[0] for w in r["nombre"].split()[:2])
    else:
        who = (f'<strong>Equipo editorial de {C.SITE_NAME}</strong><br><span class="src">Última actualización: {upd}. '
               f'Basado en normativa y publicaciones oficiales. <a href="/metodologia-editorial/">Cómo elaboramos el contenido</a>.</span>')
        ini = "i"
    return f'<div class="byline"><div class="av" aria-hidden="true">{ini}</div><div>{who}</div></div>'


def article(p):
    body, toc = add_ids(p["body"])
    upd = human_date(p.get("updated", C.UPDATED))
    reviewer = f'Revisado por {esc(C.REVISOR["nombre"])}' if C.REVISOR else f"Equipo editorial de {C.SITE_NAME}"
    words = len(strip_tags(p["body"]).split())
    meta = f'<div class="meta"><span>Actualizado: <time datetime="{p.get("updated", C.UPDATED)}">{upd}</time></span><span>{reviewer}</span><span>{max(2, round(words / 220))} min de lectura</span></div>'
    plain = p.get("kind") in ("page", "about")
    if plain:
        meta = ""
    answer = f'<div class="answer"><strong>Respuesta rápida</strong>{p["answer"]}</div>' if p.get("answer") else ""
    faqs = ""
    if p.get("faqs"):
        faqs = '<section class="faq"><h2 id="preguntas-frecuentes">Preguntas frecuentes</h2>' + "".join(
            f'<details><summary>{q}</summary><p>{a}</p></details>' for q, a in p["faqs"]) + '</section>'
        toc.append(("preguntas-frecuentes", "Preguntas frecuentes"))
    src = ""
    if p.get("sources"):
        src = '<h2 id="fuentes" style="font-size:20px">Fuentes</h2><ul class="src">' + "".join(
            f'<li><a href="{u}" rel="noopener" target="_blank">{n}</a></li>' for n, u in p["sources"]) + '</ul>'
    rel = ""
    if p.get("related"):
        rel = '<nav class="related" aria-label="Relacionados"><h2 style="font-size:20px">Seguí leyendo</h2><ul>' + "".join(
            f'<li><a href="{r}">{BY_PATH[r]["h1"]}</a></li>' for r in p["related"] if r in BY_PATH) + '</ul></nav>'
    side_cta = p.get("side_cta") or ("persona", None, "¿Querés que un contador revise tu caso?", "Diagnóstico gratis en 2 minutos. Sin compromiso y sin pedirte la clave fiscal.")
    tocs = ""
    if len(toc) >= 3:
        tocs = '<nav class="tool" aria-label="En esta página" style="margin:0 0 18px;padding:18px 20px"><strong style="font-size:15px">En esta página</strong><ul style="padding-left:18px;margin:8px 0 0;font-size:15px">' + "".join(
            f'<li><a href="#{i}">{t}</a></li>' for i, t in toc) + '</ul></nav>'
    from lib import cta
    return f'''{crumbs_html(p)}
<div class="wrap layout" id="contenido">
<main class="main">
<article>
<h1>{p["h1"]}</h1>
{meta}
{answer}
{body}
{faqs}
{"" if plain else byline(p)}
{src}
</article>
{rel}
</main>
<aside class="side">{tocs}{cta(side_cta[0], side_cta[1], side_cta[2], side_cta[3], inline=False, tag="h2")}</aside>
</div>'''


def render(p):
    if p.get("kind") == "custom":
        main = crumbs_html(p) + f'<main id="contenido">{p["body"]}</main>'
    else:
        main = article(p)
    return head(p) + header() + main + footer(p)


# ---------------------------------------------------------------- build
def build():
    if DIST.exists():
        shutil.rmtree(DIST)
    (DIST / "assets").mkdir(parents=True)
    (DIST / "assets" / JS_NAME).write_text(JS, encoding="utf-8")
    for name, txt in EXTRA_JS.values():
        (DIST / "assets" / name).write_text(txt, encoding="utf-8")
    for p in PAGES:
        out = DIST / p["path"].strip("/") / "index.html" if p["path"] != "/" else DIST / "index.html"
        if p["path"] == "/404/":
            out = DIST / "404.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render(p), encoding="utf-8")

    indexable = [p for p in PAGES if not p.get("noindex")]
    # sitemap
    sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for p in indexable:
        sm.append(f'<url><loc>{url(p["path"])}</loc><lastmod>{p.get("updated", C.UPDATED)}</lastmod></url>')
    sm.append("</urlset>")
    (DIST / "sitemap.xml").write_text("\n".join(sm), encoding="utf-8")

    # robots: buscadores y motores de IA explícitamente habilitados
    bots = ["Googlebot", "Bingbot", "OAI-SearchBot", "ChatGPT-User", "GPTBot", "ClaudeBot", "Claude-SearchBot", "Claude-User",
            "PerplexityBot", "Perplexity-User", "Google-Extended", "Applebot", "Applebot-Extended", "DuckAssistBot", "Meta-ExternalAgent", "CCBot"]
    robots = "# Buscadores y asistentes de IA: bienvenidos.\n"
    robots += "".join(f"User-agent: {b}\nAllow: /\nDisallow: /api/\n\n" for b in bots)
    robots += f"User-agent: *\nAllow: /\nDisallow: /api/\nDisallow: /gracias/\n\nSitemap: {url('/sitemap.xml')}\n"
    (DIST / "robots.txt").write_text(robots, encoding="utf-8")

    # llms.txt (resumen para LLMs) + llms-full.txt (texto completo)
    groups = {"Empresas: impuestos y auditoría": empresas.PAGES, "Responsables inscriptos e IVA": ri.PAGES, "Ingresos Brutos, Ganancias y Retenciones": secciones.PAGES, "Monotributo y contador": personas.PAGES,
              "General": [p for p in general.PAGES if not p.get("noindex")]}
    llms = [f"# {C.SITE_NAME}", "", f"> {C.SITE_TAGLINE}. Guías actualizadas sobre impuestos en Argentina (Monotributo, ARCA, Ingresos Brutos, "
            "auditoría, precios de transferencia) y diagnóstico gratuito que conecta a personas y empresas con estudios contables aliados.", "",
            f"Última actualización: {C.UPDATED}. Las cifras citan su vigencia y su fuente oficial.", ""]
    for g, ps in groups.items():
        llms.append(f"## {g}")
        llms += [f"- [{p['h1']}]({url(p['path'])}): {p['description']}" for p in ps if not p.get("noindex")]
        llms.append("")
    (DIST / "llms.txt").write_text("\n".join(llms), encoding="utf-8")
    full = [f"# {C.SITE_NAME} — contenido completo", f"Actualizado: {C.UPDATED}", ""]
    for p in indexable:
        if p.get("kind") in ("custom",) and p["path"] != "/":
            continue
        full += [f"## {p['h1']}", f"URL: {url(p['path'])}", ""]
        if p.get("answer"):
            full += [strip_tags(p["answer"]), ""]
        full += [strip_tags(p["body"]), ""]
        for q, a in p.get("faqs", []):
            full += [f"P: {q}", f"R: {strip_tags(a)}", ""]
    (DIST / "llms-full.txt").write_text("\n".join(full), encoding="utf-8")

    # Cloudflare Pages: cabeceras y redirecciones
    (DIST / "_headers").write_text(f"""/*
  X-Content-Type-Options: nosniff
  Referrer-Policy: strict-origin-when-cross-origin
  Permissions-Policy: camera=(), microphone=(), geolocation=()
  Strict-Transport-Security: max-age=31536000; includeSubDomains
  X-Frame-Options: DENY
  Content-Security-Policy: default-src 'self'; script-src 'self' https://static.cloudflareinsights.com; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' https://cloudflareinsights.com; form-action 'self'; base-uri 'self'; frame-ancestors 'none'
/iva/mi-cuenta/*
  X-Robots-Tag: noindex
  Referrer-Policy: no-referrer
/api/*
  Cache-Control: no-store
/assets/*
  Cache-Control: public, max-age=31536000, immutable
/og/*
  Cache-Control: public, max-age=604800
/llms.txt
  Content-Type: text/plain; charset=utf-8
/llms-full.txt
  Content-Type: text/plain; charset=utf-8
/gracias/*
  X-Robots-Tag: noindex
""", encoding="utf-8")
    (DIST / "_redirects").write_text("""/monotributo/categorias-y-cuotas /monotributo/categorias/ 301
/calculadora-monotributo /monotributo/categorias/ 301
/auditoria /empresas/auditoria-de-estados-contables/ 301
/vencimientos /calendario-fiscal/ 301
/contacto /diagnostico/ 301
""", encoding="utf-8")
    (DIST / "favicon.svg").write_text(FAVICON, encoding="utf-8")
    (DIST / "site.webmanifest").write_text(json.dumps({"name": C.SITE_NAME, "short_name": C.SITE_NAME.split(".")[0], "start_url": "/", "display": "browser",
                                                       "theme_color": "#0B6E4F", "background_color": "#F6F7F9",
                                                       "icons": [{"src": "/logo-512.png", "sizes": "512x512", "type": "image/png"}]}), encoding="utf-8")
    (DIST / f"{C.INDEXNOW_KEY}.txt").write_text(C.INDEXNOW_KEY, encoding="utf-8")
    # Imágenes (OG, logo) generadas por scripts/images.py y guardadas en src/static
    static = SRC / "static"
    if static.exists():
        shutil.copytree(static, DIST, dirs_exist_ok=True)
    print(f"OK: {len(PAGES)} páginas, {len(indexable)} indexables → {DIST}")


if __name__ == "__main__":
    build()
