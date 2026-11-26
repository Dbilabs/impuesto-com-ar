"""
bot/backoffice_growth.py
Backoffice SaaS & Growth Suite de nivel Enterprise para impuesto.com.ar (100% Super-Admin).

Módulos:
  1. FinOps & Growth Funnel (MRR, ARR, ARPU, conversión, DAU/WAU/MAU, Stickiness, Funnel de activación, Mix de LLMs)
  2. Radar AI RevOps (Oportunidades de Upsell, Riesgo de Churn, Fricción de Onboarding, Power Users)
  3. Feature Flags & Quotas por Plan (con enforcement de Modo Mantenimiento en vivo)
  4. Cupones Promocionales & Programa de Referidos (Growth Loops)
  5. Tickets de Soporte & Anuncios Globales In-Chat
  6. Reporte Ejecutivo / Inversor en Markdown listo para board/WhatsApp/Notion
"""

import datetime
import secrets
from typing import Dict, Any, Optional, List

from .boveda_segura import (
    VAULT_DIR,
    HISTORY_FILE,
    _vault_io_lock,
    _read_enc_json,
    _write_enc_json,
    _load_vault,
    _load_acl,
    _load_billing,
    _now_iso,
    normalizar_email,
    es_admin_plataforma,
)

GROWTH_FILE = VAULT_DIR / "admin_growth.enc"

DEFAULT_FEATURE_FLAGS = {
    "registro_abierto": True,
    "modo_mantenimiento": False,
    "permitir_emision_wsfe": True,
    "habilitar_frase_clave_personalizada": True,
    "habilitar_multi_usuario_invitados": True,
    "habilitar_estudios_b2b": True,
    "beta_oauth_2_1": False,
}

DEFAULT_PLAN_QUOTAS = {
    "free": {"max_cuits": 1, "auditorias_mes": 5, "max_invitados": 0, "precio_sugerido_ars": 0},
    "pro": {"max_cuits": 2, "auditorias_mes": 30, "max_invitados": 2, "precio_sugerido_ars": 19900},
    "pyme": {"max_cuits": 5, "auditorias_mes": 100, "max_invitados": 5, "precio_sugerido_ars": 49900},
    "estudio": {"max_cuits": 50, "auditorias_mes": 9999, "max_invitados": 15, "precio_sugerido_ars": 149000},
    "enterprise": {"max_cuits": 9999, "auditorias_mes": 99999, "max_invitados": 999, "precio_sugerido_ars": 350000},
}


def _load_growth() -> Dict[str, Any]:
    data = _read_enc_json(GROWTH_FILE, {})
    data.setdefault("feature_flags", dict(DEFAULT_FEATURE_FLAGS))
    for k, v in DEFAULT_FEATURE_FLAGS.items():
        data["feature_flags"].setdefault(k, v)
    data.setdefault("plan_quotas", {k: dict(v) for k, v in DEFAULT_PLAN_QUOTAS.items()})
    data.setdefault("cupones", {})
    data.setdefault("tickets", [])
    data.setdefault("anuncio_global", {"activo": False, "titulo": "", "mensaje": "", "actualizado_at": None})
    return data


def _save_growth(data: Dict[str, Any]) -> None:
    _write_enc_json(GROWTH_FILE, data)


def _parse_ts(ts: Optional[str]) -> Optional[datetime.datetime]:
    if not ts:
        return None
    try:
        dt = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt
    except Exception:
        return None


def esta_en_mantenimiento() -> bool:
    with _vault_io_lock:
        g = _load_growth()
        return bool(g["feature_flags"].get("modo_mantenimiento", False))


def obtener_anuncio_global_activo() -> Optional[Dict[str, Any]]:
    with _vault_io_lock:
        g = _load_growth()
        an = g.get("anuncio_global") or {}
        if an.get("activo") and an.get("mensaje"):
            return an
    return None


# =====================================================================
# 1. FINOPS, UNIT ECONOMICS & GROWTH FUNNEL
# =====================================================================

def admin_metricas_growth_saas(admin_email: str, tipo_cambio_usd: float = 1200.0) -> Dict[str, Any]:
    if not es_admin_plataforma(admin_email):
        return {"ok": False, "acceso_denegado": True, "error": "Acción restringida al Super-Admin Owner de impuesto.com.ar."}

    now = datetime.datetime.now(datetime.timezone.utc)
    d1 = now - datetime.timedelta(days=1)
    d7 = now - datetime.timedelta(days=7)
    d30 = now - datetime.timedelta(days=30)

    with _vault_io_lock:
        vault = _load_vault()
        acl = _load_acl()
        hist = _read_enc_json(HISTORY_FILE, [])
        billing = _load_billing()
        growth = _load_growth()

    users = acl.get("users", {})
    cuit_acl = acl.get("cuit_acl", {})
    subs = billing.get("subscriptions", {})
    all_emails = set(users.keys()) | set(subs.keys()) | {c.get("owner_email") for c in cuit_acl.values() if c.get("owner_email")}

    # FinOps
    mrr_ars = 0.0
    pagos_activos = 0
    trials = 0
    suspendidos = 0
    por_plan: Dict[str, int] = {}
    for em in all_emails:
        s = subs.get(em, {"plan": "free", "estado_cuenta": "activo", "precio_mensual_ars": 0.0})
        pl = s.get("plan", "free")
        est = s.get("estado_cuenta", "activo")
        por_plan[pl] = por_plan.get(pl, 0) + 1
        if est == "trial":
            trials += 1
        if est == "suspendido":
            suspendidos += 1
        precio = float(s.get("precio_mensual_ars") or 0.0)
        if est == "activo" and pl != "free" and precio > 0:
            mrr_ars += precio
            pagos_activos += 1

    arr_ars = mrr_ars * 12.0
    arpu_ars = (mrr_ars / pagos_activos) if pagos_activos else 0.0
    tc = max(1.0, float(tipo_cambio_usd or 1200.0))
    conv_rate = round((pagos_activos / len(all_emails)) * 100.0, 2) if all_emails else 0.0

    # Engagement (DAU / WAU / MAU / Features / LLM Mix)
    dau_set, wau_set, mau_set = set(), set(), set()
    por_llm: Dict[str, int] = {}
    por_accion: Dict[str, int] = {}
    auditados_emails = set()

    for ev in hist:
        em = ev.get("email", "")
        dt = _parse_ts(ev.get("ts"))
        if dt and em:
            if dt >= d1:
                dau_set.add(em)
            if dt >= d7:
                wau_set.add(em)
            if dt >= d30:
                mau_set.add(em)
        llm = ev.get("origen_llm", "mcp")
        por_llm[llm] = por_llm.get(llm, 0) + 1
        acc = ev.get("accion", "otra")
        por_accion[acc] = por_accion.get(acc, 0) + 1
        if acc == "auditoria_360_completada" and em:
            auditados_emails.add(em)

    stickiness = round((len(dau_set) / len(mau_set)) * 100.0, 1) if mau_set else 0.0

    # Activation Funnel
    con_token = sum(1 for u in users.values() if u.get("tokens"))
    owners_con_cuit = {c.get("owner_email") for c in cuit_acl.values() if c.get("owner_email")}
    owners_con_equipo = {c.get("owner_email") for c in cuit_acl.values() if c.get("authorized")}

    funnel = {
        "1_registrados": len(all_emails),
        "2_con_token_multi_llm": con_token,
        "3_con_cuit_vinculado": len(owners_con_cuit),
        "4_corrio_auditoria_360": len(auditados_emails),
        "5_invito_equipo_colaboradores": len(owners_con_equipo),
        "6_clientes_pagos_activos": pagos_activos,
    }

    top_features = sorted(por_accion.items(), key=lambda kv: kv[1], reverse=True)[:8]

    return {
        "ok": True,
        "fecha_corte": now.isoformat(),
        "finops": {
            "mrr_ars": round(mrr_ars, 2),
            "arr_ars": round(arr_ars, 2),
            "mrr_usd_est": round(mrr_ars / tc, 2),
            "arr_usd_est": round(arr_ars / tc, 2),
            "arpu_ars": round(arpu_ars, 2),
            "clientes_pagos": pagos_activos,
            "en_trial": trials,
            "suspendidos": suspendidos,
            "tasa_conversion_pago_pct": conv_rate,
            "distribucion_por_plan": por_plan,
        },
        "engagement": {
            "dau_24h": len(dau_set),
            "wau_7d": len(wau_set),
            "mau_30d": len(mau_set),
            "stickiness_dau_mau_pct": stickiness,
            "eventos_totales": len(hist),
            "mix_canales_llm": por_llm,
            "top_funcionalidades": [{"accion": k, "usos": v} for k, v in top_features],
        },
        "funnel_activacion": funnel,
        "cupones_activos": sum(1 for c in growth["cupones"].values() if c.get("activo")),
        "tickets_soporte_abiertos": sum(1 for t in growth["tickets"] if t.get("estado") != "resuelto"),
    }


# =====================================================================
# 2. AI REVOPS: RADAR DE OPORTUNIDADES (UPSELL / CHURN / POWER USERS)
# =====================================================================

def admin_detectar_oportunidades_y_riesgo(admin_email: str, dias_inactividad_churn: int = 14) -> Dict[str, Any]:
    if not es_admin_plataforma(admin_email):
        return {"ok": False, "acceso_denegado": True, "error": "Acción restringida al Super-Admin Owner de impuesto.com.ar."}

    now = datetime.datetime.now(datetime.timezone.utc)
    corte_churn = now - datetime.timedelta(days=max(1, int(dias_inactividad_churn or 14)))

    with _vault_io_lock:
        acl = _load_acl()
        hist = _read_enc_json(HISTORY_FILE, [])
        billing = _load_billing()

    users = acl.get("users", {})
    cuit_acl = acl.get("cuit_acl", {})
    subs = billing.get("subscriptions", {})
    all_emails = sorted(set(users.keys()) | set(subs.keys()) | {c.get("owner_email") for c in cuit_acl.values() if c.get("owner_email")})

    ev_by_email: Dict[str, List[Dict[str, Any]]] = {}
    for ev in hist:
        em = ev.get("email", "")
        if em:
            ev_by_email.setdefault(em, []).append(ev)

    upsell, churn_risk, onboarding_stuck, power_users = [], [], [], []

    for em in all_emails:
        sub = subs.get(em, {"plan": "free", "estado_cuenta": "activo", "precio_mensual_ars": 0.0})
        plan = sub.get("plan", "free")
        evs = ev_by_email.get(em, [])
        llms_usados = sorted({e.get("origen_llm", "mcp") for e in evs if e.get("origen_llm") not in ("oracle_cloud", "portal_web")})
        cuits_propios = [c for c, info in cuit_acl.items() if info.get("owner_email") == em]
        invitados = sum(len(info.get("authorized") or {}) for c, info in cuit_acl.items() if info.get("owner_email") == em)
        last_dt = max((_parse_ts(e.get("ts")) for e in evs if _parse_ts(e.get("ts"))), default=None)

        # Fricción de onboarding: tiene usuario pero 0 CUITs vinculados
        if not cuits_propios:
            onboarding_stuck.append({"email": em, "plan": plan, "motivo": "Registrado sin CUIT vinculado aún"})

        # Upsell: plan free/trial con alta tracción
        if plan in ("free", "trial") and (len(evs) >= 3 or len(cuits_propios) >= 2 or invitados > 0):
            sugerido = "estudio" if len(cuits_propios) >= 3 else ("pyme" if invitados > 0 else "pro")
            upsell.append({
                "email": em,
                "plan_actual": plan,
                "plan_sugerido": sugerido,
                "eventos": len(evs),
                "cuits": len(cuits_propios),
                "invitados": invitados,
                "mensaje_sugerido": f"Hola! Vi que ya estás usando impuesto.com.ar activamente ({len(evs)} operaciones). Si activás el plan {sugerido.upper()} destrabás auditorías ilimitadas, alertas automáticas y colaboradores por email.",
            })

        # Riesgo de Churn: sin actividad reciente
        if cuits_propios and (last_dt is None or last_dt < corte_churn):
            dias_sin = (now - last_dt).days if last_dt else 999
            churn_risk.append({
                "email": em,
                "plan": plan,
                "dias_sin_actividad": dias_sin,
                "mensaje_sugerido": f"Hola! Hace {dias_sin} días que no revisamos tu estado en ARCA. ¿Querés que corramos en 1 minuto tu chequeo de DFE y vencimientos del mes?",
            })

        # Power Users: usa múltiples LLMs o alto volumen
        if len(llms_usados) >= 2 or len(evs) >= 5:
            power_users.append({
                "email": em,
                "plan": plan,
                "eventos": len(evs),
                "llms_usados": llms_usados,
                "accion_growth": "Invitar a programa de referidos / pedir testimonio",
            })

    return {
        "ok": True,
        "resumen": {
            "oportunidades_upsell": len(upsell),
            "riesgo_churn": len(churn_risk),
            "onboarding_incompleto": len(onboarding_stuck),
            "power_users": len(power_users),
        },
        "oportunidades_upsell": upsell,
        "riesgo_churn": churn_risk,
        "onboarding_incompleto": onboarding_stuck,
        "power_users": power_users,
    }


# =====================================================================
# 3. FEATURE FLAGS & QUOTAS POR PLAN
# =====================================================================

def admin_gestionar_feature_flags_y_limites(
    admin_email: str,
    accion: str = "listar",
    flag_nombre: str = "",
    flag_valor: Optional[bool] = None,
    plan_nombre: str = "",
    plan_limites: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if not es_admin_plataforma(admin_email):
        return {"ok": False, "acceso_denegado": True, "error": "Acción restringida al Super-Admin Owner de impuesto.com.ar."}

    acc = (accion or "listar").strip().lower()
    with _vault_io_lock:
        g = _load_growth()
        if acc == "listar":
            return {"ok": True, "feature_flags": g["feature_flags"], "plan_quotas": g["plan_quotas"]}

        if acc == "actualizar_flag":
            if not flag_nombre or flag_valor is None:
                return {"ok": False, "error": "Indicá `flag_nombre` y `flag_valor` (true/false)."}
            g["feature_flags"][flag_nombre.strip()] = bool(flag_valor)
            _save_growth(g)
            return {"ok": True, "flag_actualizado": {flag_nombre.strip(): bool(flag_valor)}, "feature_flags": g["feature_flags"]}

        if acc == "actualizar_plan":
            pl = (plan_nombre or "").strip().lower()
            if not pl or not isinstance(plan_limites, dict):
                return {"ok": False, "error": "Indicá `plan_nombre` y `plan_limites` (objeto con max_cuits, auditorias_mes, max_invitados, precio_sugerido_ars)."}
            cur = g["plan_quotas"].setdefault(pl, {})
            cur.update(plan_limites)
            _save_growth(g)
            return {"ok": True, "plan_actualizado": pl, "limites": cur}

    return {"ok": False, "error": f"Acción '{accion}' desconocida. Usá: listar, actualizar_flag o actualizar_plan."}


# =====================================================================
# 4. CUPONES PROMOCIONALES & PROGRAMA DE REFERIDOS
# =====================================================================

def admin_gestionar_cupones_y_referidos(
    admin_email: str,
    accion: str = "listar",
    codigo: str = "",
    descuento_pct: int = 0,
    meses_gratis: int = 0,
    plan_objetivo: str = "todos",
    usos_maximos: int = 100,
    referidor_email: str = "",
) -> Dict[str, Any]:
    if not es_admin_plataforma(admin_email):
        return {"ok": False, "acceso_denegado": True, "error": "Acción restringida al Super-Admin Owner de impuesto.com.ar."}

    acc = (accion or "listar").strip().lower()
    cod = (codigo or "").strip().upper()
    with _vault_io_lock:
        g = _load_growth()
        if acc == "listar":
            return {"ok": True, "total": len(g["cupones"]), "cupones": list(g["cupones"].values())}

        if acc == "crear":
            if not cod or len(cod) < 3:
                return {"ok": False, "error": "Indicá un código de cupón de al menos 3 caracteres (ej: LANZAMIENTO50)."}
            g["cupones"][cod] = {
                "codigo": cod,
                "activo": True,
                "descuento_pct": max(0, min(100, int(descuento_pct or 0))),
                "meses_gratis": max(0, int(meses_gratis or 0)),
                "plan_objetivo": (plan_objetivo or "todos").lower(),
                "usos_maximos": max(1, int(usos_maximos or 100)),
                "usos_actuales": 0,
                "referidor_email": normalizar_email(referidor_email),
                "creado_at": _now_iso(),
            }
            _save_growth(g)
            return {"ok": True, "cupon": g["cupones"][cod]}

        if acc == "desactivar":
            if cod not in g["cupones"]:
                return {"ok": False, "error": f"Cupón '{cod}' no encontrado."}
            g["cupones"][cod]["activo"] = False
            _save_growth(g)
            return {"ok": True, "cupon": g["cupones"][cod]}

        if acc == "registrar_uso":
            if cod not in g["cupones"] or not g["cupones"][cod].get("activo"):
                return {"ok": False, "error": f"Cupón '{cod}' inexistente o inactivo."}
            cup = g["cupones"][cod]
            if cup["usos_actuales"] >= cup["usos_maximos"]:
                return {"ok": False, "error": f"Cupón '{cod}' alcanzó su límite de usos."}
            cup["usos_actuales"] += 1
            _save_growth(g)
            return {"ok": True, "cupon": cup}

    return {"ok": False, "error": f"Acción '{accion}' desconocida. Usá: listar, crear, desactivar o registrar_uso."}


# =====================================================================
# 5. SOPORTE (TICKETS) & ANUNCIO GLOBAL IN-CHAT
# =====================================================================

def admin_gestionar_soporte_y_anuncios(
    admin_email: str,
    accion: str = "listar_tickets",
    cliente_email: str = "",
    asunto: str = "",
    detalle: str = "",
    prioridad: str = "media",
    ticket_id: str = "",
    anuncio_activo: Optional[bool] = None,
    anuncio_titulo: str = "",
    anuncio_mensaje: str = "",
) -> Dict[str, Any]:
    if not es_admin_plataforma(admin_email):
        return {"ok": False, "acceso_denegado": True, "error": "Acción restringida al Super-Admin Owner de impuesto.com.ar."}

    acc = (accion or "listar_tickets").strip().lower()
    with _vault_io_lock:
        g = _load_growth()

        if acc == "listar_tickets":
            return {"ok": True, "total": len(g["tickets"]), "tickets": list(reversed(g["tickets"][-50:])), "anuncio_global": g["anuncio_global"]}

        if acc == "crear_ticket":
            tid = f"tkt_{secrets.token_hex(4)}"
            t = {
                "id": tid,
                "cliente_email": normalizar_email(cliente_email),
                "asunto": (asunto or "Consulta soporte")[:160],
                "detalle": (detalle or "")[:1000],
                "prioridad": (prioridad or "media").lower(),
                "estado": "abierto",
                "creado_at": _now_iso(),
            }
            g["tickets"].append(t)
            g["tickets"] = g["tickets"][-300:]
            _save_growth(g)
            return {"ok": True, "ticket": t}

        if acc == "resolver_ticket":
            for t in g["tickets"]:
                if t.get("id") == ticket_id:
                    t["estado"] = "resuelto"
                    t["resuelto_at"] = _now_iso()
                    if detalle:
                        t["resolucion"] = detalle[:600]
                    _save_growth(g)
                    return {"ok": True, "ticket": t}
            return {"ok": False, "error": f"Ticket '{ticket_id}' no encontrado."}

        if acc == "configurar_anuncio":
            g["anuncio_global"] = {
                "activo": bool(anuncio_activo) if anuncio_activo is not None else bool(anuncio_mensaje),
                "titulo": (anuncio_titulo or "Aviso impuesto.com.ar")[:120],
                "mensaje": (anuncio_mensaje or "")[:600],
                "actualizado_at": _now_iso(),
            }
            _save_growth(g)
            return {"ok": True, "anuncio_global": g["anuncio_global"]}

    return {"ok": False, "error": f"Acción '{accion}' desconocida. Usá: listar_tickets, crear_ticket, resolver_ticket o configurar_anuncio."}


# =====================================================================
# 6. REPORTE EJECUTIVO / INVERSOR EN MARKDOWN (1 CLIC)
# =====================================================================

def admin_exportar_reporte_inversor_markdown(admin_email: str, tipo_cambio_usd: float = 1200.0) -> Dict[str, Any]:
    if not es_admin_plataforma(admin_email):
        return {"ok": False, "acceso_denegado": True, "error": "Acción restringida al Super-Admin Owner de impuesto.com.ar."}

    m = admin_metricas_growth_saas(admin_email, tipo_cambio_usd=tipo_cambio_usd)
    op = admin_detectar_oportunidades_y_riesgo(admin_email)
    fl = admin_gestionar_feature_flags_y_limites(admin_email, accion="listar")

    f = m["finops"]
    e = m["engagement"]
    fn = m["funnel_activacion"]
    op_r = op["resumen"]

    md = "\n".join([
        f"# 📊 Reporte Ejecutivo SaaS — impuesto.com.ar",
        f"**Fecha:** {m['fecha_corte'][:10]} · **Owner:** {normalizar_email(admin_email)}",
        "",
        "## 1. FinOps & Ingresos",
        f"- **MRR:** ARS ${f['mrr_ars']:,.2f} (~USD ${f['mrr_usd_est']:,.2f})",
        f"- **ARR:** ARS ${f['arr_ars']:,.2f} (~USD ${f['arr_usd_est']:,.2f})",
        f"- **ARPU:** ARS ${f['arpu_ars']:,.2f} · **Conversión a pago:** {f['tasa_conversion_pago_pct']}%",
        f"- **Clientes pagos:** {f['clientes_pagos']} · **Trial:** {f['en_trial']} · **Suspendidos:** {f['suspendidos']}",
        f"- **Planes:** {f['distribucion_por_plan']}",
        "",
        "## 2. Tracción, Retención y Mix de Canales LLM",
        f"- **DAU / WAU / MAU:** {e['dau_24h']} / {e['wau_7d']} / {e['mau_30d']} · **Stickiness (DAU/MAU):** {e['stickiness_dau_mau_pct']}%",
        f"- **Eventos acumulados:** {e['eventos_totales']} · **Canales LLM:** {e['mix_canales_llm']}",
        "",
        "## 3. Funnel de Activación",
        f"1. Registrados: **{fn['1_registrados']}** → 2. Con Token: **{fn['2_con_token_multi_llm']}** → 3. Con CUIT: **{fn['3_con_cuit_vinculado']}** → 4. Auditoría 360°: **{fn['4_corrio_auditoria_360']}** → 5. Equipo invitado: **{fn['5_invito_equipo_colaboradores']}** → 6. Pagos: **{fn['6_clientes_pagos_activos']}**",
        "",
        "## 4. Radar RevOps (Acciones de Growth Hoy)",
        f"- 🔥 **Oportunidades de Upsell:** {op_r['oportunidades_upsell']}",
        f"- ⚠️ **Riesgo de Churn:** {op_r['riesgo_churn']} · **Onboarding incompleto:** {op_r['onboarding_incompleto']}",
        f"- 🏆 **Power Users (embajadores/referidos):** {op_r['power_users']}",
        "",
        "## 5. Operación & Flags Activos",
        f"- **Modo mantenimiento:** {fl['feature_flags'].get('modo_mantenimiento')} · **Registro abierto:** {fl['feature_flags'].get('registro_abierto')} · **WSFE:** {fl['feature_flags'].get('permitir_emision_wsfe')}",
        f"- **Cupones activos:** {m['cupones_activos']} · **Tickets abiertos:** {m['tickets_soporte_abiertos']}",
    ])

    return {"ok": True, "reporte_markdown": md, "metricas": m}
