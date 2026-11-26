"""
bot/manuales_knowledge.py
Módulo de Consulta de Manuales, Guías Paso a Paso y Lógica Operativa de ARCA.
Permite a la IA acceder al conocimiento oficial de los 245 trámites indexados,
comprendiendo la arquitectura de rutas, solapas y lógica histórica de cada servicio.
"""

import os
import json
from typing import Dict, Any, List, Optional

DATA_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "manuales_arca", "indice_guias_arca.json"))

def cargar_base_conocimiento() -> Dict[str, Any]:
    if os.path.exists(DATA_PATH):
        try:
            with open(DATA_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"guias_oficiales": [], "manuales_operativos_servicios": {}}

def buscar_manual_o_guia(query: str, categoria: Optional[str] = None) -> Dict[str, Any]:
    """
    Busca manuales oficiales, guías paso a paso y flujos de pantallas de ARCA.
    Contempla la equivalencia histórica ARCA == AFIP == DGI.
    """
    base = cargar_base_conocimiento()
    guias = base.get("guias_oficiales", [])
    servicios = base.get("manuales_operativos_servicios", {})
    
    # Normalización y expansión de sinónimos ARCA <-> AFIP <-> DGI
    q_lower = query.lower()
    q_words = [w for w in q_lower.split() if len(w) > 2]
    
    # Expansión de sinónimos institucionales
    palabras_expandidas = list(q_words)
    if "arca" in q_words and "afip" not in palabras_expandidas:
        palabras_expandidas.append("afip")
    if "afip" in q_words and "arca" not in palabras_expandidas:
        palabras_expandidas.append("arca")
    if "dgi" in q_words:
        palabras_expandidas.extend(["afip", "arca"])
        
    # 1. Coincidencias en servicios operativos clave
    servicios_relevantes = []
    for k, serv in servicios.items():
        txt_serv = (serv.get("nombre", "") + " " + json.dumps(serv)).lower()
        if any(w in txt_serv for w in palabras_expandidas) or not q_words:
            servicios_relevantes.append(serv)
            
    # 2. Coincidencias en las 245 guías paso a paso oficiales
    guias_relevantes = []
    for g in guias:
        if categoria and g.get("categoria", "").upper() != categoria.upper():
            continue
        txt_guia = (g.get("titulo", "") + " " + g.get("categoria", "")).lower()
        if any(w in txt_guia for w in palabras_expandidas) or not q_words:
            guias_relevantes.append(g)
            
    return {
        "consulta": query,
        "categoria_filtro": categoria or "TODAS",
        "contexto_institucional_arca_afip": (
            "ARCA (Agencia de Recaudación y Control Aduanero) es el nuevo nombre oficial que sustituyó a la AFIP "
            "a partir del Decreto 953/2024. Los sistemas informáticos, resoluciones generales, formularios (F. 762, F. 2002, "
            "F. 931) y URLs con dominios .afip.gob.ar mantienen total vigencia, equivalencia y continuidad jurídica."
        ),
        "total_servicios_arquitectura_encontrados": len(servicios_relevantes),
        "arquitectura_servicios_y_rutas": servicios_relevantes,
        "total_guias_paso_a_paso_encontradas": len(guias_relevantes),
        "guias_oficiales_muestra": guias_relevantes[:15],
        "leccion_operativa_arca": (
            "ARCA utiliza Single Page Applications (SPA) y sistemas legados heredados de AFIP. "
            "Es mandatorio no limitarse a la pantalla de bienvenida (#/inicio) y navegar "
            "las solapas de historiales (ej. '#/declaraciones.anteriores' en F. 762 Bienes Personales)."
        )
    }
    }

if __name__ == "__main__":
    res = buscar_manual_o_guia("bienes personales f762")
    print(f"Servicios: {res['total_servicios_arquitectura_encontrados']}, Guías: {res['total_guias_paso_a_paso_encontradas']}")
