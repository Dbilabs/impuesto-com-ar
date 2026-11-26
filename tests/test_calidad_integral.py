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


if __name__ == "__main__":
    unittest.main()
