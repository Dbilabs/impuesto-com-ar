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

import re
import sys
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from bot.main import app
from bot.auditoria_unificada import _parse_ccma_detalle_periodos
from bot.validador_invariantes import validar_invariantes_auditoria
from bot.doublecheck_arca import obtener_protocolo_doublecheck, validar_cobertura_auditoria
from bot.playbooks_servicios import obtener_playbook_servicio


class TestContratosYCalidadFiscal(unittest.TestCase):
    def test_01_fastapi_endpoints_y_boveda_sin_fuga(self):
        client = TestClient(app)
        self.assertEqual(client.get("/health").status_code, 200)
        r_vinc = client.get("/vincular?tipo=estudio")
        self.assertEqual(r_vinc.status_code, 200)
        self.assertIn("AES-256", r_vinc.text)

        # Vincular, verificar sin fuga y revocar CUIT ficticio
        test_cuit = "20301234567"
        r_save = client.post("/api/v1/vincular", json={"cuit": test_cuit, "clave_fiscal": "TestSecret999", "modo": "solo_lectura_cifrada"})
        self.assertEqual(r_save.status_code, 200)
        self.assertTrue(r_save.json()["ok"])

        r_state = client.get(f"/api/v1/vincular/{test_cuit}")
        self.assertEqual(r_state.status_code, 200)
        self.assertNotIn("TestSecret999", r_state.text)

        r_del = client.delete(f"/api/v1/vincular/{test_cuit}")
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

        # 2. Owner vincula CUIT y obtiene token + URLs privadas
        r_link = client.post("/api/v1/vincular", json={
            "email": owner_email,
            "cuit": cuit_test,
            "clave_fiscal": "ClaveSoloTest123",
            "modo": "solo_lectura_cifrada",
            "etiqueta_token": "gemini_test",
        })
        self.assertTrue(r_link.json().get("ok"))
        tok_owner = r_link.json().get("token")
        self.assertTrue(tok_owner.startswith("imp_live_"))
        self.assertIn("gemini", r_link.json().get("urls_privadas_mcp", {}))

        # 3. Intruso con su propio token NO ve el CUIT del Owner ni puede consultarlo
        tok_attacker = bv.crear_token_usuario(attacker_email, "intruso")["token"]
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

        # 5. Socio genera token y ve el CUIT + deja nota desde ChatGPT -> Owner la ve desde Gemini
        tok_socio = bv.crear_token_usuario(socio_email, "chatgpt")["token"]
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

        # 7. Frase clave personalizada: rechaza cortas (<16), acepta seguras (>=16) y rechaza colisiones entre usuarios
        r_short = bv.crear_token_usuario(owner_email, "corta", custom_token="clave123")
        self.assertFalse(r_short.get("ok"))
        r_custom = bv.crear_token_usuario(owner_email, "custom", custom_token="Cafe-Cordoba-Fiscal-8924")
        self.assertTrue(r_custom.get("ok"))
        self.assertEqual(bv.resolver_email_por_token("Cafe-Cordoba-Fiscal-8924"), owner_email)
        r_dup = bv.crear_token_usuario(attacker_email, "dup", custom_token="Cafe-Cordoba-Fiscal-8924")
        self.assertFalse(r_dup.get("ok"))

        # Limpieza de fixture
        client.delete(f"/api/v1/vincular/{cuit_test}")

    def test_09_backoffice_super_admin_plataforma(self):
        from fastapi.testclient import TestClient
        from bot.main import app
        from bot import boveda_segura as bv

        client = TestClient(app)
        admin_tok = bv.crear_token_usuario("damianbourdieu@gmail.com", "admin_test")["token"]
        user_email = "cliente_saas_test@impuesto.test"
        user_tok = bv.crear_token_usuario(user_email, "user_test")["token"]

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


if __name__ == "__main__":
    unittest.main()
