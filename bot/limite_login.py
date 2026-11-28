"""
bot/limite_login.py
Limitador de intentos de autenticación/OTP en tres niveles (IP+usuario, usuario, solo IP y global).
Inspirado en src/auth/limiteLogin.js de diegoparras/arcanum (Licencia MIT).

Características (cierre R2 + N3 + N3-b):
- Claves hasheadas con SHA-256 (nunca almacena emails ni IPs en claro en memoria).
- Normalización compartida de IP (`normalizar_clave_ip`): IPv4 completa e IPv6 agrupada por /64.
- Memoria acotada (máx. 10.000 entradas con poda periódica y LRU).
- Backoff exponencial por (IP, usuario) desde el umbral (30s -> 1m -> 2m -> ... máx. 15m).
- Topes globales por minuto, hora y día dimensionados a la cuota real del proveedor de email
  (configurables por env), con alerta en log al 80 %.
- En envíos OTP, cuando se activa el tope global solo se bloquean emails NUNCA verificados:
  los usuarios ya verificados/conocidos siguen pudiendo pedir OTP (cierre N3-b).
"""

import hashlib
import ipaddress
import logging
import os
import threading
import time
from collections import OrderedDict
from typing import Dict, Optional, Tuple

logger = logging.getLogger("impuesto.limite_login")


def normalizar_clave_ip(ip: str) -> str:
    """Clave normalizada compartida: IPv4 completa; IPv6 agrupada por prefijo /64 (N3-b)."""
    raw = (ip or "").strip()
    if not raw:
        return "unknown"
    # Si viene X-Forwarded-For con múltiples IPs, tomar la primera
    if "," in raw:
        raw = raw.split(",")[0].strip()
    # Quitar corchetes de IPv6 con puerto si viniera [::1]:1234
    if raw.startswith("[") and "]" in raw:
        raw = raw[1:raw.index("]")]
    try:
        addr = ipaddress.ip_address(raw)
        if isinstance(addr, ipaddress.IPv6Address):
            if addr.ipv4_mapped:
                return str(addr.ipv4_mapped)
            return str(ipaddress.ip_network(f"{addr}/64", strict=False))
        return str(addr)
    except ValueError:
        return raw[:64] or "unknown"


def _h(val: str) -> str:
    return hashlib.sha256(val.encode("utf-8")).hexdigest()[:24]


class LimiteLogin:
    def __init__(
        self,
        por_ip_usuario: int = 5,
        por_usuario: int = 10,
        global_por_min: int = 200,
        max_claves: int = 10000,
        por_ip: int = 0,
        global_por_hora: int = 0,
        global_por_dia: int = 0,
        solo_bloquear_desconocidos_en_global: bool = False,
        nombre: str = "limite",
    ):
        self.por_ip_usuario = por_ip_usuario
        self.por_usuario = por_usuario
        self.por_ip = por_ip
        self.global_por_min = global_por_min
        self.global_por_hora = global_por_hora
        self.global_por_dia = global_por_dia
        self.solo_bloquear_desconocidos_en_global = solo_bloquear_desconocidos_en_global
        self.nombre = nombre
        self.max_claves = max_claves
        self._lock = threading.Lock()
        self._fallos: OrderedDict[str, Dict[str, float]] = OrderedDict()
        self._ventana_global = {"desde": 0.0, "n": 0, "hasta": 0.0}
        self._ventana_hora = {"desde": 0.0, "n": 0, "alertado": False}
        self._ventana_dia = {"desde": 0.0, "n": 0, "alertado": False}
        self._ops = 0

    def _clave_ip(self, ip: str, usuario: str) -> str:
        ip_k = normalizar_clave_ip(ip)
        return "i:" + _h(f"{ip_k}\n{(usuario or '').strip().lower()}")

    def _clave_solo_ip(self, ip: str) -> str:
        ip_k = normalizar_clave_ip(ip)
        return "p:" + _h(ip_k)

    def _clave_usuario(self, usuario: str) -> str:
        return "u:" + _h((usuario or "").strip().lower())

    def _podar(self, now: float, forzar: bool = False) -> None:
        self._ops += 1
        if not forzar and len(self._fallos) <= self.max_claves and (self._ops % 100) != 0:
            return
        to_del = [k for k, v in self._fallos.items() if v["hasta"] <= now and (now - v["visto"]) > 900.0]
        for k in to_del:
            self._fallos.pop(k, None)
        while len(self._fallos) > self.max_claves:
            self._fallos.popitem(last=False)

    def _sumar(self, clave: str, umbral: int, espera_fn, now: float) -> None:
        rec = self._fallos.get(clave) or {"n": 0, "hasta": 0.0, "visto": now}
        if now - rec["visto"] > 900.0 and rec["hasta"] <= now:
            rec = {"n": 0, "hasta": 0.0, "visto": now}
        rec["n"] += 1
        rec["visto"] = now
        if rec["n"] >= umbral:
            rec["hasta"] = now + espera_fn(rec["n"] - umbral)
        self._fallos.pop(clave, None)
        self._fallos[clave] = rec

    def _tope_global_activo(self, now: float) -> Optional[str]:
        if self._ventana_global["hasta"] > now:
            return "Demasiados intentos en la plataforma. Probá de nuevo en 1 minuto."
        if self.global_por_hora > 0 and (now - self._ventana_hora["desde"]) <= 3600.0 and self._ventana_hora["n"] >= self.global_por_hora:
            return "Se alcanzó el cupo horario de envíos para nuevos registros. Probá de nuevo más tarde."
        if self.global_por_dia > 0 and (now - self._ventana_dia["desde"]) <= 86400.0 and self._ventana_dia["n"] >= self.global_por_dia:
            return "Se alcanzó el cupo diario de envíos para nuevos registros. Probá de nuevo mañana."
        return None

    def chequear(self, ip: str, usuario: str, *, es_usuario_conocido: bool = False) -> Tuple[bool, Optional[str]]:
        now = time.time()
        with self._lock:
            msg_global = self._tope_global_activo(now)
            if msg_global:
                # N3-b: cuando se activa el tope global en envíos OTP, los usuarios ya verificados siguen entrando
                if not (self.solo_bloquear_desconocidos_en_global and es_usuario_conocido):
                    return False, msg_global
            claves = [self._clave_ip(ip, usuario), self._clave_usuario(usuario)]
            if self.por_ip > 0:
                claves.append(self._clave_solo_ip(ip))
            for k in claves:
                r = self._fallos.get(k)
                if r and r["hasta"] > now:
                    wait_s = max(1, int(r["hasta"] - now))
                    return False, f"Demasiados intentos. Esperá {wait_s} segundos antes de reintentar."
        return True, None

    def registrar_fallo(self, ip: str, usuario: str) -> None:
        now = time.time()
        with self._lock:
            self._sumar(
                self._clave_ip(ip, usuario),
                self.por_ip_usuario,
                lambda extra: min(900.0, 30.0 * (2 ** min(extra, 6))),
                now,
            )
            self._sumar(
                self._clave_usuario(usuario),
                self.por_usuario,
                lambda _extra: 900.0,
                now,
            )
            if self.por_ip > 0:
                self._sumar(
                    self._clave_solo_ip(ip),
                    self.por_ip,
                    lambda extra: min(900.0, 60.0 * (2 ** min(extra, 4))),
                    now,
                )
            if now - self._ventana_global["desde"] > 60.0:
                self._ventana_global = {"desde": now, "n": 0, "hasta": 0.0}
            self._ventana_global["n"] += 1
            if self._ventana_global["n"] >= self.global_por_min:
                self._ventana_global["hasta"] = now + 60.0

            if self.global_por_hora > 0:
                if now - self._ventana_hora["desde"] > 3600.0:
                    self._ventana_hora = {"desde": now, "n": 0, "alertado": False}
                self._ventana_hora["n"] += 1
                if not self._ventana_hora["alertado"] and self._ventana_hora["n"] >= int(self.global_por_hora * 0.8):
                    self._ventana_hora["alertado"] = True
                    logger.warning(f"[ALERTA CUOTA 80%] {self.nombre}: {self._ventana_hora['n']}/{self.global_por_hora} envíos en la última hora.")

            if self.global_por_dia > 0:
                if now - self._ventana_dia["desde"] > 86400.0:
                    self._ventana_dia = {"desde": now, "n": 0, "alertado": False}
                self._ventana_dia["n"] += 1
                if not self._ventana_dia["alertado"] and self._ventana_dia["n"] >= int(self.global_por_dia * 0.8):
                    self._ventana_dia["alertado"] = True
                    logger.warning(f"[ALERTA CUOTA 80%] {self.nombre}: {self._ventana_dia['n']}/{self.global_por_dia} envíos en las últimas 24h.")

            self._podar(now)

    def registrar_exito(self, ip: str, usuario: str) -> None:
        with self._lock:
            self._fallos.pop(self._clave_ip(ip, usuario), None)
            self._fallos.pop(self._clave_usuario(usuario), None)


# Instancias separadas (N3 + N3-b):
# - LIMITE_OTP_ENVIO: balde por IP/64 (5/15m), por email (5/15m), cupo global por min/hora/día configurable
#   (dimensionado a cuota de Resend, con alerta al 80 %) y bypass de tope global para usuarios ya verificados.
LIMITE_OTP_ENVIO = LimiteLogin(
    por_ip_usuario=3,
    por_usuario=5,
    por_ip=5,
    global_por_min=int(os.environ.get("OTP_GLOBAL_PER_MIN", "100")),
    global_por_hora=int(os.environ.get("OTP_GLOBAL_PER_HOUR", "300")),
    global_por_dia=int(os.environ.get("OTP_GLOBAL_PER_DAY", "1000")),
    solo_bloquear_desconocidos_en_global=True,
    nombre="LIMITE_OTP_ENVIO",
)
LIMITE_OTP_VERIF = LimiteLogin(por_ip_usuario=5, por_usuario=10, global_por_min=150, nombre="LIMITE_OTP_VERIF")
LIMITE_LOGIN_CHAT = LimiteLogin(por_ip_usuario=5, por_usuario=10, global_por_min=150, nombre="LIMITE_LOGIN_CHAT")
