"""
bot/limite_login.py
Limitador de intentos de autenticación/OTP en tres niveles (IP+usuario, usuario y global).
Inspirado en src/auth/limiteLogin.js de diegoparras/arcanum (Licencia MIT).

Características:
- Claves hasheadas con SHA-256 (nunca almacena emails ni IPs en claro en memoria).
- Memoria acotada (máx. 10.000 entradas con poda LRU).
- Backoff exponencial por (IP, usuario) desde el 5° fallo (30s -> 1m -> 2m -> ... máx. 15m).
- Límite por usuario (10 fallos -> 15m; evita bloqueos DoS de 24h sobre la víctima).
- Límite global por minuto (200 eventos/min -> pausa 60s).
"""

import hashlib
import threading
import time
from collections import OrderedDict
from typing import Dict, Optional, Tuple


def _h(val: str) -> str:
    return hashlib.sha256(val.encode("utf-8")).hexdigest()[:24]


class LimiteLogin:
    def __init__(
        self,
        por_ip_usuario: int = 5,
        por_usuario: int = 10,
        global_por_min: int = 200,
        max_claves: int = 10000,
    ):
        self.por_ip_usuario = por_ip_usuario
        self.por_usuario = por_usuario
        self.global_por_min = global_por_min
        self.max_claves = max_claves
        self._lock = threading.Lock()
        self._fallos: OrderedDict[str, Dict[str, float]] = OrderedDict()
        self._ventana_global = {"desde": 0.0, "n": 0, "hasta": 0.0}

    def _clave_ip(self, ip: str, usuario: str) -> str:
        return "i:" + _h(f"{ip}\n{(usuario or '').strip().lower()}")

    def _clave_usuario(self, usuario: str) -> str:
        return "u:" + _h((usuario or "").strip().lower())

    def _podar(self, now: float) -> None:
        if len(self._fallos) <= self.max_claves:
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

    def chequear(self, ip: str, usuario: str) -> Tuple[bool, Optional[str]]:
        now = time.time()
        with self._lock:
            if self._ventana_global["hasta"] > now:
                return False, "Demasiados intentos en la plataforma. Probá de nuevo en 1 minuto."
            for k in (self._clave_ip(ip, usuario), self._clave_usuario(usuario)):
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
            if now - self._ventana_global["desde"] > 60.0:
                self._ventana_global = {"desde": now, "n": 0, "hasta": 0.0}
            self._ventana_global["n"] += 1
            if self._ventana_global["n"] >= self.global_por_min:
                self._ventana_global["hasta"] = now + 60.0
            self._podar(now)

    def registrar_exito(self, ip: str, usuario: str) -> None:
        with self._lock:
            self._fallos.pop(self._clave_ip(ip, usuario), None)
            self._fallos.pop(self._clave_usuario(usuario), None)


# Instancias separadas para envío OTP, verificación OTP y login por frase clave
LIMITE_OTP_ENVIO = LimiteLogin(por_ip_usuario=3, por_usuario=5, global_por_min=60)
LIMITE_OTP_VERIF = LimiteLogin(por_ip_usuario=5, por_usuario=10, global_por_min=150)
LIMITE_LOGIN_CHAT = LimiteLogin(por_ip_usuario=5, por_usuario=10, global_por_min=150)
