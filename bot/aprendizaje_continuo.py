"""
bot/aprendizaje_continuo.py
Ciclo de Aprendizaje Continuo (Knowledge Loop) para el Estudio Contable Agéntico.

Cuando un cliente hace una pregunta para la cual el bot no tiene una respuesta validada:
1. No inventa ni alucina: registra la pregunta en la cola de investigación (pendiente) y la deriva
   a un contador especialista humano.
2. Una vez resuelta y validada, la respuesta se incorpora automáticamente al conocimiento
   permanente del bot para futuros clientes.
"""

import os
import json
import uuid
import datetime
from typing import Dict, Any, List, Optional

DATA_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "conocimiento_aprendido.json"))
os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)


def _cargar_db() -> List[Dict[str, Any]]:
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []


def _guardar_db(items: List[Dict[str, Any]]):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2, ensure_ascii=False)


def registrar_consulta_sin_respuesta(
    pregunta: str,
    cuit_origen: Optional[str] = None,
    contexto_cliente: Optional[str] = None
) -> Dict[str, Any]:
    """
    Agenda una consulta tributaria que el bot aún no tiene resuelta con certeza,
    para que un especialista humano la resuelva y luego quede incorporada al conocimiento del bot.
    """
    items = _cargar_db()
    cid = f"KNOW-{datetime.datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:6].upper()}"
    ahora = datetime.datetime.now().isoformat()

    registro = {
        "id": cid,
        "cuit_origen": cuit_origen or "anonimo",
        "pregunta": pregunta.strip(),
        "contexto_cliente": contexto_cliente or "",
        "estado": "pendiente",
        "respuesta_clara": None,
        "normativa_oficial": None,
        "creada": ahora,
        "resuelta": None
    }
    items.append(registro)
    _guardar_db(items)

    return {
        "consulta_id": cid,
        "estado": "AGENDADA_PARA_ESPECIALISTA",
        "pregunta_registrada": pregunta.strip(),
        "mensaje_para_cliente": (
            f"Agendé tu consulta bajo el código {cid} para que un contador especialista de nuestro equipo "
            "la revise con precisión normativa. Apenas tengamos el dictamen confirmado te avisamos y además "
            "queda incorporado al conocimiento del asistente."
        )
    }


def incorporar_conocimiento_resuelto(
    consulta_id: str,
    respuesta_clara: str,
    normativa_oficial: str = ""
) -> Dict[str, Any]:
    """
    Cierra una consulta pendiente e incorpora la respuesta validada al cerebro permanente del bot.
    """
    items = _cargar_db()
    ahora = datetime.datetime.now().isoformat()
    for it in items:
        if it["id"] == consulta_id:
            it["estado"] = "resuelta_y_aprendida"
            it["respuesta_clara"] = respuesta_clara.strip()
            it["normativa_oficial"] = normativa_oficial.strip()
            it["resuelta"] = ahora
            _guardar_db(items)
            return {
                "ok": True,
                "consulta_id": consulta_id,
                "estado": "resuelta_y_aprendida",
                "mensaje": "Conocimiento incorporado exitosamente a la base permanente del bot."
            }

    return {"ok": False, "error": f"No se encontró la consulta {consulta_id}."}


def buscar_conocimiento_aprendido(query: str) -> Dict[str, Any]:
    """
    Busca respuestas previamente resueltas por contadores especialistas e incorporadas al bot.
    """
    items = _cargar_db()
    resueltas = [it for it in items if it.get("estado") == "resuelta_y_aprendida"]
    q_words = [w.lower() for w in query.split() if len(w) > 2]

    matches = []
    for it in resueltas:
        txt = (it.get("pregunta", "") + " " + (it.get("respuesta_clara") or "") + " " + (it.get("normativa_oficial") or "")).lower()
        if not q_words or any(w in txt for w in q_words):
            matches.append(it)

    return {
        "consulta": query,
        "total_aprendido_en_base": len(resueltas),
        "coincidencias": matches[:10]
    }
