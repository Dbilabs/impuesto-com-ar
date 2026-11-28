#!/usr/bin/env python3
"""
scripts/medir_poc_http.py
Script de medición segura para la PoC Fase 3.2 (20 corridas x 3 CUITs propios del equipo).

NOTA: Este script vive en `scripts/` y se corre desde el repositorio local (NO desde la imagen Docker).
Requiere credenciales SOLO de CUITs propios del equipo vía archivo JSON local (permisos 0600).

Guardas anti-bloqueo de Clave Fiscal (M1):
  - Corta inmediatamente el CUIT ante cualquier `ClaveIncorrecta` (incluido captcha) o `LoginNoConfirmado`.
  - Tope duro de 2 fallos post-contraseña por CUIT (`MAX_POST_PW_FAILS_PER_CUIT = 2`).
  - Pausa configurable `--pausa-seg` entre corridas (default: 30 s).
  - Aborta TODA la medición si se acumulan 2 captchas globales.

Paridad de importes (M2):
  - Compara los importes extraídos del HTML HTTP contra una corrida de Playwright del mismo CUIT
    en la misma ventana e informa `paridad_pct`.
  - Criterio de Go: éxito >= 95 %, paridad == 100 %, p95 < 10 s y RSS < 80 MB.
"""

import argparse
import json
import resource
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.arca_errors import ClaveIncorrecta, LoginNoConfirmado
from bot.poc_http.arca_http import ArcaHttpClient, is_http_login_enabled

MAX_POST_PW_FAILS_PER_CUIT = 2
MAX_CAPTCHAS_GLOBAL = 2


def _rss_mb() -> float:
    ru = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return round(ru / (1024 * 1024), 2)
    return round(ru / 1024, 2)


def _p95(values: List[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = min(len(s) - 1, max(0, int(len(s) * 0.95 + 0.9999) - 1))
    return round(s[idx], 3)


def _comparar_importes(http_imp: Dict[str, Any], pw_imp: Dict[str, Any], servicio: str) -> bool:
    key = {"ccma": "total_saldo_deudor", "mis_facilidades": "planes_vigentes", "sct": "deuda_sct"}.get(servicio)
    if not key:
        return False
    v_h = http_imp.get(key)
    v_p = pw_imp.get(key)
    if v_h is None or v_p is None:
        return False
    if isinstance(v_h, (int, float)) and isinstance(v_p, (int, float)):
        return abs(float(v_h) - float(v_p)) < 0.01
    return v_h == v_p


def ejecutar_medicion(
    creds: List[Dict[str, str]],
    *,
    corridas: int = 20,
    servicio: str = "ccma",
    pausa_seg: float = 30.0,
    transport=None,
    playwright_fn: Optional[Callable[[str, str, str], Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    if not is_http_login_enabled():
        raise RuntimeError("Ejecutá con ARCA_HTTP_LOGIN=1.")
    client = ArcaHttpClient(require_flag=True, transport=transport)
    tiempos: List[float] = []
    ok_count = 0
    captchas_global = 0
    abortado_por_captchas = False
    errores: List[str] = []
    paridad_total = 0
    paridad_ok = 0

    for item in creds:
        if abortado_por_captchas:
            break
        cuit = "".join(c for c in str(item["cuit"]) if c.isdigit())
        clave = str(item["clave"])
        fallos_post_pw = 0
        pw_baseline: Optional[Dict[str, Any]] = None
        if playwright_fn is not None:
            try:
                pw_baseline = playwright_fn(cuit, clave, servicio)
            except Exception as exc:
                errores.append(f"{cuit[:4]}***[pw_baseline]: {type(exc).__name__}")

        for i in range(corridas):
            if fallos_post_pw >= MAX_POST_PW_FAILS_PER_CUIT:
                break
            if i > 0 and pausa_seg > 0:
                time.sleep(pausa_seg)
            t0 = time.perf_counter()
            try:
                res = client.autenticar_y_abrir_servicio(cuit=cuit, clave=clave, servicio=servicio)
                if res.get("ok"):
                    ok_count += 1
                    if pw_baseline is not None:
                        paridad_total += 1
                        if _comparar_importes(res.get("importes_extraidos") or {}, pw_baseline, servicio):
                            paridad_ok += 1
            except ClaveIncorrecta as exc:
                fallos_post_pw += 1
                if exc.captcha:
                    captchas_global += 1
                errores.append(f"{cuit[:4]}***: ClaveIncorrecta(captcha={exc.captcha})")
                if captchas_global >= MAX_CAPTCHAS_GLOBAL:
                    abortado_por_captchas = True
                # M1: cortar SIEMPRE este CUIT ante cualquier ClaveIncorrecta (incluido captcha)
                break
            except LoginNoConfirmado:
                fallos_post_pw += 1
                errores.append(f"{cuit[:4]}***: LoginNoConfirmado")
                # M1: cortar este CUIT ante LoginNoConfirmado para proteger la Clave Fiscal
                break
            except Exception as exc:
                errores.append(f"{cuit[:4]}***: {type(exc).__name__}")
            finally:
                tiempos.append(time.perf_counter() - t0)

    total = len(tiempos)
    tasa_exito = round((ok_count / total) * 100.0, 2) if total else 0.0
    paridad_pct = round((paridad_ok / paridad_total) * 100.0, 2) if paridad_total else None
    p95_seg = _p95(tiempos)
    rss_peak_mb = _rss_mb()
    cumple_go = bool(
        not abortado_por_captchas
        and tasa_exito >= 95.0
        and paridad_pct == 100.0
        and p95_seg < 10.0
        and rss_peak_mb < 80.0
    )
    return {
        "servicio": servicio,
        "cuits_evaluados": len(creds),
        "corridas_totales": total,
        "exitos": ok_count,
        "tasa_exito_pct": tasa_exito,
        "paridad_evaluaciones": paridad_total,
        "paridad_pct": paridad_pct,
        "captchas": captchas_global,
        "abortado_por_captchas": abortado_por_captchas,
        "p50_seg": round(statistics.median(tiempos), 3) if tiempos else 0.0,
        "p95_seg": p95_seg,
        "rss_peak_mb": rss_peak_mb,
        "errores_muestra": errores[:10],
        "cumple_go": cumple_go,
    }


def _playwright_baseline_default(cuit: str, clave: str, servicio: str) -> Dict[str, Any]:
    from bot.auditoria_unificada import auditar_estado_integral_arca
    res = auditar_estado_integral_arca(cuit=cuit, clave=clave)
    if servicio == "ccma":
        return {"total_saldo_deudor": (res.get("ccma") or {}).get("total_saldo_deudor")}
    if servicio == "mis_facilidades":
        planes = (res.get("mis_facilidades") or {}).get("planes") or []
        return {"planes_vigentes": len(planes)}
    if servicio == "sct":
        return {"deuda_sct": (res.get("sct") or {}).get("deuda_sct")}
    return {}


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark PoC HTTP ARCA (Fase 3.2 — M1/M2).")
    parser.add_argument("--creds-json", required=True, help='JSON local (0600): [{"cuit": "...", "clave": "..."}] (solo CUITs propios del equipo)')
    parser.add_argument("--corridas", type=int, default=20, help="Corridas por CUIT (default: 20)")
    parser.add_argument("--pausa-seg", type=float, default=30.0, help="Pausa en segundos entre corridas (default: 30)")
    parser.add_argument("--servicio", default="ccma", choices=["ccma", "mis_facilidades", "sct"])
    parser.add_argument("--sin-playwright", action="store_true", help="Omitir comparación contra Playwright (paridad_pct=None, cumple_go=False)")
    args = parser.parse_args()

    creds = json.loads(Path(args.creds_json).read_text(encoding="utf-8"))
    pw_fn = None if args.sin_playwright else _playwright_baseline_default
    res = ejecutar_medicion(creds, corridas=args.corridas, servicio=args.servicio, pausa_seg=args.pausa_seg, playwright_fn=pw_fn)
    print(json.dumps(res, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
