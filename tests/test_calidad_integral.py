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
os.environ["IMPUESTO_ENV"] = "test"
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

        # 4. Owner validado autoriza a socio por email desde Claude
        bv.marcar_cuit_validado(cuit_test)
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

        # Owner validado autoriza al contador como editor (el contador todavía no inició sesión nunca)
        _bv_mod.marcar_cuit_validado(cuit_v)
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
        _bv_mod.marcar_cuit_validado(cuit_propio)
        # 1. Emisión cruzada bloqueada
        r_cross = client.post("/api/v1/mcp/tool", headers={"X-User-Token": tok}, json={
            "name": "emitir_factura_wsfe",
            "arguments": {"cuit": cuit_propio, "cuit_emisor": "30715875086", "cbte_tipo": 11, "importe_neto": 100, "confirmado": "false"},
        })
        self.assertFalse(r_cross.json().get("ok"))
        self.assertTrue(r_cross.json().get("acceso_denegado"))

        # 2. confirmado=true con huella de servidor (idempotency_key opcional) -> 2 llamadas solo emiten 1 CAE
        emisiones = {"n": 0}
        def fake_emit(**kw):
            emisiones["n"] += 1
            return {"ok": True, "cae": "76471234567890", "cbte_nro": 1}
        with patch.object(arca_ws, "obtener_ultimo_autorizado_wsfe", return_value=0), \
             patch.object(arca_ws, "emitir_comprobante_wsfe", side_effect=fake_emit):
            payload = {
                "name": "emitir_factura_wsfe",
                "arguments": {"cuit": cuit_propio, "cuit_emisor": cuit_propio, "cbte_tipo": 11, "importe_neto": 100, "confirmado": True, "idempotency_key": "venta-0001"},
            }
            r_e1 = client.post("/api/v1/mcp/tool", headers={"X-User-Token": tok}, json=payload)
            r_e2 = client.post("/api/v1/mcp/tool", headers={"X-User-Token": tok}, json=payload)
            self.assertTrue(r_e1.json().get("ok"))
            self.assertTrue(r_e2.json().get("replay"))
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

    def test_sec_n1_ataque3_secuestro_cuit_y_logins_fallidos_bloqueado(self):
        """N1 / Ataque 3 de Claude: atacante con email verificado intenta vincular CUIT ajeno con 5 claves distintas -> máx. 2 logins en 24h y el CUIT se libera tras fallo."""
        from unittest.mock import patch
        from bot import main as bot_main
        client = TestClient(app)
        cuit_ajeno = "20777777771"
        atacante = "atacante_n1@impuesto.test"
        tok_att = _tok_verificado(atacante)

        logins = {"n": 0}
        def fake_bad_arca(cuit, clave):
            logins["n"] += 1
            raise RuntimeError("CLAVE_FISCAL_INCORRECTA: ARCA informó 'Clave o usuario incorrecto'")

        bot_main._clear_bad_creds(cuit_ajeno, clear_budget=True)
        with patch.object(bot_main, "auditar_estado_integral_arca", side_effect=fake_bad_arca), \
             patch.object(bot_main, "AUDIT_SYNC_WAIT_SEC", 1.0):
            for idx in range(5):
                clave_falsa = f"MalaClave{idx}"
                r_v = client.post("/api/v1/vincular", headers={"X-User-Token": tok_att}, json={
                    "email": atacante, "cuit": cuit_ajeno, "clave_fiscal": clave_falsa,
                })
                if r_v.json().get("ok"):
                    bot_main._ejecutar_auditoria_sin_timeout(cuit_ajeno, clave_falsa, forzar_refresco=True)
            # Presupuesto por CUIT corta en 2 logins en 24h (nunca 5!)
            self.assertLessEqual(logins["n"], bot_main.CUIT_MAX_FAILS_24H)
            # Y el CUIT fue liberado (no quedó secuestrado por el atacante)
            self.assertIsNone(_bv_mod.obtener_credenciales_descifradas(cuit_ajeno))
        bot_main._clear_bad_creds(cuit_ajeno, clear_budget=True)

    def test_sec_n3_ataque4_70_otp_aleatorios_no_bloquean_usuario_legitimo(self):
        """N3 / Ataque 4 de Claude: 70 pedidos de OTP con emails e IPs aleatorios NO deben bloquear a un usuario legítimo."""
        from unittest.mock import patch
        from bot import limite_login as ll
        # Usar instancia limpia para no interferir con otros tests
        fresh_lim = ll.LimiteLogin(por_ip_usuario=3, por_usuario=5, por_ip=5, global_por_min=600)
        with patch.object(ll, "LIMITE_OTP_ENVIO", fresh_lim), \
             patch.object(_bv_mod, "_enviar_email_otp", return_value=(True, "resend")):
            for i in range(70):
                _bv_mod.solicitar_codigo_otp_email(f"rand{i}@evil.test", client_ip=f"10.0.{i // 250}.{i % 250 + 1}")
            # Usuario legítimo desde su IP sigue pudiendo pedir OTP sin DoS global
            r_legit = _bv_mod.solicitar_codigo_otp_email("usuario_real@empresa.com.ar", client_ip="200.1.2.3")
            self.assertTrue(r_legit.get("ok"), f"Usuario legítimo bloqueado por DoS global: {r_legit}")

    def test_sec_n1c_timeout_no_reconocido_y_presupuesto_persistido(self):
        """N1-c + N1-d: TimeoutError en login ARCA consume presupuesto persistido en volumen y bloquea en <= CUIT_MAX_FAILS_24H tras reinicio."""
        from unittest.mock import patch
        from bot import main as bot_main
        cuit_t = "20777777772"
        calls = {"n": 0}
        def fake_timeout(cuit, clave):
            calls["n"] += 1
            raise TimeoutError("Timeout 25000ms exceeded waiting for URL **/portalcf.cloud.**")

        bot_main._clear_bad_creds(cuit_t, clear_budget=True)
        with patch.object(bot_main, "auditar_estado_integral_arca", side_effect=fake_timeout), \
             patch.object(bot_main, "AUDIT_SYNC_WAIT_SEC", 1.0):
            for i in range(4):
                bot_main._ejecutar_auditoria_sin_timeout(cuit_t, f"Pass{i}", forzar_refresco=True)
            self.assertLessEqual(calls["n"], bot_main.CUIT_MAX_FAILS_24H)
            # Simular reinicio del proceso limpiando RAM: el presupuesto persiste en volumen
            bot_main._CUIT_FAIL_BUDGET.clear()
            bot_main._BAD_CREDS_CB.clear()
            r_after = bot_main._ejecutar_auditoria_sin_timeout(cuit_t, "PassNueva", forzar_refresco=True)
            self.assertEqual(r_after.get("estado"), "PRESUPUESTO_FALLOS_CUIT_AGOTADO")
            self.assertLessEqual(calls["n"], bot_main.CUIT_MAX_FAILS_24H)
        bot_main._clear_bad_creds(cuit_t, clear_budget=True)

    def test_sec_n1g_carrera_vinculacion_rechazo_inflight_y_restauracion_owner(self):
        """N1-g (Prueba A): rechaza reemplazo de pendiente durante AUDIT_INFLIGHT/TOOL_INFLIGHT y restaura owner+clave en mismatch."""
        import threading
        import time as _t
        from unittest.mock import patch
        from bot import main as bot_main

        class _DeferredExec:
            def __init__(self):
                self.q = []
            def submit(self, fn, *a, **k):
                self.q.append((fn, a, k))
            def run_all(self):
                while self.q:
                    fn, a, k = self.q.pop(0)
                    fn(*a, **k)

        client = TestClient(bot_main.app)
        cuit_v = "27123456781"
        tok_real = _tok_verificado("real_n1g@impuesto.test")
        tok_att = _tok_verificado("att_n1g@impuesto.test")
        bot_main._clear_bad_creds(cuit_v, clear_budget=True)
        bot_main.AUDIT_INFLIGHT.pop(cuit_v, None)

        dex = _DeferredExec()
        def fake_arca_ok(cuit, clave):
            if clave == "LaVerdadera1":
                return {"ok": True, "doublecheck": {"fuentes_verificadas": ["ccma"]}}
            raise RuntimeError("CLAVE_FISCAL_INCORRECTA: ARCA informó 'Clave o usuario incorrecto'")

        old_prewarm = os.environ.pop("DISABLE_AUDIT_PREWARM", None)
        try:
            with patch.object(bot_main, "executor", dex), \
                 patch.object(bot_main, "auditar_estado_integral_arca", side_effect=fake_arca_ok), \
                 patch.object(bot_main, "AUDIT_SYNC_WAIT_SEC", 0.2):
                r_real = client.post("/api/v1/mcp/tool", headers={"X-User-Token": tok_real}, json={
                    "name": "vincular_cuenta_en_chat",
                    "arguments": {"email": "real_n1g@impuesto.test", "cuit": cuit_v, "clave_fiscal": "LaVerdadera1"},
                }).json()
                self.assertTrue(r_real.get("ok"))

                # Atacante intenta reemplazar mientras el login del dueño sigue en AUDIT_INFLIGHT -> VALIDACION_EN_CURSO
                r_att = client.post("/api/v1/mcp/tool", headers={"X-User-Token": tok_att}, json={
                    "name": "vincular_cuenta_en_chat",
                    "arguments": {"email": "att_n1g@impuesto.test", "cuit": cuit_v, "clave_fiscal": "Basura"},
                }).json()
                self.assertFalse(r_att.get("ok"))
                self.assertEqual(r_att.get("estado"), "VALIDACION_EN_CURSO")

                # Al terminar el login del dueño real, queda owner VALIDADO con su clave real
                dex.run_all()
                self.assertTrue(_bv_mod.es_owner_validado("real_n1g@impuesto.test", cuit_v))
                self.assertEqual(_bv_mod.obtener_credenciales_descifradas(cuit_v)["clave_fiscal"], "LaVerdadera1")

                # También rechazar reemplazo cuando hay un TOOL_INFLIGHT activo sobre un CUIT pendiente
                cuit_tool = "27123456782"
                _bv_mod.guardar_credenciales_cifradas(cuit=cuit_tool, clave_fiscal="ClaveTool1", owner_email="real_n1g@impuesto.test")
                bot_main.TOOL_INFLIGHT[f"ccma:{cuit_tool}"] = {
                    "started_at": _t.time(), "event": threading.Event(), "result": None, "cuit": cuit_tool, "usa_login": True,
                }
                try:
                    r_att_tool = client.post("/api/v1/vincular", headers={"X-User-Token": tok_att}, json={
                        "email": "att_n1g@impuesto.test", "cuit": cuit_tool, "clave_fiscal": "BasuraTool",
                    }).json()
                    self.assertFalse(r_att_tool.get("ok"))
                    self.assertEqual(r_att_tool.get("estado"), "VALIDACION_EN_CURSO")
                finally:
                    bot_main.TOOL_INFLIGHT.pop(f"ccma:{cuit_tool}", None)
        finally:
            if old_prewarm is not None:
                os.environ["DISABLE_AUDIT_PREWARM"] = old_prewarm

        # Capa 2 directa: aunque una carrera hubiera pisado la entrada pendiente, marcar_cuit_validado restaura al actor exitoso y su clave
        cuit_race = "27123456783"
        _bv_mod.guardar_credenciales_cifradas(cuit=cuit_race, clave_fiscal="ClaveRealRace", owner_email="real_race@impuesto.test")
        _bv_mod.guardar_credenciales_cifradas(cuit=cuit_race, clave_fiscal="BasuraRace", owner_email="att_race@impuesto.test")
        h_real = _bv_mod.hash_clave_cuit(cuit_race, "ClaveRealRace")
        # Sin clave_fiscal para restaurar -> nunca valida al atacante
        self.assertFalse(_bv_mod.marcar_cuit_validado(cuit_race, email_actor="real_race@impuesto.test", clave_hash=h_real))
        self.assertFalse(_bv_mod.es_owner_validado("att_race@impuesto.test", cuit_race))
        # Con clave_fiscal del login exitoso -> restaura al dueño real como owner validado con su clave
        self.assertTrue(_bv_mod.marcar_cuit_validado(cuit_race, email_actor="real_race@impuesto.test", clave_hash=h_real, clave_fiscal="ClaveRealRace"))
        self.assertTrue(_bv_mod.es_owner_validado("real_race@impuesto.test", cuit_race))
        self.assertEqual(_bv_mod.obtener_credenciales_descifradas(cuit_race)["clave_fiscal"], "ClaveRealRace")

    def test_sec_n1h_clasificacion_por_etapa_y_owner_validado_resiste_arca_lenta(self):
        """N1-h (Prueba B): timeout de page.goto ANTES de enviar contraseña no consume presupuesto ni bloquea a un owner validado; LoginNoConfirmado no crea CB de clave incorrecta."""
        from unittest.mock import patch, MagicMock
        from playwright.sync_api import TimeoutError as PWTimeout
        from bot import main as bot_main
        from bot.arca_errors import ArcaNoDisponible, LoginNoConfirmado, ClaveIncorrecta
        from bot.auditoria_unificada import _login_portal_cf
        from bot.scraper import _login_arca

        # 1. Clasificación por etapa en _login_portal_cf y _login_arca
        p_goto_fail = MagicMock()
        p_goto_fail.goto.side_effect = PWTimeout('page.goto: Timeout 30000ms exceeded.\nnavigating to "https://auth.afip.gob.ar/contribuyente_/login.xhtml"')
        with self.assertRaises(ArcaNoDisponible):
            _login_portal_cf(p_goto_fail, "20987654321", "ClaveOk1")
        with self.assertRaises(ArcaNoDisponible):
            _login_arca(p_goto_fail, "20987654321", "ClaveOk1")

        p_post_pw = MagicMock()
        p_post_pw.url = "https://auth.afip.gob.ar/contribuyente_/login.xhtml"
        p_post_pw.inner_text.return_value = "Cargando..."
        p_post_pw.query_selector.return_value = None
        p_post_pw.wait_for_url.side_effect = PWTimeout("Timeout 25000ms exceeded waiting for URL **/portalcf.cloud.**")
        with patch("time.sleep", return_value=None):
            with self.assertRaises(LoginNoConfirmado):
                _login_portal_cf(p_post_pw, "20987654321", "ClaveOk1")

        p_bad_pw = MagicMock()
        p_bad_pw.url = "https://auth.afip.gob.ar/contribuyente_/login.xhtml"
        p_bad_pw.inner_text.return_value = "Clave o usuario incorrecto"
        with self.assertRaises(ClaveIncorrecta):
            _login_portal_cf(p_bad_pw, "20987654321", "ClaveMala")

        # 2. Flujo completo Prueba B: owner validado + 2 timeouts de page.goto -> presupuesto 0 y sigue operando cuando ARCA vuelve
        client = TestClient(bot_main.app)
        cuit_w = "20987654321"
        em_w = "valido_n1h@impuesto.test"
        tok_w = _tok_verificado(em_w)
        bot_main._clear_bad_creds(cuit_w, clear_budget=True)
        _bv_mod.guardar_credenciales_cifradas(cuit=cuit_w, clave_fiscal="ClaveOk1", owner_email=em_w)
        _bv_mod.marcar_cuit_validado(cuit_w, email_actor=em_w, clave_hash=_bv_mod.hash_clave_cuit(cuit_w, "ClaveOk1"), clave_fiscal="ClaveOk1")

        modo = {"v": "arca_lento"}
        logins = {"n": 0}
        def fake_arca_b(cuit, clave):
            logins["n"] += 1
            if modo["v"] == "arca_lento":
                raise PWTimeout('page.goto: Timeout 30000ms exceeded.\nnavigating to "https://auth.afip.gob.ar/contribuyente_/login.xhtml", waiting until "domcontentloaded"')
            if modo["v"] == "login_no_confirmado":
                raise LoginNoConfirmado("Timeout esperando portalcf.cloud")
            return {"ok": True, "doublecheck": {"fuentes_verificadas": ["ccma"]}}

        with patch.object(bot_main, "auditar_estado_integral_arca", side_effect=fake_arca_b), \
             patch.object(bot_main, "AUDIT_SYNC_WAIT_SEC", 1.0):
            for _ in range(2):
                r_slow = client.post("/api/v1/mcp/tool", headers={"X-User-Token": tok_w}, json={
                    "name": "auditar_estado_integral_arca", "arguments": {"cuit": cuit_w, "forzar_refresco": True},
                }).json()
                self.assertEqual(r_slow.get("estado"), "ARCA_TEMPORALMENTE_NO_DISPONIBLE")
            self.assertEqual(len(bot_main._CUIT_FAIL_BUDGET.get(cuit_w, [])), 0)

            modo["v"] = "ok"
            r_ok = client.post("/api/v1/mcp/tool", headers={"X-User-Token": tok_w}, json={
                "name": "auditar_estado_integral_arca", "arguments": {"cuit": cuit_w, "forzar_refresco": True},
            }).json()
            self.assertTrue(r_ok.get("ok"))
            self.assertEqual(logins["n"], 3)

            # LoginNoConfirmado para owner validado: descuenta presupuesto, estado LOGIN_NO_CONFIRMADO, sin CB de clave incorrecta
            modo["v"] = "login_no_confirmado"
            r_lnc = client.post("/api/v1/mcp/tool", headers={"X-User-Token": tok_w}, json={
                "name": "auditar_estado_integral_arca", "arguments": {"cuit": cuit_w, "forzar_refresco": True},
            }).json()
            self.assertEqual(r_lnc.get("estado"), "LOGIN_NO_CONFIRMADO")
            self.assertEqual(len(bot_main._CUIT_FAIL_BUDGET.get(cuit_w, [])), 1)
            self.assertNotIn(cuit_w, bot_main._BAD_CREDS_CB)

            modo["v"] = "ok"
            r_recov = client.post("/api/v1/mcp/tool", headers={"X-User-Token": tok_w}, json={
                "name": "auditar_estado_integral_arca", "arguments": {"cuit": cuit_w, "forzar_refresco": True},
            }).json()
            self.assertTrue(r_recov.get("ok"))
        bot_main._clear_bad_creds(cuit_w, clear_budget=True)

    def test_sec_n1i_purga_pendientes_borra_boveda_created_at_y_refresco_persistido(self):
        """N1-i (Prueba C): purga por vencimiento borra ACL y bóveda, mide desde created_at, y el cooldown de refresco persiste en volumen."""
        from unittest.mock import patch
        import datetime as _dt

        cuit_x = "20111111112"
        _bv_mod.guardar_credenciales_cifradas(cuit=cuit_x, clave_fiscal="ClavePendiente", owner_email="pend_n1i@impuesto.test")
        with patch.object(_bv_mod, "PENDING_TTL_SEC", -1):
            _bv_mod.listar_cuits_autorizados("pend_n1i@impuesto.test")
        self.assertNotIn(cuit_x, _bv_mod._load_acl()["cuit_acl"])
        self.assertIsNone(_bv_mod.obtener_credenciales_descifradas(cuit_x))

        # Vencimiento se mide desde created_at (actualizar updated_at no renueva indefinidamente)
        viejo = (_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(seconds=3600)).isoformat()
        ahora = _dt.datetime.now(_dt.timezone.utc).isoformat()
        self.assertTrue(_bv_mod._es_pendiente_vencido({"validado": False, "created_at": viejo, "updated_at": ahora}))

        # Cooldown de forzar_refresco persiste en volumen (pending_refresh.enc)
        cuit_ref = "20111111119"
        _bv_mod.limpiar_refresco_no_validado(cuit_ref)
        ok1, _ = _bv_mod.verificar_y_marcar_refresco_no_validado(cuit_ref, cooldown_seg=600.0)
        ok2, wait_s = _bv_mod.verificar_y_marcar_refresco_no_validado(cuit_ref, cooldown_seg=600.0)
        self.assertTrue(ok1)
        self.assertFalse(ok2)
        self.assertGreater(wait_s, 0)
        _bv_mod.limpiar_refresco_no_validado(cuit_ref)

    def test_sec_n1j_tools_fail_closed(self):
        """N1-j: _run_tool_sin_timeout clasifica fallos post-contraseña en fail-closed, descuenta presupuesto y libera CUIT pendiente."""
        from unittest.mock import patch
        from bot import main as bot_main
        from bot.arca_errors import LoginNoConfirmado
        client = TestClient(app)

        cuit_j = "20333222111"
        em_j = "att_n1j@impuesto.test"
        tok_j = _tok_verificado(em_j)
        bot_main._clear_bad_creds(cuit_j, clear_budget=True)
        _bv_mod.guardar_credenciales_cifradas(cuit=cuit_j, clave_fiscal="MalaPassJ", owner_email=em_j)

        calls = {"n": 0}
        def fake_ccma_fail(cuit, clave):
            calls["n"] += 1
            raise LoginNoConfirmado("Timeout esperando portalcf.cloud tras enviar contraseña")

        with patch("bot.auditoria_unificada.consultar_ccma_preciso", side_effect=fake_ccma_fail), \
             patch.object(bot_main, "ERROR_TTL_SEC", 0), \
             patch.object(bot_main, "AUDIT_SYNC_WAIT_SEC", 1.0):
            for _ in range(5):
                client.post("/api/v1/mcp/tool", headers={"X-User-Token": tok_j}, json={
                    "name": "consultar_ccma_cuenta_corriente",
                    "arguments": {"cuit": cuit_j},
                })
        self.assertLessEqual(calls["n"], bot_main.CUIT_MAX_FAILS_24H)
        self.assertGreaterEqual(len(bot_main._CUIT_FAIL_BUDGET.get(cuit_j, [])), 1)
        self.assertIsNone(_bv_mod.obtener_credenciales_descifradas(cuit_j))
        bot_main._clear_bad_creds(cuit_j, clear_budget=True)

    def test_sec_n4_wsfe_idempotencia_persistente_y_adopcion(self):
        """Fase 3.1 / N4: idempotencia WSFE persistente en volumen + adopción de CAE (casos a, b, c, d del spec)."""
        import datetime as _dt
        from unittest.mock import patch
        from bot import main as bot_main
        from bot import arca_ws
        client = TestClient(app)

        cuit_em = "20555555558"
        em_user = "emisor_n4@impuesto.test"
        tok = _tok_verificado(em_user)
        _bv_mod.guardar_credenciales_cifradas(cuit=cuit_em, clave_fiscal="ClaveN4", owner_email=em_user)
        _bv_mod.marcar_cuit_validado(cuit_em, email_actor=em_user, clave_hash=_bv_mod.hash_clave_cuit(cuit_em, "ClaveN4"), clave_fiscal="ClaveN4")
        hoy = _dt.datetime.now().strftime("%Y%m%d")

        # (a) ARCA autoriza pero la respuesta se pierde; reintento llega con OTRA key -> adopta 1 solo CAE
        state_a = {"emits": 0, "ultimo": 10, "comps": {}}
        def emit_drop_a(**kw):
            state_a["emits"] += 1
            state_a["ultimo"] = 11
            state_a["comps"][11] = {
                "cbte_nro": 11, "pto_vta": 1, "cbte_tipo": 11,
                "cae": "76479999000011", "cae_vencimiento": "20261207",
                "imp_total": 1500.00, "doc_tipo": 80, "doc_nro": 30715875086, "cbte_fch": hoy,
            }
            raise TimeoutError("Read timed out esperando respuesta SOAP FECAESolicitar")

        with patch.object(arca_ws, "obtener_ultimo_autorizado_wsfe", side_effect=lambda **kw: state_a["ultimo"]), \
             patch.object(arca_ws, "consultar_comprobante_por_nro_wsfe", side_effect=lambda **kw: state_a["comps"].get(kw["cbte_nro"])), \
             patch.object(arca_ws, "emitir_comprobante_wsfe", side_effect=emit_drop_a):
            r1 = client.post("/api/v1/mcp/tool", headers={"X-User-Token": tok}, json={
                "name": "emitir_factura_wsfe",
                "arguments": {
                    "cuit": cuit_em, "cuit_emisor": cuit_em, "pto_vta": 1, "cbte_tipo": 11,
                    "receptor_cuit": "30715875086", "importe_neto": 1500.0, "importe_iva": 0.0,
                    "confirmado": True, "idempotency_key": "llm-key-1",
                },
            }).json()
            self.assertFalse(r1.get("ok"))
            self.assertEqual(r1.get("estado"), "ESTADO_INCIERTO_REQUIERE_REVISION")

            # Reintento con OTRA key (llm-key-2): debe reconciliar y adoptar el CAE sin re-emitir
            r2 = client.post("/api/v1/mcp/tool", headers={"X-User-Token": tok}, json={
                "name": "emitir_factura_wsfe",
                "arguments": {
                    "cuit": cuit_em, "cuit_emisor": cuit_em, "pto_vta": 1, "cbte_tipo": 11,
                    "receptor_cuit": "30715875086", "importe_neto": 1500.0, "importe_iva": 0.0,
                    "confirmado": True, "idempotency_key": "llm-key-2",
                },
            }).json()
            self.assertTrue(r2.get("ok"))
            self.assertTrue(r2.get("adoptado"))
            self.assertEqual(r2.get("cae"), "76479999000011")
            self.assertEqual(state_a["emits"], 1)

        # (b) Lo mismo con un reinicio de proceso (se limpia toda la RAM) -> adopta igual desde volumen
        state_b = {"emits": 0, "ultimo": 20, "comps": {}}
        def emit_drop_b(**kw):
            state_b["emits"] += 1
            state_b["ultimo"] = 21
            state_b["comps"][21] = {
                "cbte_nro": 21, "pto_vta": 1, "cbte_tipo": 11,
                "cae": "76479999000021", "cae_vencimiento": "20261207",
                "imp_total": 2500.00, "doc_tipo": 80, "doc_nro": 30715875086, "cbte_fch": hoy,
            }
            raise ConnectionError("Connection reset by peer")

        with patch.object(arca_ws, "obtener_ultimo_autorizado_wsfe", side_effect=lambda **kw: state_b["ultimo"]), \
             patch.object(arca_ws, "consultar_comprobante_por_nro_wsfe", side_effect=lambda **kw: state_b["comps"].get(kw["cbte_nro"])), \
             patch.object(arca_ws, "emitir_comprobante_wsfe", side_effect=emit_drop_b):
            r_b1 = client.post("/api/v1/mcp/tool", headers={"X-User-Token": tok}, json={
                "name": "emitir_factura_wsfe",
                "arguments": {
                    "cuit": cuit_em, "cuit_emisor": cuit_em, "pto_vta": 1, "cbte_tipo": 11,
                    "receptor_cuit": "30715875086", "importe_neto": 2500.0, "importe_iva": 0.0,
                    "confirmado": True,
                },
            }).json()
            self.assertEqual(r_b1.get("estado"), "ESTADO_INCIERTO_REQUIERE_REVISION")
            # Simular reinicio de proceso limpiando cachés y locks en memoria
            bot_main._WSFE_IDEM_CACHE.clear()
            getattr(bot_main, "_WSFE_EMIT_LOCKS", {}).clear()
            r_b2 = client.post("/api/v1/mcp/tool", headers={"X-User-Token": tok}, json={
                "name": "emitir_factura_wsfe",
                "arguments": {
                    "cuit": cuit_em, "cuit_emisor": cuit_em, "pto_vta": 1, "cbte_tipo": 11,
                    "receptor_cuit": "30715875086", "importe_neto": 2500.0, "importe_iva": 0.0,
                    "confirmado": True,
                },
            }).json()
            self.assertTrue(r_b2.get("ok"))
            self.assertTrue(r_b2.get("adoptado"))
            self.assertEqual(r_b2.get("cae"), "76479999000021")
            self.assertEqual(state_b["emits"], 1)

        # (c) Dos ventas idénticas con reemitir_aunque_duplicado=True -> 2 CAE y queda en historial
        state_c = {"n": 30}
        def emit_ok_c(**kw):
            state_c["n"] += 1
            return {"ok": True, "resultado": "APROBADO", "cae": f"764700000000{state_c['n']}", "cbte_nro": state_c["n"]}

        with patch.object(arca_ws, "obtener_ultimo_autorizado_wsfe", side_effect=lambda **kw: state_c["n"]), \
             patch.object(arca_ws, "emitir_comprobante_wsfe", side_effect=emit_ok_c):
            rc1 = client.post("/api/v1/mcp/tool", headers={"X-User-Token": tok}, json={
                "name": "emitir_factura_wsfe",
                "arguments": {
                    "cuit": cuit_em, "cuit_emisor": cuit_em, "pto_vta": 1, "cbte_tipo": 11,
                    "receptor_cuit": "", "importe_neto": 5000.0, "importe_iva": 0.0, "confirmado": True,
                },
            }).json()
            rc2 = client.post("/api/v1/mcp/tool", headers={"X-User-Token": tok}, json={
                "name": "emitir_factura_wsfe",
                "arguments": {
                    "cuit": cuit_em, "cuit_emisor": cuit_em, "pto_vta": 1, "cbte_tipo": 11,
                    "receptor_cuit": "", "importe_neto": 5000.0, "importe_iva": 0.0,
                    "confirmado": True, "reemitir_aunque_duplicado": True,
                },
            }).json()
            self.assertTrue(rc1.get("ok"))
            self.assertTrue(rc2.get("ok"))
            self.assertNotEqual(rc1.get("cae"), rc2.get("cae"))
            self.assertEqual(state_c["n"], 32)
            hist = _bv_mod.obtener_historial_actividad(em_user, cuit=cuit_em, limite=10)
            self.assertIn("reemitir_aunque_duplicado", str(hist))

        # (d) El importe en ARCA NO coincide -> ESTADO_INCIERTO_REQUIERE_REVISION, sin re-emisión
        state_d = {"emits": 0, "ultimo": 40}
        def emit_drop_d(**kw):
            state_d["emits"] += 1
            state_d["ultimo"] = 41
            raise TimeoutError("Timeout WSFE")

        comp_distinto = {
            "cbte_nro": 41, "pto_vta": 1, "cbte_tipo": 11,
            "cae": "76479999000041", "cae_vencimiento": "20261207",
            "imp_total": 9999.99, "doc_tipo": 80, "doc_nro": 30715875086, "cbte_fch": hoy,
        }
        with patch.object(arca_ws, "obtener_ultimo_autorizado_wsfe", side_effect=lambda **kw: state_d["ultimo"]), \
             patch.object(arca_ws, "consultar_comprobante_por_nro_wsfe", return_value=comp_distinto), \
             patch.object(arca_ws, "emitir_comprobante_wsfe", side_effect=emit_drop_d):
            rd1 = client.post("/api/v1/mcp/tool", headers={"X-User-Token": tok}, json={
                "name": "emitir_factura_wsfe",
                "arguments": {
                    "cuit": cuit_em, "cuit_emisor": cuit_em, "pto_vta": 1, "cbte_tipo": 11,
                    "receptor_cuit": "30715875086", "importe_neto": 4321.0, "importe_iva": 0.0, "confirmado": True,
                },
            }).json()
            self.assertEqual(rd1.get("estado"), "ESTADO_INCIERTO_REQUIERE_REVISION")
            rd2 = client.post("/api/v1/mcp/tool", headers={"X-User-Token": tok}, json={
                "name": "emitir_factura_wsfe",
                "arguments": {
                    "cuit": cuit_em, "cuit_emisor": cuit_em, "pto_vta": 1, "cbte_tipo": 11,
                    "receptor_cuit": "30715875086", "importe_neto": 4321.0, "importe_iva": 0.0, "confirmado": True,
                },
            }).json()
            self.assertFalse(rd2.get("ok"))
            self.assertEqual(rd2.get("estado"), "ESTADO_INCIERTO_REQUIERE_REVISION")
            self.assertEqual(state_d["emits"], 1)

    def test_sec_n4_bcde_ventana_override_tz_y_respuesta_sin_resultado(self):
        """Cierre N4-b, N4-c, N4-d, N4-e: INCIERTO bloquea sin ventana y sin override, fecha AR 23:30 ART, y XML sin <Resultado> -> INCIERTO."""
        import datetime as _dt
        import time as _t
        from unittest.mock import patch
        from bot import arca_ws
        from bot import wsfe_idempotencia as wi

        # N4-d: 23:30 ART del 27/11/2026 = 02:30 UTC del 28/11/2026 -> CbteFch debe ser 20261127
        dt_2330_art = _dt.datetime(2026, 11, 28, 2, 30, 0, tzinfo=_dt.timezone.utc)
        self.assertEqual(arca_ws.fecha_hoy_arca(dt_2330_art), "20261127")

        # N4-b y N4-c: INCIERTO tras >10 min y con reemitir_aunque_duplicado=True -> reconcilia (1 sola factura)
        arca = {"ultimo": 200, "comps": {}, "modo": "ok", "emitidas": 0}
        hoy_ar = arca_ws.fecha_hoy_arca()

        def fake_emit(**k):
            arca["ultimo"] += 1
            n = arca["ultimo"]
            arca["emitidas"] += 1
            imp = round(k["importe_neto"] + k["importe_iva"], 2)
            arca["comps"][n] = {"cae": f"CAE{n}", "imp_total": imp, "doc_nro": 0, "cbte_fch": k.get("cbte_fch") or hoy_ar, "cbte_nro": n}
            if arca["modo"] == "drop":
                raise TimeoutError("timed out")
            return {"ok": True, "resultado": "APROBADO", "cae": f"CAE{n}", "cbte_nro": n}

        class _Clock:
            def __init__(self):
                self.offset = 0
            def time(self):
                return _t.time() + self.offset

        clk = _Clock()
        base_v = dict(cuit_emisor="20304050609", pto_vta=1, cbte_tipo=11, receptor_cuit="", importe_iva=0.0)
        with patch.object(wi.arca_ws, "obtener_ultimo_autorizado_wsfe", side_effect=lambda **k: arca["ultimo"]), \
             patch.object(wi.arca_ws, "consultar_comprobante_por_nro_wsfe", side_effect=lambda **k: arca["comps"].get(k["cbte_nro"])), \
             patch.object(wi.arca_ws, "emitir_comprobante_wsfe", side_effect=fake_emit), \
             patch.object(wi, "time", clk):
            # N4-b: 11 minutos después de INCIERTO -> adopta, NO emite duplicado
            arca["modo"] = "drop"
            wi.emitir_wsfe_con_idempotencia(**base_v, importe_neto=2500.0, idempotency_key="x1")
            arca["modo"] = "ok"
            clk.offset = 660
            r_b = wi.emitir_wsfe_con_idempotencia(**base_v, importe_neto=2500.0, idempotency_key="x2")
            self.assertTrue(r_b.get("ok"))
            self.assertTrue(r_b.get("adoptado"))
            self.assertEqual(sum(1 for c in arca["comps"].values() if c["imp_total"] == 2500.0), 1)
            clk.offset = 0

            # N4-c: override reemitir_aunque_duplicado=True con INCIERTO previo -> reconcilia primero, 1 sola factura
            arca["modo"] = "drop"
            wi.emitir_wsfe_con_idempotencia(**base_v, importe_neto=777.0)
            arca["modo"] = "ok"
            r_c = wi.emitir_wsfe_con_idempotencia(**base_v, importe_neto=777.0, reemitir_aunque_duplicado=True)
            self.assertTrue(r_c.get("ok"))
            self.assertTrue(r_c.get("adoptado"))
            self.assertEqual(sum(1 for c in arca["comps"].values() if c["imp_total"] == 777.0), 1)

        # N4-e: respuesta SOAP sin <Resultado> -> INCIERTO, nunca RECHAZADO
        xml_sin_res = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ar="http://ar.gov.afip.dif.FEV1/">'
            '<soap:Body><ar:FECAESolicitarResponse><ar:FECAESolicitarResult/></ar:FECAESolicitarResponse></soap:Body>'
            '</soap:Envelope>'
        )
        with patch.object(arca_ws, "autenticar_wsaa", return_value={"token": "t", "sign": "s"}), \
             patch.object(arca_ws, "consultar_ultimo_comprobante_wsfe", return_value=50), \
             patch.object(arca_ws, "_soap_post", return_value=xml_sin_res):
            r_e = arca_ws.emitir_comprobante_wsfe(
                cuit_emisor="20304050609", pto_vta=1, cbte_tipo=11, receptor_cuit="",
                importe_neto=100.0, importe_iva=0.0, confirmado=True,
                cert_path="/tmp/fake.crt", key_path="/tmp/fake.key", cbte_fch="20261127",
            )
            self.assertFalse(r_e.get("ok"))
            self.assertEqual(r_e.get("resultado"), "INCIERTO")
            self.assertEqual(r_e.get("estado"), "ESTADO_INCIERTO_REQUIERE_REVISION")
            self.assertEqual(r_e.get("fecha"), "20261127")

    def test_sec_n4f_no_emitido_y_resolucion_manual(self):
        """N4-f: INCIERTO que nunca llegó a ARCA se desbloquea tras >=2 min (1 factura) y tool resolver_emision_incierta es solo para Owner validado."""
        import time as _t
        from unittest.mock import patch
        from bot import arca_ws
        from bot import wsfe_idempotencia as wi
        client = TestClient(app)

        cuit_f = "20555555561"
        owner_em = "owner_n4f@impuesto.test"
        editor_em = "editor_n4f@impuesto.test"
        tok_own = _tok_verificado(owner_em)
        tok_ed = _tok_verificado(editor_em)
        _bv_mod.guardar_credenciales_cifradas(cuit=cuit_f, clave_fiscal="ClaveF", owner_email=owner_em)
        _bv_mod.marcar_cuit_validado(cuit_f, email_actor=owner_em, clave_hash=_bv_mod.hash_clave_cuit(cuit_f, "ClaveF"), clave_fiscal="ClaveF")
        _bv_mod.autorizar_usuario_cuit(owner_em, cuit_f, editor_em, rol="editor")

        arca = {"ultimo": 300, "comps": {}, "emitidas": 0}
        hoy_ar = arca_ws.fecha_hoy_arca()

        def fake_emit_ok(**k):
            arca["ultimo"] += 1
            n = arca["ultimo"]
            arca["emitidas"] += 1
            imp = round(k["importe_neto"] + k["importe_iva"], 2)
            arca["comps"][n] = {"cae": f"CAE{n}", "imp_total": imp, "doc_nro": 0, "cbte_fch": k.get("cbte_fch") or hoy_ar, "cbte_nro": n}
            return {"ok": True, "resultado": "APROBADO", "cae": f"CAE{n}", "cbte_nro": n}

        class _Clock:
            def __init__(self):
                self.offset = 0
            def time(self):
                return _t.time() + self.offset

        clk = _Clock()
        venta_f = dict(cuit_emisor=cuit_f, pto_vta=1, cbte_tipo=11, receptor_cuit="", importe_neto=1234.0, importe_iva=0.0)
        with patch.object(wi.arca_ws, "obtener_ultimo_autorizado_wsfe", side_effect=lambda **k: arca["ultimo"]), \
             patch.object(wi.arca_ws, "consultar_comprobante_por_nro_wsfe", side_effect=lambda **k: arca["comps"].get(k["cbte_nro"])), \
             patch.object(wi, "time", clk):
            # 1) Conexión rechazada (nunca llegó a ARCA) -> queda INCIERTO
            with patch.object(wi.arca_ws, "emitir_comprobante_wsfe", side_effect=ConnectionRefusedError("Connection refused")):
                r1 = wi.emitir_wsfe_con_idempotencia(**venta_f)
            self.assertEqual(r1.get("estado"), "ESTADO_INCIERTO_REQUIERE_REVISION")

            # 2) Antes de 2 min -> sigue INCIERTO (fail-closed)
            with patch.object(wi.arca_ws, "emitir_comprobante_wsfe", side_effect=fake_emit_ok):
                r_early = wi.emitir_wsfe_con_idempotencia(**venta_f)
                self.assertEqual(r_early.get("estado"), "ESTADO_INCIERTO_REQUIERE_REVISION")
                self.assertEqual(arca["emitidas"], 0)

                # 3) Después de >= 2 min con FECompUltimoAutorizado == ultimo_nro_antes -> NO_EMITIDO_CONFIRMADO y emite 1 factura
                clk.offset = 180
                r_ok = wi.emitir_wsfe_con_idempotencia(**venta_f)
                self.assertTrue(r_ok.get("ok"))
                self.assertTrue(r_ok.get("reemitido_tras_no_emitido_confirmado"))
                self.assertEqual(arca["emitidas"], 1)

            # 4) Tool resolver_emision_incierta: editor rechazado, owner validado puede marcar_no_emitido
            venta_man = dict(cuit_emisor=cuit_f, pto_vta=1, cbte_tipo=11, receptor_cuit="", importe_neto=8888.0, importe_iva=0.0)
            with patch.object(wi.arca_ws, "emitir_comprobante_wsfe", side_effect=ConnectionRefusedError("refused")):
                r_inc = wi.emitir_wsfe_con_idempotencia(**venta_man)
            huella_short = r_inc["huella_idempotencia"]

            r_ed = client.post("/api/v1/mcp/tool", headers={"X-User-Token": tok_ed}, json={
                "name": "resolver_emision_incierta",
                "arguments": {"cuit": cuit_f, "huella": huella_short, "accion": "marcar_no_emitido", "confirmado": True},
            }).json()
            self.assertFalse(r_ed.get("ok"))
            self.assertTrue(r_ed.get("acceso_denegado"))

            # Sin confirmado=True -> rechazado (N4-j)
            r_noconf = client.post("/api/v1/mcp/tool", headers={"X-User-Token": tok_own}, json={
                "name": "resolver_emision_incierta",
                "arguments": {"cuit": cuit_f, "huella": huella_short, "accion": "marcar_no_emitido"},
            }).json()
            self.assertFalse(r_noconf.get("ok"))
            self.assertTrue(r_noconf.get("requiere_confirmacion"))

            # Sin forzar cuando la reconciliación da INCIERTO (<2 min) -> exige forzar:true (residual P3 N4-j)
            r_reqf = client.post("/api/v1/mcp/tool", headers={"X-User-Token": tok_own}, json={
                "name": "resolver_emision_incierta",
                "arguments": {"cuit": cuit_f, "huella": huella_short, "accion": "marcar_no_emitido", "confirmado": True},
            }).json()
            self.assertFalse(r_reqf.get("ok"))
            self.assertTrue(r_reqf.get("requiere_forzar"))

            # Con forzar=True -> marca NO_EMITIDO_CONFIRMADO
            r_own = client.post("/api/v1/mcp/tool", headers={"X-User-Token": tok_own}, json={
                "name": "resolver_emision_incierta",
                "arguments": {"cuit": cuit_f, "huella": huella_short, "accion": "marcar_no_emitido", "confirmado": True, "forzar": True},
            }).json()
            self.assertTrue(r_own.get("ok"))
            self.assertEqual(r_own.get("estado"), "NO_EMITIDO_CONFIRMADO")

        # Residual P3: sin ARCA_WS_CERT ni ARCA_WS_KEY -> devuelve CERTIFICADO_PENDIENTE con guía CSR
        with patch.dict(os.environ, {"ARCA_WS_CERT": "", "ARCA_WS_KEY": ""}):
            r_nocert = wi.emitir_wsfe_con_idempotencia(
                cuit_emisor=cuit_f, pto_vta=1, cbte_tipo=11, receptor_cuit="", importe_neto=300.0, importe_iva=0.0,
            )
            self.assertFalse(r_nocert.get("ok"))
            self.assertEqual(r_nocert.get("estado"), "CERTIFICADO_PENDIENTE")
            self.assertIn("generar_certificado_csr_arca", r_nocert.get("mensaje", ""))

    def test_sec_n4g_h_i_j_wsfe_errores_y_guardas(self):
        """Cierre N4-g, N4-h, N4-i, N4-j: errores WSFE nunca son 'no emitido', sin ultimo_antes no emite, intento_at fijo y guardas de resolver_emision_incierta."""
        import time as _t
        from unittest.mock import patch
        from bot import arca_ws
        from bot import wsfe_idempotencia as wi

        # N4-g (parser): FECompUltimoAutorizado con <Errors> lanza RuntimeError (nunca 0)
        xml_err_ult = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ar="http://ar.gov.afip.dif.FEV1/">'
            '<soap:Body><ar:FECompUltimoAutorizadoResponse><ar:FECompUltimoAutorizadoResult>'
            '<ar:Errors><ar:Err><ar:Code>500</ar:Code><ar:Msg>Error interno</ar:Msg></ar:Err></ar:Errors>'
            '</ar:FECompUltimoAutorizadoResult></ar:FECompUltimoAutorizadoResponse></soap:Body></soap:Envelope>'
        )
        with patch.object(arca_ws, "_soap_post", return_value=xml_err_ult):
            with self.assertRaises(RuntimeError):
                arca_ws.consultar_ultimo_comprobante_wsfe("20304050607", 1, 11, "t", "s")

        # N4-g (parser): FECompConsultar código 602 -> None; otro error -> RuntimeError
        xml_602 = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ar="http://ar.gov.afip.dif.FEV1/">'
            '<soap:Body><ar:FECompConsultarResponse><ar:FECompConsultarResult>'
            '<ar:Errors><ar:Err><ar:Code>602</ar:Code><ar:Msg>Sin resultados</ar:Msg></ar:Err></ar:Errors>'
            '</ar:FECompConsultarResult></ar:FECompConsultarResponse></soap:Body></soap:Envelope>'
        )
        xml_500 = xml_602.replace("602", "500")
        with patch.object(arca_ws, "_soap_post", return_value=xml_602):
            self.assertIsNone(arca_ws.consultar_comprobante_wsfe("20304050607", 1, 11, 99, "t", "s"))
        with patch.object(arca_ws, "_soap_post", return_value=xml_500):
            with self.assertRaises(RuntimeError):
                arca_ws.consultar_comprobante_wsfe("20304050607", 1, 11, 99, "t", "s")

        # N4-h: sin ultimo_nro_antes -> ARCA_NO_DISPONIBLE sin emitir
        emits_h = {"n": 0}
        with patch.object(wi.arca_ws, "obtener_ultimo_autorizado_wsfe", return_value=None), \
             patch.object(wi.arca_ws, "emitir_comprobante_wsfe", side_effect=lambda **k: emits_h.__setitem__("n", emits_h["n"] + 1)):
            r_h = wi.emitir_wsfe_con_idempotencia(
                cuit_emisor="20304050610", pto_vta=1, cbte_tipo=11, receptor_cuit="", importe_neto=900.0, importe_iva=0.0,
            )
            self.assertFalse(r_h.get("ok"))
            self.assertEqual(r_h.get("estado"), "ARCA_NO_DISPONIBLE")
            self.assertEqual(emits_h["n"], 0)

        # N4-i + N4-g + N4-j
        class _Clk:
            def __init__(self): self.offset = 0
            def time(self): return _t.time() + self.offset
        clk = _Clk()
        hoy_ar = arca_ws.fecha_hoy_arca()
        arca = {"ultimo": 400, "comps": {}, "emits": 0}
        def emit_ok(**k):
            arca["ultimo"] += 1; n = arca["ultimo"]; arca["emits"] += 1
            arca["comps"][n] = {"cae": f"CAE{n}", "imp_total": round(k["importe_neto"], 2), "doc_nro": 0, "cbte_fch": hoy_ar, "cbte_nro": n}
            return {"ok": True, "resultado": "APROBADO", "cae": f"CAE{n}", "cbte_nro": n}

        v_i = dict(cuit_emisor="20304050611", pto_vta=1, cbte_tipo=11, receptor_cuit="", importe_neto=555.0, importe_iva=0.0)
        with patch.object(wi.arca_ws, "obtener_ultimo_autorizado_wsfe", side_effect=lambda **k: arca["ultimo"]), \
             patch.object(wi.arca_ws, "consultar_comprobante_por_nro_wsfe", side_effect=lambda **k: arca["comps"].get(k["cbte_nro"])), \
             patch.object(wi, "time", clk):
            with patch.object(wi.arca_ws, "emitir_comprobante_wsfe", side_effect=ConnectionRefusedError("refused")):
                wi.emitir_wsfe_con_idempotencia(**v_i)
            with patch.object(wi.arca_ws, "emitir_comprobante_wsfe", side_effect=emit_ok):
                # Reintento al minuto 1 -> sigue INCIERTO, pero NO reinicia intento_at (N4-i)
                clk.offset = 60
                r_m1 = wi.emitir_wsfe_con_idempotencia(**v_i)
                self.assertEqual(r_m1.get("estado"), "ESTADO_INCIERTO_REQUIERE_REVISION")
                # Reintento al minuto 2m10s -> ya pasaron >120s desde intento_at -> desbloquea y emite 1
                clk.offset = 130
                r_m2 = wi.emitir_wsfe_con_idempotencia(**v_i)
                self.assertTrue(r_m2.get("ok"))
                self.assertEqual(arca["emits"], 1)

            # N4-j: adoptar_nro con importe distinto rechaza sin forzar=True, acepta con forzar=True
            v_j = dict(cuit_emisor="20304050611", pto_vta=1, cbte_tipo=11, receptor_cuit="", importe_neto=666.0, importe_iva=0.0)
            with patch.object(wi.arca_ws, "emitir_comprobante_wsfe", side_effect=TimeoutError("drop")):
                r_jinc = wi.emitir_wsfe_con_idempotencia(**v_j)
            h_j = r_jinc["huella_idempotencia"]
            # Comprobante #401 tiene importe 555.0 != 666.0
            r_mismatch = wi.resolver_emision_incierta(cuit_emisor="20304050611", huella=h_j, accion="adoptar_nro", cbte_nro=401, confirmado=True)
            self.assertFalse(r_mismatch.get("ok"))
            self.assertTrue(r_mismatch.get("discrepancia_datos"))
            r_forced = wi.resolver_emision_incierta(cuit_emisor="20304050611", huella=h_j, accion="adoptar_nro", cbte_nro=401, confirmado=True, forzar=True)
            self.assertTrue(r_forced.get("ok"))
            self.assertTrue(r_forced.get("forzado"))

    def test_sec_wsapoc_fase33_apocrifo_limpio_fallback_xml_y_errors(self):
        """Fase 3.3 WSAPOC: apócrifo, limpio, caché 24h sin PLAYWRIGHT_SEM, fallback si WS caído, XML malformado y <Errors>."""
        from unittest.mock import patch
        from bot import arca_ws
        client = TestClient(app)
        arca_ws._WSAPOC_CACHE.clear()

        xml_apoc = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/" xmlns:t="http://tempuri.org/">'
            '<soap:Body><t:GetPublicacionAPOCResponse><t:GetPublicacionAPOCResult>'
            '<t:codigo>0</t:codigo><t:descripcion>OK</t:descripcion>'
            '<t:resultados><t:PublicacionAPOC>'
            '<t:Cuit>30999999995</t:Cuit><t:Descripcion>Apócrifo</t:Descripcion>'
            '<t:FechaCondicion>2025-04-10</t:FechaCondicion><t:FechaPublicacion>2025-04-15</t:FechaPublicacion>'
            '</t:PublicacionAPOC></t:resultados>'
            '</t:GetPublicacionAPOCResult></t:GetPublicacionAPOCResponse></soap:Body></soap:Envelope>'
        )
        xml_limpio = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/" xmlns:t="http://tempuri.org/">'
            '<soap:Body><t:GetPublicacionAPOCResponse><t:GetPublicacionAPOCResult>'
            '<t:codigo>0</t:codigo><t:descripcion>Sin registros</t:descripcion><t:resultados/>'
            '</t:GetPublicacionAPOCResult></t:GetPublicacionAPOCResponse></soap:Body></soap:Envelope>'
        )
        xml_errors = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/" xmlns:t="http://tempuri.org/">'
            '<soap:Body><t:GetPublicacionAPOCResponse><t:GetPublicacionAPOCResult>'
            '<t:Errors><t:Error>Token expirado</t:Error></t:Errors>'
            '</t:GetPublicacionAPOCResult></t:GetPublicacionAPOCResponse></soap:Body></soap:Envelope>'
        )

        # 1. Apócrifo + caché 24h (2da llamada no invoca _soap_post)
        soap_calls = {"n": 0}
        def fake_soap_apoc(*a, **k):
            soap_calls["n"] += 1
            return xml_apoc

        with patch.dict(os.environ, {"WSAPOC_ENABLED": "1", "ARCA_WS_CERT": "/tmp/c.crt", "ARCA_WS_KEY": "/tmp/k.key"}), \
             patch.object(arca_ws, "autenticar_wsaa", return_value={"token": "t", "sign": "s"}), \
             patch.object(arca_ws, "_soap_post", side_effect=fake_soap_apoc):
            r1 = client.post("/api/v1/mcp/tool", json={
                "name": "verificar_proveedor_apocrifo_apoc",
                "arguments": {"cuit_proveedor": "30999999995", "ambiente": "homologacion"},
            }).json()
            r2 = client.post("/api/v1/mcp/tool", json={
                "name": "verificar_proveedor_apocrifo_apoc",
                "arguments": {"cuit_proveedor": "30999999995", "ambiente": "homologacion"},
            }).json()
            self.assertTrue(r1.get("ok"))
            self.assertTrue(r1.get("es_apocrifo"))
            self.assertEqual(r1.get("fecha_condicion"), "2025-04-10")
            self.assertEqual(r1.get("fuente"), "WSAPOC")
            self.assertTrue(r2.get("desde_cache"))
            self.assertEqual(soap_calls["n"], 1)

        # 2. Limpio
        with patch.dict(os.environ, {"WSAPOC_ENABLED": "1", "ARCA_WS_CERT": "/tmp/c.crt", "ARCA_WS_KEY": "/tmp/k.key"}), \
             patch.object(arca_ws, "autenticar_wsaa", return_value={"token": "t", "sign": "s"}), \
             patch.object(arca_ws, "_soap_post", return_value=xml_limpio):
            r_clean = client.post("/api/v1/mcp/tool", json={
                "name": "verificar_proveedor_apocrifo_apoc",
                "arguments": {"cuit_proveedor": "30715875086", "ambiente": "homologacion"},
            }).json()
            self.assertTrue(r_clean.get("ok"))
            self.assertFalse(r_clean.get("es_apocrifo"))
            self.assertIsNone(r_clean.get("fecha_condicion"))
            self.assertEqual(r_clean.get("fuente"), "WSAPOC")

        # 3. Web Service caído -> fallback a Playwright
        with patch.dict(os.environ, {"WSAPOC_ENABLED": "1", "ARCA_WS_CERT": "/tmp/c.crt", "ARCA_WS_KEY": "/tmp/k.key"}), \
             patch.object(arca_ws, "autenticar_wsaa", return_value={"token": "t", "sign": "s"}), \
             patch.object(arca_ws, "_soap_post", side_effect=TimeoutError("WSAPOC down")), \
             patch("bot.scraper_extras_arca.verificar_proveedor_apocrifo_apoc", return_value={"ok": True, "cuit": "30888888881", "es_apocrifo": False, "fuente": "PLAYWRIGHT_FALLBACK"}):
            r_fb = client.post("/api/v1/mcp/tool", json={
                "name": "verificar_proveedor_apocrifo_apoc",
                "arguments": {"cuit_proveedor": "30888888881", "ambiente": "homologacion"},
            }).json()
            self.assertTrue(r_fb.get("ok"))
            self.assertEqual(r_fb.get("fuente"), "PLAYWRIGHT_FALLBACK")

        # 4. XML malformado -> error explícito, NUNCA es_apocrifo=False
        with patch.dict(os.environ, {"WSAPOC_ENABLED": "1", "ARCA_WS_CERT": "/tmp/c.crt", "ARCA_WS_KEY": "/tmp/k.key"}), \
             patch.object(arca_ws, "autenticar_wsaa", return_value={"token": "t", "sign": "s"}), \
             patch.object(arca_ws, "_soap_post", return_value="<soap:Broken><unclosed"):
            r_mal = client.post("/api/v1/mcp/tool", json={
                "name": "verificar_proveedor_apocrifo_apoc",
                "arguments": {"cuit_proveedor": "30888888882", "ambiente": "homologacion"},
            }).json()
            self.assertFalse(r_mal.get("ok"))
            self.assertNotIn("es_apocrifo", r_mal)

        # 5. Respuesta con <Errors> -> error explícito, NUNCA es_apocrifo=False
        with patch.dict(os.environ, {"WSAPOC_ENABLED": "1", "ARCA_WS_CERT": "/tmp/c.crt", "ARCA_WS_KEY": "/tmp/k.key"}), \
             patch.object(arca_ws, "autenticar_wsaa", return_value={"token": "t", "sign": "s"}), \
             patch.object(arca_ws, "_soap_post", return_value=xml_errors):
            r_err = client.post("/api/v1/mcp/tool", json={
                "name": "verificar_proveedor_apocrifo_apoc",
                "arguments": {"cuit_proveedor": "30888888883", "ambiente": "homologacion"},
            }).json()
            self.assertFalse(r_err.get("ok"))
            self.assertNotIn("es_apocrifo", r_err)
        arca_ws._WSAPOC_CACHE.clear()

    def test_sec_w1_w2_w3_w4_wsaa_cache_y_wsapoc(self):
        """W1 (WSAA cifrado en VAULT_DIR + alreadyAuthenticated), W2 (rate limit + LRU), W3 (filtro CUIT), W4 (flag WSAPOC_ENABLED)."""
        import datetime as _dt
        from unittest.mock import patch
        from bot import arca_ws
        from bot import main as bot_main
        client = TestClient(app)

        # W1: ticket cifrado guardado en VAULT_DIR/wsaa_cache y leído sin re-llamar a WSAA
        exp_fut = (_dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(hours=8)).isoformat()
        cache_p = arca_ws._wsaa_cache_dir() / "ta_homologacion_wsfe_testcert.crt.enc"
        _bv_mod._write_enc_json(cache_p, {"token": "TOK_VOL", "sign": "SIGN_VOL", "expiration": exp_fut})
        self.assertTrue(str(cache_p).startswith(str(_bv_mod.VAULT_DIR)))
        ta = arca_ws.autenticar_wsaa("/tmp/testcert.crt", "/tmp/testcert.key", service="wsfe", ambiente="homologacion")
        self.assertTrue(ta["desde_cache"])
        self.assertEqual(ta["token"], "TOK_VOL")

        # W1: respuesta WSAA con coe.alreadyAuthenticated -> WsaaAlreadyAuthenticatedError tipada
        xml_already = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">'
            '<soapenv:Body><soapenv:Fault><faultcode>ns1:coe.alreadyAuthenticated</faultcode>'
            '<faultstring>El CEE ya posee un TA valido para el acceso al WSN solicitado</faultstring>'
            '</soapenv:Fault></soapenv:Body></soapenv:Envelope>'
        )
        fake_c = _bv_mod.VAULT_DIR / "dummy_w1.crt"
        fake_k = _bv_mod.VAULT_DIR / "dummy_w1.key"
        fake_c.write_text("x"); fake_k.write_text("y")
        def fake_subp(cmd, **kw):
            out_idx = cmd.index("-out") + 1
            Path(cmd[out_idx]).write_bytes(b"DER")
        with patch.object(arca_ws.subprocess, "run", side_effect=fake_subp), \
             patch.object(arca_ws, "_soap_post", return_value=xml_already):
            with self.assertRaises(arca_ws.WsaaAlreadyAuthenticatedError):
                arca_ws.autenticar_wsaa(str(fake_c), str(fake_k), service="wsfe", ambiente="homologacion")

        # W3: PublicacionAPOC de OTRO CUIT no debe marcar es_apocrifo=True
        xml_otro = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/" xmlns:t="http://tempuri.org/">'
            '<soap:Body><t:GetPublicacionAPOCResponse><t:GetPublicacionAPOCResult>'
            '<t:codigo>0</t:codigo><t:resultados><t:PublicacionAPOC>'
            '<t:Cuit>30111111119</t:Cuit><t:FechaCondicion>2025-01-01</t:FechaCondicion>'
            '</t:PublicacionAPOC></t:resultados></t:GetPublicacionAPOCResult></t:GetPublicacionAPOCResponse></soap:Body></soap:Envelope>'
        )
        res_w3 = arca_ws.parsear_respuesta_wsapoc(xml_otro, "30222222228")
        self.assertTrue(res_w3["ok"])
        self.assertFalse(res_w3["es_apocrifo"])

        # W2: rate limit por IP (30/min) en verificar_proveedor_apocrifo_apoc
        bot_main._APOC_IP_HITS.clear()
        with patch.object(bot_main, "APOC_RATE_LIMIT_PER_MIN", 2), \
             patch("bot.scraper_extras_arca.verificar_proveedor_apocrifo_apoc", return_value={"ok": True, "es_apocrifo": False}):
            client.post("/api/v1/mcp/tool", headers={"CF-Connecting-IP": "198.51.100.7"}, json={"name": "verificar_proveedor_apocrifo_apoc", "arguments": {"cuit_proveedor": "30715875086"}})
            client.post("/api/v1/mcp/tool", headers={"CF-Connecting-IP": "198.51.100.7"}, json={"name": "verificar_proveedor_apocrifo_apoc", "arguments": {"cuit_proveedor": "30715875086"}})
            r_lim = client.post("/api/v1/mcp/tool", headers={"CF-Connecting-IP": "198.51.100.7"}, json={"name": "verificar_proveedor_apocrifo_apoc", "arguments": {"cuit_proveedor": "30715875086"}}).json()
            self.assertFalse(r_lim.get("ok"))
            self.assertTrue(r_lim.get("rate_limited"))
        bot_main._APOC_IP_HITS.clear()

        # W4: sin WSAPOC_ENABLED=1 usa fallback a Playwright incluso con ARCA_WS_CERT seteado
        with patch.dict(os.environ, {"WSAPOC_ENABLED": "0", "ARCA_WS_CERT": "/tmp/c.crt", "ARCA_WS_KEY": "/tmp/k.key"}), \
             patch("bot.scraper_extras_arca.verificar_proveedor_apocrifo_apoc", return_value={"ok": True, "fuente": "PW_DEFAULT"}):
            r_w4 = client.post("/api/v1/mcp/tool", headers={"CF-Connecting-IP": "198.51.100.8"}, json={"name": "verificar_proveedor_apocrifo_apoc", "arguments": {"cuit_proveedor": "30715875099"}}).json()
            self.assertTrue(r_w4.get("ok"))
            self.assertEqual(r_w4.get("fuente"), "PW_DEFAULT")
        bot_main._APOC_IP_HITS.clear()

        # Residual P3 W1: migración de tickets WSAA legados (.json -> .enc)
        import json as _json
        leg_dir = _bv_mod.VAULT_DIR / "legacy_wsaa_test"
        leg_dir.mkdir(parents=True, exist_ok=True)
        leg_file = leg_dir / "ta_homologacion_wsfe_migr.crt.json"
        leg_file.write_text(_json.dumps({"token": "T_MIG", "sign": "S_MIG", "expiration": exp_fut}), encoding="utf-8")
        cnt = arca_ws.migrar_tickets_wsaa_legados(legacy_dir=leg_dir)
        self.assertEqual(cnt, 1)
        self.assertFalse(leg_file.exists())
        ta_mig = arca_ws.autenticar_wsaa("/tmp/migr.crt", "/tmp/migr.key", service="wsfe", ambiente="homologacion")
        self.assertTrue(ta_mig["desde_cache"])
        self.assertEqual(ta_mig["token"], "T_MIG")

    def test_sec_n3b_ipv6_slash64_y_ataque4b_usuario_conocido(self):
        """N3-b: 10 IPs de la misma /64 cuentan como 1 sola; tras ataque 4b (tope global), un usuario ya verificado sigue entrando."""
        from unittest.mock import patch
        from bot import limite_login as ll

        # 1. Agrupamiento IPv6 por /64
        self.assertEqual(
            ll.normalizar_clave_ip("2001:db8:abcd:0012::1"),
            ll.normalizar_clave_ip("2001:db8:abcd:0012:ffff:ffff:ffff:fffe"),
        )
        self.assertEqual(ll.normalizar_clave_ip("203.0.113.42"), "203.0.113.42")

        lim_v6 = ll.LimiteLogin(por_ip_usuario=50, por_usuario=50, por_ip=5, global_por_min=500)
        bloqueado_v6 = False
        for i in range(10):
            ip6 = f"2001:db8:cafe:1234::{i + 1:x}"
            ok, _ = lim_v6.chequear(ip6, f"u{i}@test.com")
            if not ok:
                bloqueado_v6 = True
                break
            lim_v6.registrar_fallo(ip6, f"u{i}@test.com")
        self.assertTrue(bloqueado_v6, "10 IPs distintas del mismo /64 deberían chocar contra el límite por_ip=5")

        # 2. Ataque 4b (muchas IPs saturan tope global): desconocidos bloqueados, usuario ya verificado entra
        email_conocido = "conocido_n3b@empresa.com.ar"
        _tok_verificado(email_conocido)
        lim_4b = ll.LimiteLogin(
            por_ip_usuario=3, por_usuario=5, por_ip=5,
            global_por_min=50, global_por_hora=100, global_por_dia=500,
            solo_bloquear_desconocidos_en_global=True,
            nombre="TEST_N3B",
        )
        with patch.object(ll, "LIMITE_OTP_ENVIO", lim_4b), \
             patch.object(_bv_mod, "_enviar_email_otp", return_value=(True, "resend")):
            for i in range(70):
                _bv_mod.solicitar_codigo_otp_email(f"bot{i}@evil.test", client_ip=f"10.1.{i // 250}.{i % 250 + 1}")
            # Email nunca verificado -> bloqueado por tope global
            r_new = _bv_mod.solicitar_codigo_otp_email("nuevo_desconocido@test.com", client_ip="198.51.100.50")
            self.assertFalse(r_new.get("ok"))
            self.assertTrue(r_new.get("rate_limited"))
            # Usuario ya verificado -> ENTRA igual (cierre N3-b)
            r_known = _bv_mod.solicitar_codigo_otp_email(email_conocido, client_ip="198.51.100.51")
            self.assertTrue(r_known.get("ok"), f"Usuario conocido bloqueado por ataque 4b: {r_known}")

    def test_sec_o1_produccion_fail_closed_por_defecto(self):
        """O1: sin variables de entorno, producción es fail-closed (_is_cloud_prod=True, _check_secret lanza 503, middleware 503 salvo /health)."""
        from unittest.mock import patch
        from fastapi import HTTPException
        from bot import main as bot_main
        client = TestClient(app)

        clean_env = {
            "IMPUESTO_ENV": "",
            "OCI_REGION": "",
            "ORACLE_CLOUD": "",
            "FLY_APP_NAME": "",
            "REQUIRE_BOT_SECRET": "",
            "REQUIRE_VAULT_KEY": "",
            "BOT_API_SECRET": "",
            "IMPUESTO_VAULT_KEY": "",
        }
        with patch.dict(os.environ, clean_env):
            self.assertTrue(_bv_mod._is_cloud_prod())
            self.assertTrue(bot_main._is_prod_env())
            with self.assertRaises(HTTPException) as ctx:
                bot_main._check_secret(None)
            self.assertEqual(ctx.exception.status_code, 503)
            self.assertEqual(client.get("/health").status_code, 200)
            self.assertEqual(client.post("/api/v1/mcp/tool", json={"name": "listar_empresas", "arguments": {}}).status_code, 503)

        # Con IMPUESTO_ENV=test relaja los requisitos como en la suite
        with patch.dict(os.environ, {**clean_env, "IMPUESTO_ENV": "test"}):
            self.assertFalse(_bv_mod._is_cloud_prod())
            self.assertFalse(bot_main._is_prod_env())
            bot_main._check_secret(None)

    def test_sec_o2_migracion_clave_boveda_y_guarda_runtime(self):
        """O2: bóveda cifrada con .vault_key -> migración dry-run y --aplicar -> se lee con IMPUESTO_VAULT_KEY; clave equivocada no pisa nada."""
        import tempfile as _tf
        import datetime as _dt
        from unittest.mock import patch
        from bot import main as bot_main
        from bot import arca_ws
        from bot.migrar_clave_boveda import migrar_boveda

        with _tf.TemporaryDirectory(prefix="impuesto_o2_") as td:
            vdir = Path(td) / "boveda"
            vdir.mkdir(parents=True, exist_ok=True)
            vfile = vdir / "credenciales.enc"
            bfile = vdir / "cuit_budget.enc"
            kfile = vdir / ".vault_key"
            wsaa_dir = vdir / "wsaa_cache"
            wsaa_dir.mkdir(parents=True, exist_ok=True)
            ta_file = wsaa_dir / "ta_homologacion_wsfe_o2.crt.enc"

            with patch.object(_bv_mod, "VAULT_DIR", vdir), \
                 patch.object(_bv_mod, "VAULT_FILE", vfile), \
                 patch.object(_bv_mod, "KEY_FILE", kfile), \
                 patch.dict(os.environ, {"IMPUESTO_ENV": "test", "IMPUESTO_VAULT_KEY": ""}):
                # 1. Crear bóveda + presupuesto + ticket WSAA cifrados con .vault_key
                _bv_mod._write_enc_json(vfile, {"20999999991": {"clave_fiscal": "SecretaO2"}})
                _bv_mod.guardar_presupuesto_cuit({"20999999991": [1700000000.0]})
                exp_fut = (_dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(hours=6)).isoformat()
                _bv_mod._write_enc_json(ta_file, {"token": "TO2", "sign": "SO2", "expiration": exp_fut})
                self.assertTrue(kfile.exists())

                orig_v_bytes = vfile.read_bytes()
                orig_b_bytes = bfile.read_bytes()
                orig_t_bytes = ta_file.read_bytes()

                # 2. Clave nueva equivocada en prod: VaultKeyMismatchError y NO reescribe ningún archivo
                with patch.dict(os.environ, {"IMPUESTO_ENV": "production", "IMPUESTO_VAULT_KEY": "NuevaClaveMaestraO2-2026"}):
                    with self.assertRaises(_bv_mod.VaultKeyMismatchError):
                        _bv_mod._read_enc_json(vfile, {})
                    bot_main._save_budget_locked("20999999991", [1700000999.0])
                    with self.assertRaises(_bv_mod.VaultKeyMismatchError):
                        arca_ws.autenticar_wsaa("/tmp/o2.crt", "/tmp/o2.key", service="wsfe", ambiente="homologacion")
                    self.assertEqual(vfile.read_bytes(), orig_v_bytes)
                    self.assertEqual(bfile.read_bytes(), orig_b_bytes)
                    self.assertEqual(ta_file.read_bytes(), orig_t_bytes)

                # 3. Dry-run no modifica nada ni renombra .vault_key
                r_dry = migrar_boveda(vdir, "NuevaClaveMaestraO2-2026", aplicar=False)
                self.assertTrue(r_dry["ok"] and r_dry["dry_run"])
                self.assertEqual(r_dry["archivos_encontrados"], 3)
                self.assertTrue(kfile.exists())
                self.assertEqual(vfile.read_bytes(), orig_v_bytes)

                # 3b. O2-b: fallo a mitad en el 3er archivo (No space left) no corrompe originales y el reintento completa todo
                import bot.migrar_clave_boveda as _mig_mod
                orig_fn = _mig_mod._fernet_from_env_key
                class _BoomFernet:
                    def __init__(self, f): self.f = f; self.n = 0
                    def encrypt(self, b):
                        self.n += 1
                        if self.n == 3:
                            raise OSError("No space left on device")
                        return self.f.encrypt(b)
                    def decrypt(self, b):
                        return self.f.decrypt(b)
                with patch.object(_mig_mod, "_fernet_from_env_key", lambda k: _BoomFernet(orig_fn(k))):
                    with self.assertRaises(OSError):
                        migrar_boveda(vdir, "NuevaClaveMaestraO2-2026", aplicar=True)
                # Originales intactos tras el fallo en staging
                self.assertEqual(vfile.read_bytes(), orig_v_bytes)
                self.assertTrue(kfile.exists())

                # 4. --aplicar tras el fallo: migra los 3 *.enc, backup DENTRO de vdir/_backups_o2 (O2-c) y renombra .vault_key
                r_ap = migrar_boveda(vdir, "NuevaClaveMaestraO2-2026", aplicar=True)
                self.assertTrue(r_ap["ok"] and not r_ap["dry_run"])
                self.assertTrue(Path(r_ap["backup_dir"]).exists())
                self.assertTrue(str(Path(r_ap["backup_dir"]).resolve()).startswith(str((vdir / "_backups_o2").resolve())))
                self.assertFalse(kfile.exists())
                self.assertTrue((vdir / ".vault_key.migrada").exists())

                # 5. Todo se lee perfecto con IMPUESTO_VAULT_KEY
                with patch.dict(os.environ, {"IMPUESTO_ENV": "production", "IMPUESTO_VAULT_KEY": "NuevaClaveMaestraO2-2026"}):
                    self.assertEqual(_bv_mod._read_enc_json(vfile, {})["20999999991"]["clave_fiscal"], "SecretaO2")
                    self.assertEqual(_bv_mod.cargar_presupuesto_cuit()["20999999991"], [1700000000.0])
                    ta_ok = arca_ws.autenticar_wsaa("/tmp/o2.crt", "/tmp/o2.key", service="wsfe", ambiente="homologacion")
                    self.assertTrue(ta_ok["desde_cache"])
                    self.assertEqual(ta_ok["token"], "TO2")

    def test_poc_http_fase32_fixtures_redactados(self):
        """Fase 3.2 PoC HTTP: login OK, clave incorrecta, captcha, timeout pre/post contraseña, servicio sin autorización y flag."""
        from unittest.mock import patch
        import httpx
        from bot.arca_errors import ArcaNoDisponible, ClaveIncorrecta, LoginNoConfirmado
        from bot.poc_http import ArcaHttpClient, ServicioNoAutorizadoError, redactar_headers_y_payload

        # 0. Redacción de secretos en headers/payloads
        red = redactar_headers_y_payload({"F1:password": "Secreta", "Cookie": "JSESSIONID=abc", "token": "T", "sign": "S", "ok": True})
        self.assertEqual(red["F1:password"], "[REDACTED]")
        self.assertEqual(red["Cookie"], "[REDACTED]")
        self.assertEqual(red["token"], "[REDACTED]")
        self.assertEqual(red["sign"], "[REDACTED]")
        self.assertTrue(red["ok"])

        # 1. Flag apagado por defecto -> bloquea ejecución
        with patch.dict(os.environ, {"ARCA_HTTP_LOGIN": "0"}):
            with self.assertRaises(RuntimeError):
                ArcaHttpClient(require_flag=True).autenticar_y_abrir_servicio(cuit="20304050607", clave="x")

        def _make_transport(mode: str) -> httpx.MockTransport:
            def handler(request: httpx.Request) -> httpx.Response:
                url = str(request.url)
                if "login.xhtml" in url and request.method == "GET":
                    if mode == "timeout_pre":
                        raise httpx.ReadTimeout("timeout en GET login.xhtml")
                    return httpx.Response(200, text='<form><input type="hidden" name="javax.faces.ViewState" value="VS1_REDACTED"/></form>')
                if "login.xhtml" in url and request.method == "POST":
                    body = request.content.decode("utf-8", errors="ignore")
                    if "F1%3Ausername" in body or "F1:username" in body:
                        if mode == "no_pw_field":
                            return httpx.Response(200, text='<form><input type="hidden" name="javax.faces.ViewState" value="VS2_REDACTED"/></form>')
                        return httpx.Response(200, text='<form><input type="password" name="F1:password"/><input type="hidden" name="javax.faces.ViewState" value="VS2_REDACTED"/></form>')
                    if mode == "timeout_post":
                        raise httpx.ReadTimeout("timeout tras enviar F1:password")
                    if mode == "bad_pass":
                        return httpx.Response(200, text='<span id="F1:msg">Clave o usuario incorrecto</span>')
                    if mode == "captcha":
                        return httpx.Response(200, text='<div class="g-recaptcha">Verificación de seguridad</div>')
                    return httpx.Response(200, text='<form action="https://portalcf.cloud.afip.gob.ar/portal/login"><input name="jwt" value="JWT_REDACTED"/></form>')
                if "portal/login" in url:
                    return httpx.Response(200, text="<html>Portal CF OK</html>")
                if "/autorizacion" in url:
                    if mode == "auth_401":
                        return httpx.Response(401, json={"error": "No autenticado"})
                    if mode == "no_auth":
                        return httpx.Response(403, json={"error": "Servicio no adherido"})
                    return httpx.Response(200, json={"token": "TOK_REDACTED", "sign": "SIGN_REDACTED"})
                if "ccma/index.aspx" in url:
                    return httpx.Response(200, text="<html>Total Saldo Deudor: $ 1.250,50</html>")
                return httpx.Response(404, text="Not found")
            return httpx.MockTransport(handler)

        with patch.dict(os.environ, {"ARCA_HTTP_LOGIN": "1"}):
            # 2. Login OK -> abre CCMA y parsea importe estricto (M2)
            res_ok = ArcaHttpClient(transport=_make_transport("ok")).autenticar_y_abrir_servicio(
                cuit="20304050607", clave="ClaveFixture", servicio="ccma",
            )
            self.assertTrue(res_ok["ok"])
            self.assertTrue(res_ok["password_enviada"])
            self.assertEqual(res_ok["fuente"], "ARCA_HTTP_POC")
            self.assertAlmostEqual(res_ok["importes_extraidos"]["total_saldo_deudor"], 1250.50, places=2)

            # 3. Clave incorrecta -> ClaveIncorrecta
            with self.assertRaises(ClaveIncorrecta) as c_bad:
                ArcaHttpClient(transport=_make_transport("bad_pass")).autenticar_y_abrir_servicio(cuit="20304050607", clave="Mala")
            self.assertFalse(c_bad.exception.captcha)

            # 4. Captcha -> ClaveIncorrecta(captcha=True)
            with self.assertRaises(ClaveIncorrecta) as c_cap:
                ArcaHttpClient(transport=_make_transport("captcha")).autenticar_y_abrir_servicio(cuit="20304050607", clave="Real")
            self.assertTrue(c_cap.exception.captcha)

            # 5. Timeout ANTES de enviar la contraseña o falta F1:password en paso 2 -> ArcaNoDisponible
            with self.assertRaises(ArcaNoDisponible):
                ArcaHttpClient(transport=_make_transport("timeout_pre")).autenticar_y_abrir_servicio(cuit="20304050607", clave="Real")
            with self.assertRaises(ArcaNoDisponible):
                ArcaHttpClient(transport=_make_transport("no_pw_field")).autenticar_y_abrir_servicio(cuit="20304050607", clave="Real")

            # 6. Timeout DESPUÉS de enviar la contraseña o HTTP 401 en paso 5 -> LoginNoConfirmado
            with self.assertRaises(LoginNoConfirmado):
                ArcaHttpClient(transport=_make_transport("timeout_post")).autenticar_y_abrir_servicio(cuit="20304050607", clave="Real")
            with self.assertRaises(LoginNoConfirmado):
                ArcaHttpClient(transport=_make_transport("auth_401")).autenticar_y_abrir_servicio(cuit="20304050607", clave="Real")

            # 7. Servicio sin autorización (403) -> ServicioNoAutorizadoError
            with self.assertRaises(ServicioNoAutorizadoError):
                ArcaHttpClient(transport=_make_transport("no_auth")).autenticar_y_abrir_servicio(cuit="20304050607", clave="Real")

            # 8. M1 + M2: medir_poc_http corta en 1er LoginNoConfirmado, corta en captcha y aborta en 2 captchas, y valida paridad 100%
            from scripts.medir_poc_http import ejecutar_medicion
            r_lnc = ejecutar_medicion(
                [{"cuit": "20304050607", "clave": "Real"}],
                corridas=20, pausa_seg=0.0, transport=_make_transport("timeout_post"),
            )
            self.assertEqual(r_lnc["corridas_totales"], 1)

            r_cap2 = ejecutar_medicion(
                [{"cuit": "20304050607", "clave": "Real"}, {"cuit": "20304050608", "clave": "Real"}, {"cuit": "20304050609", "clave": "Real"}],
                corridas=20, pausa_seg=0.0, transport=_make_transport("captcha"),
            )
            self.assertTrue(r_cap2["abortado_por_captchas"])
            self.assertEqual(r_cap2["corridas_totales"], 2)

            r_par_ok = ejecutar_medicion(
                [{"cuit": "20304050607", "clave": "Real"}],
                corridas=2, pausa_seg=0.0, transport=_make_transport("ok"),
                playwright_fn=lambda c, cl, s: {"total_saldo_deudor": 1250.50},
            )
            self.assertEqual(r_par_ok["paridad_pct"], 100.0)
            r_par_bad = ejecutar_medicion(
                [{"cuit": "20304050607", "clave": "Real"}],
                corridas=2, pausa_seg=0.0, transport=_make_transport("ok"),
                playwright_fn=lambda c, cl, s: {"total_saldo_deudor": 9999.00},
            )
            self.assertEqual(r_par_bad["paridad_pct"], 0.0)
            self.assertFalse(r_par_bad["cumple_go"])

    def test_sec_fase35_wsaa_por_cuit_certificados_y_aislamiento_cache(self):
        """Fase 3.5 WSAA por CUIT: CSR en bóveda sin filtrar clave privada, validación .crt (clave/CUIT/vigencia/owner), firma en memoria y caché aislado A/B."""
        import datetime as _dt
        from unittest.mock import patch
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from bot import arca_ws
        client = TestClient(app)

        def _make_cert_pem(priv_key, cuit_str: str, days_valid: int = 15, expired: bool = False) -> str:
            now = _dt.datetime.now(_dt.timezone.utc)
            nb = now - _dt.timedelta(days=30 if expired else 1)
            na = now - _dt.timedelta(days=1) if expired else now + _dt.timedelta(days=days_valid)
            subj = x509.Name([
                x509.NameAttribute(NameOID.COUNTRY_NAME, "AR"),
                x509.NameAttribute(NameOID.COMMON_NAME, "test_wsaa"),
                x509.NameAttribute(NameOID.SERIAL_NUMBER, f"CUIT {cuit_str}"),
            ])
            cert = (
                x509.CertificateBuilder()
                .subject_name(subj)
                .issuer_name(subj)
                .public_key(priv_key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(nb)
                .not_valid_after(na)
                .sign(priv_key, hashes.SHA256())
            )
            return cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")

        cuit_a, cuit_b = "20666666661", "20666666662"
        own_a, ed_a, own_b = "owner_a35@impuesto.test", "editor_a35@impuesto.test", "owner_b35@impuesto.test"
        tok_a = _tok_verificado(own_a)
        tok_ed = _tok_verificado(ed_a)
        tok_b = _tok_verificado(own_b)

        for c_id, em in ((cuit_a, own_a), (cuit_b, own_b)):
            _bv_mod.guardar_credenciales_cifradas(cuit=c_id, clave_fiscal="Clave35", owner_email=em)
            _bv_mod.marcar_cuit_validado(c_id, email_actor=em, clave_hash=_bv_mod.hash_clave_cuit(c_id, "Clave35"), clave_fiscal="Clave35")
        _bv_mod.autorizar_usuario_cuit(own_a, cuit_a, ed_a, rol="editor")

        # 1. Generar CSR para CUIT A: la clave privada NUNCA aparece en la respuesta
        r_csr = client.post("/api/v1/mcp/tool", headers={"X-User-Token": tok_a}, json={
            "name": "generar_certificado_csr_arca",
            "arguments": {"cuit": cuit_a, "razon_social": "Empresa A SA", "alias": "emp_a"},
        }).json()
        self.assertTrue(r_csr.get("ok"))
        self.assertIn("BEGIN CERTIFICATE REQUEST", r_csr.get("csr_pem", ""))
        self.assertNotIn("PRIVATE KEY", json.dumps(r_csr))
        self.assertNotIn("key_path", r_csr)

        priv_a = serialization.load_pem_private_key(_bv_mod.obtener_credenciales_descifradas(cuit_a)["key_pem"].encode(), password=None)
        other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

        # 2. Certificado con otra clave -> rechazado
        r_wrong_k = client.post("/api/v1/mcp/tool", headers={"X-User-Token": tok_a}, json={
            "name": "cargar_certificado_wsaa_cuit",
            "arguments": {"cuit": cuit_a, "cert_pem": _make_cert_pem(other_key, cuit_a)},
        }).json()
        self.assertFalse(r_wrong_k.get("ok"))

        # 3. Certificado con CUIT distinto en SERIALNUMBER -> rechazado
        r_wrong_c = client.post("/api/v1/mcp/tool", headers={"X-User-Token": tok_a}, json={
            "name": "cargar_certificado_wsaa_cuit",
            "arguments": {"cuit": cuit_a, "cert_pem": _make_cert_pem(priv_a, cuit_b)},
        }).json()
        self.assertFalse(r_wrong_c.get("ok"))

        # 4. Certificado vencido -> rechazado
        r_exp = client.post("/api/v1/mcp/tool", headers={"X-User-Token": tok_a}, json={
            "name": "cargar_certificado_wsaa_cuit",
            "arguments": {"cuit": cuit_a, "cert_pem": _make_cert_pem(priv_a, cuit_a, expired=True)},
        }).json()
        self.assertFalse(r_exp.get("ok"))

        # 5. Editor intentando subir certificado -> acceso denegado
        cert_a_pem = _make_cert_pem(priv_a, cuit_a, days_valid=15)
        r_ed = client.post("/api/v1/mcp/tool", headers={"X-User-Token": tok_ed}, json={
            "name": "cargar_certificado_wsaa_cuit",
            "arguments": {"cuit": cuit_a, "cert_pem": cert_a_pem},
        }).json()
        self.assertFalse(r_ed.get("ok"))
        self.assertTrue(r_ed.get("acceso_denegado"))

        # 6. Owner validado sube certificado válido (vence en 15 días -> alerta_vencimiento)
        r_ok_a = client.post("/api/v1/mcp/tool", headers={"X-User-Token": tok_a}, json={
            "name": "cargar_certificado_wsaa_cuit",
            "arguments": {"cuit": cuit_a, "cert_pem": cert_a_pem},
        }).json()
        self.assertTrue(r_ok_a.get("ok"))
        self.assertIn("alerta_vencimiento", r_ok_a)
        self.assertNotIn("PRIVATE KEY", json.dumps(r_ok_a))

        # 7. Generar y cargar certificado propio también para CUIT B -> verificar aislamiento del caché A/B y firma PKCS#7 en memoria
        client.post("/api/v1/mcp/tool", headers={"X-User-Token": tok_b}, json={
            "name": "generar_certificado_csr_arca", "arguments": {"cuit": cuit_b, "razon_social": "Empresa B SRL"},
        })
        priv_b = serialization.load_pem_private_key(_bv_mod.obtener_credenciales_descifradas(cuit_b)["key_pem"].encode(), password=None)
        cert_b_pem = _make_cert_pem(priv_b, cuit_b, days_valid=90)
        self.assertTrue(client.post("/api/v1/mcp/tool", headers={"X-User-Token": tok_b}, json={
            "name": "cargar_certificado_wsaa_cuit", "arguments": {"cuit": cuit_b, "cert_pem": cert_b_pem},
        }).json().get("ok"))

        exp_iso = (_dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(hours=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
        calls = {"n": 0}
        def fake_wsaa_soap(url, body, **kw):
            calls["n"] += 1
            tok_v = f"TOK_{calls['n']}"
            ta_xml = f"<loginTicketResponse><credentials><token>{tok_v}</token><sign>SIG_{calls['n']}</sign></credentials><header><expirationTime>{exp_iso}</expirationTime></header></loginTicketResponse>"
            import html as _html
            return f"<soap:Envelope xmlns:soap='http://schemas.xmlsoap.org/soap/envelope/'><soap:Body><loginCmsResponse><loginCmsReturn>{_html.escape(ta_xml)}</loginCmsReturn></loginCmsResponse></soap:Body></soap:Envelope>"

        with patch.object(arca_ws, "_soap_post", side_effect=fake_wsaa_soap):
            ta_a1 = arca_ws.autenticar_wsaa_para_cuit(cuit_a, service="wsfe", ambiente="homologacion")
            ta_b1 = arca_ws.autenticar_wsaa_para_cuit(cuit_b, service="wsfe", ambiente="homologacion")
            ta_a2 = arca_ws.autenticar_wsaa_para_cuit(cuit_a, service="wsfe", ambiente="homologacion")
            self.assertEqual(ta_a1["fuente_certificado"], "propio")
            self.assertEqual(ta_b1["fuente_certificado"], "propio")
            self.assertNotEqual(ta_a1["token"], ta_b1["token"])
            self.assertEqual(ta_a2["token"], ta_a1["token"])
            self.assertTrue(ta_a2["desde_cache"])
            self.assertEqual(calls["n"], 2)

        # 8. C1: regenerar CSR con cert vigente NO rompe el par activo; al subir el cert nuevo, promueve la clave pendiente
        r_csr2 = client.post("/api/v1/mcp/tool", headers={"X-User-Token": tok_a}, json={
            "name": "generar_certificado_csr_arca", "arguments": {"cuit": cuit_a, "razon_social": "Empresa A SA", "alias": "emp_a_v2"},
        }).json()
        self.assertTrue(r_csr2.get("ok"))
        cred_mid = arca_ws.resolver_credenciales_wsaa_para_cuit(cuit_a)
        self.assertEqual(cred_mid["fuente_certificado"], "propio")
        c_mid = x509.load_pem_x509_certificate(cred_mid["cert_pem"].encode())
        k_mid = serialization.load_pem_private_key(cred_mid["key_pem"].encode(), password=None)
        self.assertEqual(c_mid.public_key().public_numbers(), k_mid.public_key().public_numbers())
        # Subir cert firmado con la nueva key_pem_pendiente -> promueve al par nuevo
        priv_a2 = serialization.load_pem_private_key(_bv_mod.obtener_credenciales_descifradas(cuit_a)["key_pem_pendiente"].encode(), password=None)
        cert_a2_pem = _make_cert_pem(priv_a2, cuit_a, days_valid=180)
        r_prom = client.post("/api/v1/mcp/tool", headers={"X-User-Token": tok_a}, json={
            "name": "cargar_certificado_wsaa_cuit", "arguments": {"cuit": cuit_a, "cert_pem": cert_a2_pem},
        }).json()
        self.assertTrue(r_prom.get("ok"))
        cred_new = arca_ws.resolver_credenciales_wsaa_para_cuit(cuit_a)
        k_new = serialization.load_pem_private_key(cred_new["key_pem"].encode(), password=None)
        self.assertEqual(k_new.public_key().public_numbers(), priv_a2.public_key().public_numbers())

        # 9. C2: /api/v1/vincular rechaza key_pem subida por el usuario
        r_c2 = client.post("/api/v1/vincular", headers={"X-User-Token": tok_a}, json={
            "email": own_a, "cuit": cuit_a, "key_pem": "-----BEGIN PRIVATE KEY-----\nFAKE\n-----END PRIVATE KEY-----",
        }).json()
        self.assertFalse(r_c2.get("ok"))

    def test_sec_fase34_eventanilla_veconsumerws(self):
        """Fase 3.4 e-Ventanilla: endpoint homo, 2 páginas, vacío, Fault, XML malformado, totalItems>0 vacío, auth error, abrir sin confirmado y MD5 desparejo."""
        import base64 as _b64
        import gzip as _gzip
        import hashlib as _hl
        import urllib.error as _uerr
        from unittest.mock import patch
        from bot import arca_ws
        from bot import eventanilla_ws as ve
        from bot import main as bot_main
        client = TestClient(app)

        # 1. Endpoint homologación corregido
        self.assertEqual(
            arca_ws.ENDPOINTS["homologacion"]["veconsumerws"],
            "https://stable-middleware-tecno-ext.afip.gob.ar/ve-ws/services/veconsumer",
        )
        self.assertEqual(
            arca_ws.ENDPOINTS["produccion"]["veconsumerws"],
            "https://infraestructura.afip.gob.ar/ve-ws/services/veconsumer",
        )

        cuit_ve = "20777777781"
        em_ve = "owner_ve34@impuesto.test"
        tok_ve = _tok_verificado(em_ve)
        _bv_mod.guardar_credenciales_cifradas(cuit=cuit_ve, clave_fiscal="ClaveVE", owner_email=em_ve)
        _bv_mod.marcar_cuit_validado(cuit_ve, email_actor=em_ve, clave_hash=_bv_mod.hash_clave_cuit(cuit_ve, "ClaveVE"), clave_fiscal="ClaveVE")

        xml_estados = (
            '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
            '<soap:Body><consultarEstadosResponse><return>'
            '<estado><id>1</id><descripcion>No Leída</descripcion></estado>'
            '<estado><id>2</id><descripcion>Leída</descripcion></estado>'
            '</return></consultarEstadosResponse></soap:Body></soap:Envelope>'
        )
        xml_pag1 = (
            '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
            '<soap:Body><consultarComunicacionesResponse><RespuestaPaginada>'
            '<pagina>1</pagina><totalPaginas>2</totalPaginas><totalItems>2</totalItems>'
            '<items><item><idComunicacion>101</idComunicacion><cuitDestinatario>20777777781</cuitDestinatario>'
            '<asunto>Intimación IVA</asunto><fechaPublicacion>2026-11-01</fechaPublicacion>'
            '<estado>1</estado><sistemaPublicadorDesc>ARCA Fiscalización</sistemaPublicadorDesc><tieneAdjunto>true</tieneAdjunto></item></items>'
            '</RespuestaPaginada></consultarComunicacionesResponse></soap:Body></soap:Envelope>'
        )
        xml_pag2 = (
            '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
            '<soap:Body><consultarComunicacionesResponse><RespuestaPaginada>'
            '<pagina>2</pagina><totalPaginas>2</totalPaginas><totalItems>2</totalItems>'
            '<items><item><idComunicacion>102</idComunicacion><cuitDestinatario>20777777781</cuitDestinatario>'
            '<asunto>Aviso Vencimiento</asunto><fechaPublicacion>2026-11-10</fechaPublicacion>'
            '<estado>2</estado><sistemaPublicadorDesc>ARCA Recaudación</sistemaPublicadorDesc><tieneAdjunto>false</tieneAdjunto></item></items>'
            '</RespuestaPaginada></consultarComunicacionesResponse></soap:Body></soap:Envelope>'
        )
        xml_vacio = (
            '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
            '<soap:Body><consultarComunicacionesResponse><RespuestaPaginada>'
            '<pagina>1</pagina><totalPaginas>1</totalPaginas><totalItems>0</totalItems><items/>'
            '</RespuestaPaginada></consultarComunicacionesResponse></soap:Body></soap:Envelope>'
        )
        xml_total_sin_items = (
            '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
            '<soap:Body><consultarComunicacionesResponse><RespuestaPaginada>'
            '<pagina>1</pagina><totalPaginas>1</totalPaginas><totalItems>3</totalItems><items/>'
            '</RespuestaPaginada></consultarComunicacionesResponse></soap:Body></soap:Envelope>'
        )
        xml_fault = (
            '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
            '<soap:Body><soap:Fault><faultcode>soap:Server</faultcode><faultstring>Token inválido</faultstring></soap:Fault></soap:Body></soap:Envelope>'
        )

        # 2. Listado en 2 páginas + mapeo de estados
        ve._VE_ESTADOS_CACHE.clear()
        bot_main.TOOL_CACHE.clear()
        def fake_soap_2p(url, body, soap_action="", **kw):
            if "consultarEstados" in soap_action or "consultarEstados" in body:
                return xml_estados
            if "<pagina>2</pagina>" in body:
                return xml_pag2
            return xml_pag1

        with patch.object(arca_ws, "autenticar_wsaa_para_cuit", return_value={"token": "t", "sign": "s", "fuente_certificado": "propio"}), \
             patch.object(arca_ws, "_soap_post", side_effect=fake_soap_2p):
            r_2p = client.post("/api/v1/mcp/tool", headers={"X-User-Token": tok_ve}, json={
                "name": "leer_notificaciones_dfe", "arguments": {"cuit": cuit_ve, "ambiente": "homologacion"},
            }).json()
            self.assertTrue(r_2p.get("ok"))
            self.assertEqual(r_2p.get("fuente"), "VECONSUMERWS")
            self.assertEqual(r_2p.get("total"), 2)
            self.assertEqual(len(r_2p.get("notificaciones", [])), 2)
            self.assertEqual(r_2p["notificaciones"][0]["estado_desc"], "No Leída")
            self.assertEqual(r_2p["notificaciones"][1]["estado_desc"], "Leída")

        # 3. Vacío (totalItems=0)
        bot_main.TOOL_CACHE.clear()
        with patch.object(arca_ws, "autenticar_wsaa_para_cuit", return_value={"token": "t", "sign": "s", "fuente_certificado": "propio"}), \
             patch.object(arca_ws, "_soap_post", return_value=xml_vacio):
            r_empty = client.post("/api/v1/mcp/tool", headers={"X-User-Token": tok_ve}, json={
                "name": "leer_notificaciones_dfe", "arguments": {"cuit": cuit_ve, "ambiente": "homologacion"},
            }).json()
            self.assertTrue(r_empty.get("ok"))
            self.assertEqual(r_empty.get("total"), 0)
            self.assertEqual(r_empty.get("notificaciones"), [])

        # 4. Fault, XML malformado, totalItems>0 vacío, y error de auth (HTTP 401) -> todos error explícito
        for label, side_eff in (
            ("fault", lambda *a, **k: xml_fault),
            ("malformed", lambda *a, **k: "<soap:Broken><unclosed"),
            ("total_sin_items", lambda *a, **k: xml_total_sin_items),
            ("auth_401", lambda *a, **k: (_ for _ in ()).throw(_uerr.HTTPError("https://x", 401, "Unauthorized", {}, None))),
        ):
            bot_main.TOOL_CACHE.clear()
            with patch.object(arca_ws, "autenticar_wsaa_para_cuit", return_value={"token": "t", "sign": "s", "fuente_certificado": "propio"}), \
                 patch.object(arca_ws, "_soap_post", side_effect=side_eff):
                r_err = client.post("/api/v1/mcp/tool", headers={"X-User-Token": tok_ve}, json={
                    "name": "leer_notificaciones_dfe", "arguments": {"cuit": cuit_ve, "ambiente": "homologacion"},
                }).json()
                self.assertFalse(r_err.get("ok"), f"Caso {label} debería fallar explícitamente: {r_err}")
                self.assertNotIn("notificaciones", r_err)

        # 5. abrir_comunicacion_dfe sin confirmado=True -> rechazado con aviso legal
        r_noconf = client.post("/api/v1/mcp/tool", headers={"X-User-Token": tok_ve}, json={
            "name": "abrir_comunicacion_dfe", "arguments": {"cuit": cuit_ve, "id_comunicacion": 101},
        }).json()
        self.assertFalse(r_noconf.get("ok"))
        self.assertTrue(r_noconf.get("requiere_confirmacion"))
        self.assertIn("notificado", r_noconf.get("aviso_legal", "").lower())

        # 6. abrir_comunicacion_dfe con confirmado=True + adjunto gzip con MD5 válido vs MD5 desparejo
        plain_doc = b"Resolucion ARCA 2026 contenido oficial"
        gz_bytes = _gzip.compress(plain_doc)
        gz_b64 = _b64.b64encode(gz_bytes).decode("ascii")
        md5_ok = _hl.md5(gz_bytes).hexdigest()
        xml_com_ok = (
            '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
            '<soap:Body><consumirComunicacionResponse><Comunicacion>'
            '<mensaje>Texto completo de notificación DFE</mensaje><tiempoDeVida>30</tiempoDeVida>'
            f'<adjuntos><adjunto><filename>intimacion.txt</filename><content>{gz_b64}</content>'
            f'<compressed>true</compressed><signed>false</signed><encrypted>false</encrypted>'
            f'<md5>{md5_ok}</md5><contentSize>{len(gz_bytes)}</contentSize></adjunto></adjuntos>'
            '</Comunicacion></consumirComunicacionResponse></soap:Body></soap:Envelope>'
        )
        xml_com_bad_md5 = xml_com_ok.replace(md5_ok, "0" * 32)

        with patch.object(arca_ws, "autenticar_wsaa_para_cuit", return_value={"token": "t", "sign": "s", "fuente_certificado": "propio"}), \
             patch.object(arca_ws, "_soap_post", return_value=xml_com_ok):
            r_open = client.post("/api/v1/mcp/tool", headers={"X-User-Token": tok_ve}, json={
                "name": "abrir_comunicacion_dfe",
                "arguments": {"cuit": cuit_ve, "id_comunicacion": 101, "incluir_adjuntos": True, "confirmado": True, "ambiente": "homologacion"},
            }).json()
            self.assertTrue(r_open.get("ok"))
            self.assertEqual(r_open.get("mensaje"), "Texto completo de notificación DFE")
            self.assertEqual(_b64.b64decode(r_open["adjuntos"][0]["content_base64"]), plain_doc)

        with patch.object(arca_ws, "autenticar_wsaa_para_cuit", return_value={"token": "t", "sign": "s", "fuente_certificado": "propio"}), \
             patch.object(arca_ws, "_soap_post", return_value=xml_com_bad_md5):
            r_bad_md5 = client.post("/api/v1/mcp/tool", headers={"X-User-Token": tok_ve}, json={
                "name": "abrir_comunicacion_dfe",
                "arguments": {"cuit": cuit_ve, "id_comunicacion": 101, "incluir_adjuntos": True, "confirmado": True, "ambiente": "homologacion"},
            }).json()
            self.assertFalse(r_bad_md5.get("ok"))
            self.assertIn("md5", r_bad_md5.get("error", "").lower())

        # 7. E1 (P1): owner PENDIENTE no puede leer ni abrir DFE por Web Service -> estado=PENDIENTE_VALIDACION
        cuit_pend = "20777777782"
        em_pend = "pend_ve34@impuesto.test"
        tok_pend = _tok_verificado(em_pend)
        _bv_mod.guardar_credenciales_cifradas(cuit=cuit_pend, clave_fiscal="FalsaPend", owner_email=em_pend)
        r_p1 = client.post("/api/v1/mcp/tool", headers={"X-User-Token": tok_pend}, json={
            "name": "leer_notificaciones_dfe", "arguments": {"cuit": cuit_pend},
        }).json()
        r_p2 = client.post("/api/v1/mcp/tool", headers={"X-User-Token": tok_pend}, json={
            "name": "abrir_comunicacion_dfe", "arguments": {"cuit": cuit_pend, "id_comunicacion": 1, "confirmado": True},
        }).json()
        self.assertFalse(r_p1.get("ok"))
        self.assertEqual(r_p1.get("estado"), "PENDIENTE_VALIDACION")
        self.assertFalse(r_p2.get("ok"))
        self.assertEqual(r_p2.get("estado"), "PENDIENTE_VALIDACION")

        # 8. E2 (P2): invitado solo_lectura de un owner validado NO puede abrir comunicación DFE (requiere owner)
        em_lec = "lector_ve34@impuesto.test"
        tok_lec = _tok_verificado(em_lec)
        _bv_mod.autorizar_usuario_cuit(em_ve, cuit_ve, em_lec, rol="solo_lectura")
        r_lec_ab = client.post("/api/v1/mcp/tool", headers={"X-User-Token": tok_lec}, json={
            "name": "abrir_comunicacion_dfe", "arguments": {"cuit": cuit_ve, "id_comunicacion": 101, "confirmado": True},
        }).json()
        self.assertFalse(r_lec_ab.get("ok"))
        self.assertTrue(r_lec_ab.get("acceso_denegado"))

        # 9. P3: truncado=True cuando totalPaginas > max_paginas y zip-bomb acotado por max_length
        xml_pag_trunc = xml_pag1.replace("<totalPaginas>2</totalPaginas>", "<totalPaginas>15</totalPaginas>")
        with patch.object(arca_ws, "autenticar_wsaa_para_cuit", return_value={"token": "t", "sign": "s", "fuente_certificado": "propio"}), \
             patch.object(arca_ws, "_soap_post", return_value=xml_pag_trunc):
            r_tr = ve.consultar_comunicaciones_ve(cuit_ve, ambiente="homologacion", max_paginas=1)
            self.assertTrue(r_tr.get("ok"))
            self.assertTrue(r_tr.get("truncado"))


if __name__ == "__main__":
    unittest.main()
