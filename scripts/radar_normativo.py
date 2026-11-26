#!/usr/bin/env python3
"""
scripts/radar_normativo.py
Radar Normativo Automático (ARCA / Boletín Oficial / Jurisdicciones).

Se ejecuta diariamente vía GitHub Actions (.github/workflows/radar_normativo_diario.yml)
para detectar resoluciones generales, cambios de escalas/topes, moratorias y circulares,
actualizando data/radar_normativo.json y prompts-maestros/05-radar-normativo-vigente.md.
"""

import json
import datetime
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_JSON = ROOT / "data" / "radar_normativo.json"
OUT_MD = ROOT / "prompts-maestros" / "05-radar-normativo-vigente.md"

SOURCES = [
    ("ARCA Novedades", "https://www.arca.gob.ar/noticias/rss.xml"),
    ("Boletín Oficial - Legislación", "https://www.boletinoficial.gob.ar/rss/primera"),
]

KEYWORDS = [
    "arca", "afip", "monotributo", "ganancias", "bienes personales", "iva",
    "autonomos", "autónomos", "facilidades", "mipyme", "siradig", "f. 931",
    "retenciones", "percepciones", "agip", "arba", "convenio multilateral",
    "sifere", "sircreb", "sirtac", "moratoria", "blanqueo", "resolucion general",
    "resolución general", "recategorizacion", "recategorización", "factura electronica"
]


def fetch_rss(name: str, url: str):
    items = []
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "impuesto.com.ar-radar/1.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            xml_bytes = r.read()
        root = ET.fromstring(xml_bytes)
        for item in root.findall(".//item")[:40]:
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            pub = (item.findtext("pubDate") or "").strip()
            desc = (item.findtext("description") or "").strip()
            haystack = f"{title} {desc}".lower()
            if any(k in haystack for k in KEYWORDS):
                items.append({
                    "fuente": name,
                    "titulo": title,
                    "fecha": pub,
                    "url": link,
                })
    except Exception as e:
        items.append({"fuente": name, "error": str(e)[:120]})
    return items


def main():
    hoy = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    all_items = []
    for name, url in SOURCES:
        all_items.extend(fetch_rss(name, url))

    valid = [x for x in all_items if "titulo" in x][:15]
    payload = {
        "actualizado": hoy,
        "total_detectadas": len(valid),
        "novedades": valid,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        f"# Radar Normativo Vigente (actualizado {hoy})",
        "",
        "Novedades fiscales recientes detectadas automáticamente en fuentes oficiales (ARCA / Boletín Oficial):",
        "",
    ]
    if valid:
        for it in valid[:10]:
            lines.append(f"- **[{it['fuente']}]** {it['titulo']} ({it['fecha']}) — {it['url']}")
    else:
        lines.append("- Sin nuevas resoluciones fiscales relevantes en el último barrido; verificar siempre escalas vigentes en `https://www.arca.gob.ar` y jurisdicciones locales (AGIP/ARBA/COMARB).")

    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"✅ Radar normativo actualizado ({hoy}): {len(valid)} novedades fiscales.")


if __name__ == "__main__":
    main()
