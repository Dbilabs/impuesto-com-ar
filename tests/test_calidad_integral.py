"""
tests/test_calidad_integral.py
Suite de Contratos, Invariantes Contables y Seguridad para impuesto.com.ar.

Se ejecuta automáticamente en CI antes de cada deploy para garantizar que:
  1. Todos los imports y rutas de bot/main.py existan y respondan sin errores de contrato.
  2. Los parsers financieros cumplan los invariantes contables (sum(partes) == total).
  3. El Double-Check bloquee falsos negativos ('Deuda $0' con cobertura incompleta).
  4. skills-pack/ esté 100% sincronizado con functions/mcp/skills_bundle.js.
  5. Ninguna credencial o dato personal se filtre en el repositorio.
"""

import os
import re
import sys
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Aislar SIEMPRE la bóveda y el backoffice en un tempdir para no tocar data/boveda real (P1-17)
_TEST_TMPDIR = tempfile.TemporaryDirectory(prefix="impuesto_test_vault_")
os.environ["DISABLE_AUDIT_PREWARM"] = "1"
os.environ["PLATFORM_ADMIN_EMAILS"] = "admin_fixture@impuesto.test"

from bot import boveda_segura as _bv_mod
from bot import backoffice_growth as _bg_mod
from bot import validador_invariantes as _vi_mod

_tmp_path = Path(_TEST_TMPDIR.name)
_bv_mod.VAULT_DIR = _tmp_path
_bv_mod.VAULT_FILE = _tmp_path / "credenciales.enc"
_bv_mod.ACL_FILE = _tmp_path / "acl.enc"
_bv_mod.HISTORY_FILE = _tmp_path / "historial.enc"
_bv_mod.KEY_FILE = _tmp_path / ".vault_key"
_bv_mod.BILLING_FILE = _tmp_path / "admin_billing.enc"
_vi_mod.INCIDENTES_FILE = _tmp_path / "incidentes_calidad.json"
for _attr in ("GROWTH_FILE", "HISTORY_FILE", "VAULT_FILE", "ACL_FILE", "BILLING_FILE"):
    if hasattr(_bg_mod, _attr):
        setattr(_bg_mod, _attr, _tmp_path / f"{_attr.lower()}.enc")
_bg_mod.HISTORY_FILE = _bv_mod.HISTORY_FILE


def _tok_verificado(email: str, label: str = "test") -> str:
    return _bv_mod.crear_token_usuario(email, label, verificado=True)["token"]

from fastapi.testclient import TestClient
from bot.main import app
from bot.auditoria_unificada import _parse_ccma_detalle_periodos, _parse_ar_num
from bot.validador_invariantes import validar_invariantes_auditoria
from bot.doublecheck_arca import obtener_protocolo_doublecheck, validar_cobertura_auditoria
from bot.playbooks_servicios import obtener_playbook_servicio


class TestContratosYCalidadFiscal(unittest.TestCase):
    def test_01_fastapi_endpoints_y_boveda_sin_fuga(self):
        client = TestClient(app)
        r_h = client.get("/health")
        self.assertEqual(r_h.status_code, 200)
        self.assertIn("vault_key_fingerprint", r_h.json())
        r_vinc = client.get("/vincular?tipo=estudio")
        self.assertEqual(r_vinc.status_code, 200)
        self.assertIn("AES-256", r_vinc.text)

        # Vincular con dueño verificado, verificar sin fuga autenticado y revocar como Owner (P0-2)
        test_cuit = "20301234567"
        tok_pre = _tok_verificado("test01_owner@impuesto.test")
        r_save = client.post(
            "/api/v1/vincular",
            headers={"X-User-Token": tok_pre},
            json={
                "email": "test01_owner@impuesto.test",
                "cuit": test_cuit,
                "clave_fiscal": "TestSecret999",
                "modo": "solo_lectura_cifrada",
            },
        )
        self.assertEqual(r_save.status_code, 200)
        self.assertTrue(r_save.json()["ok"])
        tok = r_save.json()["token"]

        # Sin token, GET y DELETE devuelven 401
        self.assertEqual(client.get(f"/api/v1/vincular/{test_cuit}").status_code, 401)
        self.assertEqual(client.delete(f"/api/v1/vincular/{test_cuit}").status_code, 401)

        r_state = client.get(f"/api/v1/vincular/{test_cuit}", headers={"X-User-Token": tok})
        self.assertEqual(r_state.status_code, 200)
        self.assertNotIn("TestSecret999", r_state.text)

        r_del = client.delete(f"/api/v1/vincular/{test_cuit}", headers={"X-User-Token": tok})
        self.assertEqual(r_del.status_code, 200)
        self.assertTrue(r_del.json()["revocado"])

    def test_02_imports_reales_de_todas_las_herramientas_backend(self):
        """Verifica que ningún handler de bot/main.py tenga un ImportError oculto."""
        from bot.arca_ws import verificar_estado_servidores_wsfe, consultar_padron_a5, emitir_comprobante_wsfe, generar_csr_arca
        from bot.scraper import consultar_notificaciones_dfe, consultar_mis_comprobantes
        from bot.scraper_bbpp import consultar_bienes_personales_web
        from bot.scraper_monotributo import consultar_estado_monotributo
        from bot.scraper_extras_arca import (
            verificar_proveedor_apocrifo_apoc,
            consultar_nuestra_parte,
            consultar_mis_retenciones,
            consultar_y_renovar_certificado_mipyme,
        )
        from bot.auditoria_unificada import auditar_estado_integral_arca, consultar_ccma_preciso

        for fn in [
            verificar_estado_servidores_wsfe, consultar_padron_a5, emitir_comprobante_wsfe, generar_csr_arca,
            consultar_notificaciones_dfe, consultar_mis_comprobantes, consultar_bienes_personales_web,
            consultar_estado_monotributo, verificar_proveedor_apocrifo_apoc, consultar_nuestra_parte,
            consultar_mis_retenciones, consultar_y_renovar_certificado_mipyme,
            auditar_estado_integral_arca, consultar_ccma_preciso,
        ]:
            self.assertTrue(callable(fn))

    def test_03_invariante_parser_ccma_con_prefijo_mas_en_autonomos(self):
        """Fixture real con Monotributo (020/021/024), Autónomos con prefijo '+' y créditos PFP."""
        fixture = """
        11/2026\t020\t019\t019\tObligacion Mensual Monot.\t20/11/2026\t18,246.86
        11/2026\t020\t019\t051\tIntereses Resarcitorios Monot.\t26/11/2026\t100.36
        +\t \t11/2026\tAUT\t019\t019\tObligacion Mensual Autonomo.\t10/12/2026\t159,563.00
        +\t \t10/2026\tAUT\t019\t019\tObligacion Mensual Autonomo.\t11/11/2026\t159,563.00
        +\t \t10/2026\tAUT\t019\t051\tIntereses Resarcitorios Autonomo\t26/11/2026\t662.19
        06/2026\t020\t019\t019\tObligacion Mensual Monot.\t22/06/2026\t25,495.79
        06/2026\t020\t019\t019\tCrédito por PFP Mis Facilidades Nro W266569\t02/07/2026\t25,495.79
        """
        desg = _parse_ccma_detalle_periodos(fixture)
        self.assertAlmostEqual(desg["monotributo_vencido_total"], 18347.22, places=2)
        self.assertAlmostEqual(desg["autonomos_vencido_total"], 160225.19, places=2)
        self.assertAlmostEqual(desg["autonomos_por_vencer_total"], 159563.00, places=2)
        self.assertFalse(desg["superposicion_con_planes_vigentes"])

    def test_04_validador_invariantes_detecta_descuadre_y_contradicciones(self):
        # Caso sano: todo cuadra
        sano = {
            "ccma": {
                "saldo_deudor_vencido": 178572.41,
                "capital_mensual": 177809.86,
                "intereses_accesorios": 762.55,
                "tiene_pfp_mis_facilidades": True,
                "desglose_por_regimen": {"monotributo_vencido_total": 18347.22, "autonomos_vencido_total": 160225.19},
            },
            "mis_facilidades": {
                "cantidad_planes_vigentes": 1,
                "planes_vigentes": [{"numero": "W1", "consolidado_original": 1000.0, "capital_pagado": 250.0, "capital_remanente": 750.0}],
            },
            "portal_monotributo": {"categoria": "C", "facturado_acumulado": 21000000.0, "tope_categoria": 24670494.31, "margen_disponible_categoria": 3670494.31},
        }
        v_ok = validar_invariantes_auditoria(sano)
        self.assertTrue(v_ok["invariantes_ok"])

        # Caso roto: descuadre CCMA + Monotributo "No detectada"
        roto = {
            "ccma": {
                "saldo_deudor_vencido": 1172263.79,
                "capital_mensual": 1134309.58,
                "intereses_accesorios": 37954.21,
                "desglose_por_regimen": {"monotributo_vencido_total": 357143.65, "autonomos_vencido_total": 0.0},
            },
            "mis_facilidades": {"cantidad_planes_vigentes": 0, "planes_vigentes": []},
            "portal_monotributo": {"categoria": "No detectada"},
        }
        v_bad = validar_invariantes_auditoria(roto)
        self.assertFalse(v_bad["invariantes_ok"])
        codigos = {a["codigo"] for a in v_bad["alertas_calidad"]}
        self.assertIn("INV_CCMA_DESCUADRE", codigos)
        self.assertIn("INV_CRUCE_MONO_FALTANTE", codigos)

    def test_05_doublecheck_y_preflight_universales(self):
        dc_bad = validar_cobertura_auditoria("estado_de_cuenta_y_deudas", ["sct"])
        self.assertFalse(dc_bad["puede_afirmar_deuda_cero_o_al_dia"])
        dc_ok = validar_cobertura_auditoria("estado_de_cuenta_y_deudas", ["ccma", "mis_facilidades", "sct", "portal_monotributo"])
        self.assertTrue(dc_ok["puede_afirmar_deuda_cero_o_al_dia"])
        pb = obtener_playbook_servicio("agip")
        self.assertTrue(pb["servicio_encontrado"])
        self.assertGreaterEqual(len(pb["protocolo_preflight_universal"]), 7)

    def test_06_single_source_of_truth_skills_sincronizados(self):
        pack_slugs = sorted(p.parent.name for p in (ROOT / "skills-pack").glob("*/SKILL.md"))
        bundle_txt = (ROOT / "functions" / "mcp" / "skills_bundle.js").read_text(encoding="utf-8")
        for slug in pack_slugs:
            self.assertIn(f'"slug": "{slug}"', bundle_txt, f"Skill {slug} no sincronizado en skills_bundle.js — correr python3 scripts/sync_skills.py")

    def test_07_auditoria_sin_timeout_cache_y_herramientas_gemini(self):
        import time
        from unittest.mock import patch
        from bot import main as bot_main

        # Verificar que listar_empresas y consultar_situacion_monotributo estén mapeadas en bot/main.py
        src = (ROOT / "bot" / "main.py").read_text(encoding="utf-8")
        self.assertIn('"listar_empresas"', src)
        self.assertIn('"consultar_situacion_monotributo"', src)

        # Verificar modo anti-timeout (EN_PROGRESO rápido + deduplicación + caché TTL)
        calls = {"n": 0}
        def fake_slow_audit(cuit, clave):
            calls["n"] += 1
            time.sleep(0.35)
            return {"ok": True, "cuit": cuit, "informe_contador_markdown": "## OK"}

        test_cuit = "20999999991"
        bot_main.AUDIT_CACHE.pop(test_cuit, None)
        bot_main.AUDIT_INFLIGHT.pop(test_cuit, None)
        with patch.object(bot_main, "auditar_estado_integral_arca", side_effect=fake_slow_audit), \
             patch.object(bot_main, "AUDIT_SYNC_WAIT_SEC", 0.08):
            r1 = bot_main._ejecutar_auditoria_sin_timeout(test_cuit, "dummy")
            self.assertEqual(r1.get("estado"), "EN_PROGRESO")
            # Segunda llamada concurrente no duplica Chromium
            r2 = bot_main._ejecutar_auditoria_sin_timeout(test_cuit, "dummy")
            self.assertEqual(calls["n"], 1)
            time.sleep(0.35)
            # Tercera llamada sirve desde caché al instante
            r3 = bot_main._ejecutar_auditoria_sin_timeout(test_cuit, "dummy")
            self.assertTrue(r3.get("desde_cache"))
            self.assertEqual(r3.get("informe_contador_markdown"), "## OK")
            self.assertEqual(calls["n"], 1)
        bot_main.AUDIT_CACHE.pop(test_cuit, None)

    def test_08_aislamiento_multitenant_owner_invitados_e_historial_cross_llm(self):
        from fastapi.testclient import TestClient
        from bot.main import app
        from bot import boveda_segura as bv

        client = TestClient(app)
        cuit_test = "20333333339"
        owner_email = "owner_test@impuesto.test"
        attacker_email = "intruso_test@impuesto.test"
        socio_email = "socio_test@impuesto.test"

        # 1. Sin token: acceso bloqueado
        r_anon = client.post("/api/v1/mcp/tool", json={"name": "listar_empresas", "arguments": {}})
        self.assertEqual(r_anon.status_code, 200)
        self.assertTrue(r_anon.json().get("requiere_autenticacion"))
        self.assertTrue(r_anon.json().get("acceso_denegado"))

        # 2. Owner verificado vincula CUIT y obtiene token + URLs privadas
        tok_owner_pre = _tok_verificado(owner_email)
        r_link = client.post(
            "/api/v1/vincular",
            headers={"X-User-Token": tok_owner_pre},
            json={
                "email": owner_email,
                "cuit": cuit_test,
                "clave_fiscal": "ClaveSoloTest123",
                "modo": "solo_lectura_cifrada",
                "etiqueta_token": "gemini_test",
            },
        )
        self.assertTrue(r_link.json().get("ok"))
        tok_owner = r_link.json().get("token")
        self.assertTrue(tok_owner.startswith("imp_live_"))
        self.assertIn("gemini", r_link.json().get("urls_privadas_mcp", {}))

        # 3. Intruso con su propio token verificado NO ve el CUIT del Owner ni puede consultarlo
        tok_attacker = bv.crear_token_usuario(attacker_email, "intruso", verificado=True)["token"]
        r_att_list = client.post(
            "/api/v1/mcp/tool",
            headers={"X-User-Token": tok_attacker, "X-LLM-Origin": "gemini"},
            json={"name": "listar_empresas", "arguments": {}},
        )
        self.assertEqual(r_att_list.json().get("empresas_vinculadas"), [])
        r_att_audit = client.post(
            "/api/v1/mcp/tool",
            headers={"X-User-Token": tok_attacker, "X-LLM-Origin": "gemini"},
            json={"name": "auditar_estado_integral_arca", "arguments": {"cuit": cuit_test}},
        )
        self.assertTrue(r_att_audit.json().get("acceso_denegado"))

        # 4. Owner autoriza a socio por email desde Claude
        r_auth = client.post(
            "/api/v1/mcp/tool",
            headers={"X-User-Token": tok_owner, "X-LLM-Origin": "claude"},
            json={"name": "autorizar_usuario_cuit", "arguments": {"cuit": cuit_test, "email_invitado": socio_email, "rol": "solo_lectura"}},
        )
        self.assertTrue(r_auth.json().get("ok"))

        # 5. Socio genera token tras OTP y ve el CUIT + deja nota desde ChatGPT -> Owner la ve desde Gemini
        tok_socio = bv.crear_token_usuario(socio_email, "chatgpt", verificado=True)["token"]
        r_soc_list = client.post(
            "/api/v1/mcp/tool",
            headers={"X-User-Token": tok_socio, "X-LLM-Origin": "chatgpt"},
            json={"name": "listar_empresas", "arguments": {}},
        )
        cuits_socio = [x["cuit"] for x in r_soc_list.json().get("empresas_vinculadas", [])]
        self.assertIn(cuit_test, cuits_socio)

        r_note = client.post(
            "/api/v1/mcp/tool",
            headers={"X-User-Token": tok_socio, "X-LLM-Origin": "chatgpt"},
            json={"name": "registrar_nota_historial", "arguments": {"cuit": cuit_test, "titulo": "Cierre IVA revisado", "detalle": "Falta VEP"}},
        )
        self.assertTrue(r_note.json().get("ok"))

        r_hist = client.post(
            "/api/v1/mcp/tool",
            headers={"X-User-Token": tok_owner, "X-LLM-Origin": "gemini"},
            json={"name": "ver_historial_actividad", "arguments": {"cuit": cuit_test, "limite": 10}},
        )
        titulos = [e["titulo"] for e in r_hist.json().get("eventos", [])]
        self.assertIn("Cierre IVA revisado", titulos)

        # 6. Owner revoca acceso -> Socio bloqueado al instante
        r_rev = client.post(
            "/api/v1/mcp/tool",
            headers={"X-User-Token": tok_owner, "X-LLM-Origin": "gemini"},
            json={"name": "revocar_usuario_cuit", "arguments": {"cuit": cuit_test, "email_invitado": socio_email}},
        )
        self.assertTrue(r_rev.json().get("ok"))
        r_soc_after = client.post(
            "/api/v1/mcp/tool",
            headers={"X-User-Token": tok_socio, "X-LLM-Origin": "chatgpt"},
            json={"name": "auditar_estado_integral_arca", "arguments": {"cuit": cuit_test}},
        )
        self.assertTrue(r_soc_after.json().get("acceso_denegado"))

        # 7. Frase clave personalizada: rechaza cortas (<16), acepta seguras (>=16) con verificado=True y rechaza colisiones
        r_short = bv.crear_token_usuario(owner_email, "corta", custom_token="clave123", verificado=True)
        self.assertFalse(r_short.get("ok"))
        r_custom = bv.crear_token_usuario(owner_email, "custom", custom_token="Cafe-Cordoba-Fiscal-8924", verificado=True)
        self.assertTrue(r_custom.get("ok"))
        self.assertEqual(bv.resolver_email_por_token("Cafe-Cordoba-Fiscal-8924"), owner_email)
        r_dup = bv.crear_token_usuario(attacker_email, "dup", custom_token="Cafe-Cordoba-Fiscal-8924", verificado=True)
        self.assertFalse(r_dup.get("ok"))

        # Limpieza de fixture
        client.delete(f"/api/v1/vincular/{cuit_test}", headers={"X-User-Token": tok_owner})

    def test_09_backoffice_super_admin_plataforma(self):
        from fastapi.testclient import TestClient
        from bot.main import app
        from bot import boveda_segura as bv

        client = TestClient(app)
        admin_tok = bv.crear_token_usuario("admin_fixture@impuesto.test", "admin_test", verificado=True)["token"]
        user_email = "cliente_saas_test@impuesto.test"
        user_tok = bv.crear_token_usuario(user_email, "user_test", verificado=True)["token"]

        # 1. Usuario normal NO puede acceder al Backoffice
        r_forb = client.post(
            "/api/v1/mcp/tool",
            headers={"X-User-Token": user_tok, "X-LLM-Origin": "gemini"},
            json={"name": "admin_tablero_plataforma", "arguments": {}},
        )
        self.assertTrue(r_forb.json().get("acceso_denegado"))

        # 2. Owner de la plataforma SÍ accede al tablero y gestiona suscripciones
        r_dash = client.post(
            "/api/v1/mcp/tool",
            headers={"X-User-Token": admin_tok, "X-LLM-Origin": "claude"},
            json={"name": "admin_tablero_plataforma", "arguments": {}},
        )
        self.assertTrue(r_dash.json().get("ok"))
        self.assertIn("kpis", r_dash.json())

        r_sub = client.post(
            "/api/v1/mcp/tool",
            headers={"X-User-Token": admin_tok, "X-LLM-Origin": "claude"},
            json={"name": "admin_gestionar_suscripcion_cliente", "arguments": {"email": user_email, "plan": "estudio", "estado_cuenta": "activo", "precio_mensual_ars": 49000}},
        )
        self.assertTrue(r_sub.json().get("ok"))
        self.assertEqual(r_sub.json()["suscripcion"]["plan"], "estudio")

        # 3. Suspender usuario bloquea sus consultas; reactivar lo habilita
        r_susp = client.post(
            "/api/v1/mcp/tool",
            headers={"X-User-Token": admin_tok, "X-LLM-Origin": "gemini"},
            json={"name": "admin_accion_emergencia_plataforma", "arguments": {"accion": "suspender_usuario", "objetivo": user_email}},
        )
        self.assertTrue(r_susp.json().get("ok"))
        r_blocked = client.post(
            "/api/v1/mcp/tool",
            headers={"X-User-Token": user_tok, "X-LLM-Origin": "gemini"},
            json={"name": "listar_empresas", "arguments": {}},
        )
        self.assertTrue(r_blocked.json().get("cuenta_suspendida"))

        r_react = client.post(
            "/api/v1/mcp/tool",
            headers={"X-User-Token": admin_tok, "X-LLM-Origin": "gemini"},
            json={"name": "admin_accion_emergencia_plataforma", "arguments": {"accion": "reactivar_usuario", "objetivo": user_email}},
        )
        self.assertTrue(r_react.json().get("ok"))

    def test_10_backoffice_growth_saas_completo(self):
        from fastapi.testclient import TestClient
        from bot.main import app
        from bot import boveda_segura as bv

        client = TestClient(app)
        admin_tok = bv.crear_token_usuario("admin_fixture@impuesto.test", "growth_admin", verificado=True)["token"]
        user_tok = bv.crear_token_usuario("normal_growth@impuesto.test", "growth_user", verificado=True)["token"]

        # 1. Usuario normal bloqueado en herramientas Growth
        r_no = client.post("/api/v1/mcp/tool", headers={"X-User-Token": user_tok}, json={"name": "admin_metricas_growth_saas", "arguments": {}})
        self.assertTrue(r_no.json().get("acceso_denegado"))

        # 2. Métricas Growth, Radar RevOps y Reporte Inversor
        r_m = client.post("/api/v1/mcp/tool", headers={"X-User-Token": admin_tok}, json={"name": "admin_metricas_growth_saas", "arguments": {"tipo_cambio_usd": 1200}})
        self.assertTrue(r_m.json().get("ok"))
        self.assertIn("finops", r_m.json())
        self.assertIn("funnel_activacion", r_m.json())

        r_op = client.post("/api/v1/mcp/tool", headers={"X-User-Token": admin_tok}, json={"name": "admin_detectar_oportunidades_y_riesgo", "arguments": {}})
        self.assertTrue(r_op.json().get("ok"))

        r_cup = client.post("/api/v1/mcp/tool", headers={"X-User-Token": admin_tok}, json={"name": "admin_gestionar_cupones_y_referidos", "arguments": {"accion": "crear", "codigo": "LAUNCH50", "descuento_pct": 50}})
        self.assertTrue(r_cup.json().get("ok"))
        self.assertEqual(r_cup.json()["cupon"]["codigo"], "LAUNCH50")

        r_tkt = client.post("/api/v1/mcp/tool", headers={"X-User-Token": admin_tok}, json={"name": "admin_gestionar_soporte_y_anuncios", "arguments": {"accion": "crear_ticket", "cliente_email": "normal_growth@impuesto.test", "asunto": "Duda Factura E", "prioridad": "alta"}})
        self.assertTrue(r_tkt.json().get("ok"))
        tid = r_tkt.json()["ticket"]["id"]
        r_res = client.post("/api/v1/mcp/tool", headers={"X-User-Token": admin_tok}, json={"name": "admin_gestionar_soporte_y_anuncios", "arguments": {"accion": "resolver_ticket", "ticket_id": tid, "detalle": "Resuelto"}})
        self.assertEqual(r_res.json()["ticket"]["estado"], "resuelto")

        # 3. Modo mantenimiento bloquea usuarios normales pero NO al Super-Admin
        client.post("/api/v1/mcp/tool", headers={"X-User-Token": admin_tok}, json={"name": "admin_gestionar_feature_flags_y_limites", "arguments": {"accion": "actualizar_flag", "flag_nombre": "modo_mantenimiento", "flag_valor": True}})
        r_maint = client.post("/api/v1/mcp/tool", headers={"X-User-Token": user_tok}, json={"name": "listar_empresas", "arguments": {}})
        self.assertTrue(r_maint.json().get("modo_mantenimiento"))
        # Restaurar modo mantenimiento = False
        client.post("/api/v1/mcp/tool", headers={"X-User-Token": admin_tok}, json={"name": "admin_gestionar_feature_flags_y_limites", "arguments": {"accion": "actualizar_flag", "flag_nombre": "modo_mantenimiento", "flag_valor": False}})

        r_rep = client.post("/api/v1/mcp/tool", headers={"X-User-Token": admin_tok}, json={"name": "admin_exportar_reporte_inversor_markdown", "arguments": {}})
        self.assertTrue(r_rep.json().get("ok"))
        self.assertIn("Reporte Ejecutivo SaaS", r_rep.json().get("reporte_markdown", ""))

    def test_11_todo_en_el_chat_sin_salir_del_llm(self):
        from fastapi.testclient import TestClient
        from bot.main import app

        client = TestClient(app)
        cuit_chat = "20444444441"
        email_chat = "chat_only_user@impuesto.test"
        frase = "Mate-Mendoza-Fiscal-7741"

        # 1. Tras OTP verificado, vincula 100% en el chat con frase clave personalizada
        tok_otp = _tok_verificado(email_chat)
        r_v = client.post(
            "/api/v1/mcp/tool",
            headers={"X-LLM-Origin": "gemini", "X-User-Token": tok_otp},
            json={
                "name": "vincular_cuenta_en_chat",
                "arguments": {"email": email_chat, "cuit": cuit_chat, "clave_fiscal": "ClaveTestChat99", "frase_clave": frase},
            },
        )
        self.assertTrue(r_v.json().get("ok"))
        tok_ses = r_v.json().get("token_sesion")
        self.assertEqual(tok_ses, frase)

        # 2. En otro LLM (Claude), inicia sesión 100% en chat sin URL privada
        r_login = client.post(
            "/api/v1/mcp/tool",
            headers={"X-LLM-Origin": "claude"},
            json={"name": "iniciar_sesion_en_chat", "arguments": {"email": email_chat, "frase_clave_o_token": frase}},
        )
        self.assertTrue(r_login.json().get("ok"))
        self.assertEqual(r_login.json().get("usuario"), email_chat)

        # 3. Usa token_sesion en argumentos sin tocar headers/URL -> accede a sus empresas
        r_emp = client.post(
            "/api/v1/mcp/tool",
            headers={"X-LLM-Origin": "claude"},
            json={"name": "listar_empresas", "arguments": {"token_sesion": tok_ses}},
        )
        self.assertTrue(r_emp.json().get("ok"))
        self.assertIn(cuit_chat, [x["cuit"] for x in r_emp.json().get("empresas_vinculadas", [])])

        # Limpieza
        client.delete(f"/api/v1/vincular/{cuit_chat}", headers={"X-User-Token": tok_ses})

    def test_12_login_otp_6_digitos_universal(self):
        from unittest.mock import patch
        from fastapi.testclient import TestClient
        from bot.main import app
        from bot import boveda_segura as bv

        client = TestClient(app)
        em = "finanzas@empresa-microsoft.com.ar"
        captured = {}

        def fake_send(dest, code):
            captured["dest"] = dest
            captured["code"] = code
            return True, "resend"

        with patch.object(bv, "_enviar_email_otp", side_effect=fake_send):
            r_req = client.post(
                "/api/v1/mcp/tool",
                headers={"X-LLM-Origin": "copilot"},
                json={"name": "solicitar_codigo_acceso_email", "arguments": {"email": em}},
            )
            self.assertTrue(r_req.json().get("ok"))
            self.assertEqual(len(captured["code"]), 6)

            # Código incorrecto bloqueado
            r_bad = client.post(
                "/api/v1/mcp/tool",
                headers={"X-LLM-Origin": "copilot"},
                json={"name": "verificar_codigo_acceso_email", "arguments": {"email": em, "codigo": "000000"}},
            )
            self.assertTrue(r_bad.json().get("acceso_denegado"))

            # Código correcto emite token_sesion válido
            r_ok = client.post(
                "/api/v1/mcp/tool",
                headers={"X-LLM-Origin": "copilot"},
                json={"name": "verificar_codigo_acceso_email", "arguments": {"email": em, "codigo": captured["code"]}},
            )
            self.assertTrue(r_ok.json().get("ok"))
            self.assertTrue(r_ok.json().get("token_sesion", "").startswith("imp_live_"))

            # Uso único: reintentar el mismo código falla
            r_reuse = client.post(
                "/api/v1/mcp/tool",
                headers={"X-LLM-Origin": "copilot"},
                json={"name": "verificar_codigo_acceso_email", "arguments": {"email": em, "codigo": captured["code"]}},
            )
            self.assertTrue(r_reuse.json().get("acceso_denegado"))

    def test_13_no_deadlock_ccma_inflight_y_watchdog(self):
        """Regresión crítica: consultar_ccma_cuenta_corriente con auditoría inflight NO debe hacer deadlock en _audit_lock ni bloquear sincrónicamente."""
        import time
        import threading
        from unittest.mock import patch
        from fastapi.testclient import TestClient
        from bot import main as bot_main

        client = TestClient(bot_main.app)
        cuit_test = "20999999992"
        em = "deadlock_test@impuesto.test"

        tok_pre = _tok_verificado(em)
        r_link = client.post(
            "/api/v1/vincular",
            headers={"X-User-Token": tok_pre},
            json={
                "email": em,
                "cuit": cuit_test,
                "clave_fiscal": "ClaveTest123",
                "modo": "solo_lectura_cifrada",
            },
        )
        tok = r_link.json()["token"]

        # 1. Simular auditoría en curso (inflight) y llamar a consultar_ccma_cuenta_corriente
        fake_evt = threading.Event()
        bot_main.AUDIT_CACHE.pop(cuit_test, None)
        bot_main.AUDIT_INFLIGHT[cuit_test] = {"started_at": time.time(), "event": fake_evt, "result": None}
        try:
            with patch.object(bot_main, "AUDIT_SYNC_WAIT_SEC", 0.05):
                t0 = time.time()
                r_ccma = client.post(
                    "/api/v1/mcp/tool",
                    headers={"X-User-Token": tok},
                    json={"name": "consultar_ccma_cuenta_corriente", "arguments": {"cuit": cuit_test}},
                )
                elapsed = time.time() - t0
                self.assertEqual(r_ccma.status_code, 200)
                self.assertEqual(r_ccma.json().get("estado"), "EN_PROGRESO")
                self.assertLess(elapsed, 2.0)
        finally:
            bot_main.AUDIT_INFLIGHT.pop(cuit_test, None)

        # 2. Watchdog: una entrada inflight colgada (> INFLIGHT_MAX_AGE_SEC) debe ser desalojada
        bot_main.AUDIT_INFLIGHT[cuit_test] = {
            "started_at": time.time() - (bot_main.INFLIGHT_MAX_AGE_SEC + 30),
            "event": threading.Event(),
            "result": None,
        }
        with patch.object(bot_main, "auditar_estado_integral_arca", return_value={"ok": True, "cuit": cuit_test}), \
             patch.object(bot_main, "AUDIT_SYNC_WAIT_SEC", 1.0):
            r_fresh = bot_main._ejecutar_auditoria_sin_timeout(cuit_test, "ClaveTest123")
            self.assertTrue(r_fresh.get("ok"))
            self.assertNotEqual(r_fresh.get("estado"), "EN_PROGRESO")
        bot_main.AUDIT_CACHE.pop(cuit_test, None)
        client.delete(f"/api/v1/vincular/{cuit_test}", headers={"X-User-Token": tok})

    def test_14_deteccion_doble_jubilacion_021_y_aut(self):
        """Verifica que el parser CCMA separe 020/021/024 y dispare alerta_doble_aporte_jubilatorio si coexisten 021 y AUT."""
        fixture_doble = """
        10/2026\t020\t019\t019\tObligacion Mensual Monot.\t20/10/2026\t18,246.86
        10/2026\t021\t019\t019\tAporte SIPA Monot.\t20/10/2026\t12,500.00
        +\t \t10/2026\tAUT\t019\t019\tObligacion Mensual Autonomo.\t11/11/2026\t159,563.00
        """
        desg = _parse_ccma_detalle_periodos(fixture_doble)
        self.assertAlmostEqual(desg["monotributo_impositivo_020"], 18246.86, places=2)
        self.assertAlmostEqual(desg["monotributo_jubilacion_021"], 12500.00, places=2)
        self.assertTrue(desg["alerta_doble_aporte_jubilatorio"])

    def test_sec_p0_1_poc_reclamo_email_invitado_bloqueado(self):
        """P0-1 PoC exacto de Claude: owner autoriza a un contador invitado como editor; atacante intenta reclamar ese email sin OTP vía solo_token_llm -> BLOQUEADO."""
        client = TestClient(app)
        cuit_v = "20555555551"
        owner_em = "owner_poc1@impuesto.test"
        contador_em = "contador_invitado_poc1@impuesto.test"

        tok_owner = _tok_verificado(owner_em)
        r1 = client.post("/api/v1/vincular", headers={"X-User-Token": tok_owner}, json={
            "email": owner_em, "cuit": cuit_v, "clave_fiscal": "ClaveReal1",
        })
        self.assertTrue(r1.json().get("ok"))

        # Owner autoriza al contador como editor (el contador todavía no inició sesión nunca)
        r_auth = client.post("/api/v1/mcp/tool", headers={"X-User-Token": tok_owner}, json={
            "name": "autorizar_usuario_cuit",
            "arguments": {"cuit": cuit_v, "email_invitado": contador_em, "rol": "editor"},
        })
        self.assertTrue(r_auth.json().get("ok"))

        # Ataque PoC 1: atacante intenta reclamar contador_em vía POST /api/v1/vincular solo_token_llm sin OTP
        r_attack = client.post("/api/v1/vincular", json={
            "email": contador_em,
            "modo": "solo_token_llm",
            "token_personalizado": "Frase-Atacante-2026-9999",
        })
        self.assertFalse(r_attack.json().get("ok"))
        self.assertTrue(r_attack.json().get("requiere_otp"))
        self.assertIsNone(_bv_mod.resolver_email_por_token("Frase-Atacante-2026-9999"))

        # Admin sin OTP -> también bloqueado
        r_adm = client.post("/api/v1/mcp/tool", json={
            "name": "vincular_cuenta_en_chat",
            "arguments": {"email": "admin_fixture@impuesto.test", "cuit": "20555555559", "clave_fiscal": "Fake123"},
        })
        self.assertFalse(r_adm.json().get("ok"))
        self.assertTrue(r_adm.json().get("requiere_otp"))

    def test_sec_p0_2_poc_pisar_clave_con_email_owner_bloqueado(self):
        """P0-2 PoC exacto de Claude: conociendo solo el email del owner, POST /api/v1/vincular SIN token NO debe pisar la Clave Fiscal."""
        client = TestClient(app)
        cuit_v = "20555555553"
        owner_em = "dueno_poc2@impuesto.test"
        tok_owner = _tok_verificado(owner_em)
        r1 = client.post("/api/v1/vincular", headers={"X-User-Token": tok_owner}, json={
            "email": owner_em, "cuit": cuit_v, "clave_fiscal": "ClaveReal1",
        })
        self.assertTrue(r1.json().get("ok"))

        # Ataque PoC 2: atacante envía email del owner + clave basura sin token
        r_attack = client.post("/api/v1/vincular", json={
            "email": owner_em, "cuit": cuit_v, "clave_fiscal": "basura",
        })
        self.assertFalse(r_attack.json().get("ok"))
        self.assertTrue(r_attack.json().get("requiere_otp"))
        # Verificar que la clave real en la bóveda NO fue pisada
        rec = _bv_mod.obtener_credenciales_descifradas(cuit_v)
        self.assertEqual(rec["clave_fiscal"], "ClaveReal1")

        # Email vacío intentando pisar la clave -> rechazado
        r_empty = client.post("/api/v1/vincular", json={"email": "", "cuit": cuit_v, "clave_fiscal": "Basura999"})
        self.assertFalse(r_empty.json().get("ok"))
        self.assertTrue(r_empty.json().get("acceso_denegado"))

        # Otro usuario intentando DELETE -> 403
        tok_other = _tok_verificado("intruso_p02@impuesto.test")
        self.assertEqual(client.delete(f"/api/v1/vincular/{cuit_v}", headers={"X-User-Token": tok_other}).status_code, 403)

    def test_sec_p0_5_emision_cruzada_idempotencia_y_confirmado_estricto(self):
        """P0-5 + R1: cuit_emisor != cuit autorizado es bloqueado, confirmado='false' NO es True, y confirmado=true exige idempotency_key y no duplica CAE."""
        from unittest.mock import patch
        from bot import main as bot_main
        from bot import arca_ws
        self.assertFalse(bot_main._parse_bool_strict("false"))
        self.assertFalse(bot_main._parse_bool_strict("0"))
        self.assertTrue(bot_main._parse_bool_strict(True))
        self.assertTrue(bot_main._parse_bool_strict("true"))

        client = TestClient(app)
        cuit_propio = "20555555554"
        tok_pre = _tok_verificado("emisor_p05@impuesto.test")
        r_v = client.post("/api/v1/vincular", headers={"X-User-Token": tok_pre}, json={
            "email": "emisor_p05@impuesto.test", "cuit": cuit_propio, "clave_fiscal": "Clave1",
        })
        tok = r_v.json()["token"]
        # 1. Emisión cruzada bloqueada
        r_cross = client.post("/api/v1/mcp/tool", headers={"X-User-Token": tok}, json={
            "name": "emitir_factura_wsfe",
            "arguments": {"cuit": cuit_propio, "cuit_emisor": "30715875086", "cbte_tipo": 11, "importe_neto": 100, "confirmado": "false"},
        })
        self.assertFalse(r_cross.json().get("ok"))
        self.assertTrue(r_cross.json().get("acceso_denegado"))

        # 2. confirmado=true sin idempotency_key -> rechazado
        r_noidem = client.post("/api/v1/mcp/tool", headers={"X-User-Token": tok}, json={
            "name": "emitir_factura_wsfe",
            "arguments": {"cuit": cuit_propio, "cuit_emisor": cuit_propio, "cbte_tipo": 11, "importe_neto": 100, "confirmado": True},
        })
        self.assertFalse(r_noidem.json().get("ok"))

        # 3. confirmado=true con idempotency_key -> 2 llamadas solo emiten 1 CAE
        emisiones = {"n": 0}
        def fake_emit(**kw):
            emisiones["n"] += 1
            return {"ok": True, "cae": "76471234567890", "cbte_nro": 1}
        with patch.object(arca_ws, "emitir_comprobante_wsfe", side_effect=fake_emit):
            payload = {
                "name": "emitir_factura_wsfe",
                "arguments": {"cuit": cuit_propio, "cuit_emisor": cuit_propio, "cbte_tipo": 11, "importe_neto": 100, "confirmado": True, "idempotency_key": "venta-0001"},
            }
            r_e1 = client.post("/api/v1/mcp/tool", headers={"X-User-Token": tok}, json=payload)
            r_e2 = client.post("/api/v1/mcp/tool", headers={"X-User-Token": tok}, json=payload)
            self.assertTrue(r_e1.json().get("ok"))
            self.assertTrue(r_e2.json().get("idempotente_reusado"))
            self.assertEqual(emisiones["n"], 1)

    def test_sec_p0_6_parser_ar_num_estricto(self):
        """P0-6: _parse_ar_num distingue miles de decimales y no devuelve 0 silencioso en strict=True."""
        self.assertAlmostEqual(_parse_ar_num("1.234.567"), 1234567.0, places=2)
        self.assertAlmostEqual(_parse_ar_num("1,5"), 1.5, places=2)
        self.assertAlmostEqual(_parse_ar_num("1.426.512,52"), 1426512.52, places=2)
        self.assertAlmostEqual(_parse_ar_num("1,172,263.79"), 1172263.79, places=2)
        with self.assertRaises(ValueError):
            _parse_ar_num("N/A", strict=True)

    def test_sec_p0_7_circuit_breaker_y_recheck_en_lock(self):
        """P0-7: tras 1 error CLAVE_FISCAL_INCORRECTA, el circuit breaker frena nuevos logins incluso si otra tool estaba esperando el lock."""
        from unittest.mock import patch
        from bot import main as bot_main
        cuit_cb = "20555555555"
        calls = {"n": 0}
        def fake_bad_login(cuit, clave):
            calls["n"] += 1
            raise RuntimeError("CLAVE_FISCAL_INCORRECTA: ARCA informó 'Clave o usuario incorrecto'")

        bot_main._clear_bad_creds(cuit_cb)
        with patch.object(bot_main, "auditar_estado_integral_arca", side_effect=fake_bad_login), \
             patch.object(bot_main, "AUDIT_SYNC_WAIT_SEC", 1.0):
            r1 = bot_main._ejecutar_auditoria_sin_timeout(cuit_cb, "Mala123")
            self.assertEqual(r1.get("estado"), "CLAVE_FISCAL_INCORRECTA")
            r2 = bot_main._ejecutar_auditoria_sin_timeout(cuit_cb, "Mala123", forzar_refresco=True)
            self.assertTrue(r2.get("circuit_breaker_activo"))
            self.assertEqual(calls["n"], 1)
        bot_main._clear_bad_creds(cuit_cb)

    def test_sec_r2_limite_login_3_niveles(self):
        """R2: el limitador de 3 niveles frena fuerza bruta por IP+usuario sin bloquear 24h."""
        from bot.limite_login import LimiteLogin
        lim = LimiteLogin(por_ip_usuario=3, por_usuario=10, global_por_min=50)
        for _ in range(3):
            lim.registrar_fallo("1.2.3.4", "user@test.com")
        ok, msg = lim.chequear("1.2.3.4", "user@test.com")
        self.assertFalse(ok)
        self.assertIn("Esperá", msg)
        # Otra IP todavía puede operar hasta el umbral por usuario (sin DoS de 24h)
        ok_other, _ = lim.chequear("5.6.7.8", "user@test.com")
        self.assertTrue(ok_other)


if __name__ == "__main__":
    unittest.main()
