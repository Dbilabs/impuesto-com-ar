#!/usr/bin/env python3
"""
scripts/medir_poc_http.py
Script de medición para la PoC Fase 3.2 (20 corridas x 3 CUITs propios del equipo).

NOTA: Este script vive en `scripts/` y se corre desde el repositorio local (NO desde la imagen Docker).
Requiere credenciales SOLO de CUITs propios del equipo vía variables de entorno o archivo JSON local
(NUNCA commitear credenciales ni loguear claves, cookies, token ni sign).

Criterio de Go (Fase 3.2):
  - Tasa de éxito >= 95 %
  - Paridad de importes contra Playwright = 100 % (Total Saldo Deudor, planes vigentes, deuda SCT)
  - p95 de tiempo < 10 s
  - Peak RSS < 80 MB

Uso:
  ARCA_HTTP_LOGIN=1 python3 scripts/medir_poc_http.py --creds-json /ruta/segura/cuits_equipo.json --corridas 20
"""

import argparse
import json
import os
import resource
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.poc_http.arca_http import ArcaHttpClient, is_http_login_enabled
from bot.arca_errors import ClaveIncorrecta


def _rss_mb() -> float:
    ru = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # macOS devuelve bytes; Linux devuelve KiB
    if sys.platform == "darwin":
        return round(ru / (1024 * 1024), 2)
    return round(ru / 1024, 2)


def _p95(values: List[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = min(len(s) - 1, max(0, int(len(s) * 0.95 + 0.9999) - 1))
    return round(s[idx], 3)


def ejecutar_medicion(creds: List[Dict[str, str]], corridas: int = 20, servicio: str = "ccma") -> Dict[str, Any]:
    if not is_http_login_enabled():
        raise RuntimeError("Ejecutá con ARCA_HTTP_LOGIN=1.")
    client = ArcaHttpClient(require_flag=True)
    tiempos: List[float] = []
    ok_count = 0
    captchas = 0
    errores: List[str] = []

    for item in creds:
        cuit = "".join(c for c in str(item["cuit"]) if c.isdigit())
        clave = str(item["clave"])
        for _ in range(corridas):
            t0 = time.perf_counter()
            try:
                res = client.autenticar_y_abrir_servicio(cuit=cuit, clave=clave, servicio=servicio)
                if res.get("ok"):
                    ok_count += 1
            except ClaveIncorrecta as exc:
                if exc.captcha:
                    captchas += 1
                errores.append(f"{cuit[:4]}***: {type(exc).__name__}")
                # Ante clave incorrecta o bloqueo, cortar inmediatamente para no bloquear la Clave Fiscal
                if not exc.captcha:
                    break
            except Exception as exc:
                errores.append(f"{cuit[:4]}***: {type(exc).__name__}")
            finally:
                tiempos.append(time.perf_counter() - t0)

    total = len(tiempos)
    tasa_exito = round((ok_count / total) * 100.0, 2) if total else 0.0
    p95_seg = _p95(tiempos)
    rss_peak_mb = _rss_mb()
    return {
        "servicio": servicio,
        "cuits_evaluados": len(creds),
        "corridas_totales": total,
        "exitos": ok_count,
        "tasa_exito_pct": tasa_exito,
        "captchas": captchas,
        "p50_seg": round(statistics.median(tiempos), 3) if tiempos else 0.0,
        "p95_seg": p95_seg,
        "rss_peak_mb": rss_peak_mb,
        "errores_muestra": errores[:10],
        "cumple_latencia_y_memoria": bool(tasa_exito >= 95.0 and p95_seg < 10.0 and rss_peak_mb < 80.0),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark PoC HTTP ARCA (Fase 3.2).")
    parser.add_argument("--creds-json", required=True, help='JSON local: [{"cuit": "...", "clave": "..."}] (solo CUITs propios del equipo)')
    parser.add_argument("--corridas", type=int, default=20, help="Corridas por CUIT (default: 20)")
    parser.add_argument("--servicio", default="ccma", choices=["ccma", "mis_facilidades", "sct"])
    args = parser.parse_args()

    creds = json.loads(Path(args.creds_json).read_text(encoding="utf-8"))
    res = ejecutar_medicion(creds, corridas=args.corridas, servicio=args.servicio)
    print(json.dumps(res, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
