"""
bot/poc_http/arca_http.py
PoC Fase 3.2: Login HTTP puro contra ARCA (CCMA, Mis Facilidades, SCT) sin Chromium.

- Detrás del flag `ARCA_HTTP_LOGIN=1` (apagado por defecto; NO conectado a producción).
- Patrón basado en `afip-siradig-automation` (skill `pagosafip-siradig-http`):
  1. GET  https://auth.afip.gob.ar/contribuyente_/login.xhtml  -> javax.faces.ViewState
  2. POST F1:username + F1:btnSiguiente                       -> nuevo ViewState
  3. POST F1:password + F1:btnIngresar                        -> password_enviada=True, extraer jwt
  4. POST https://portalcf.cloud.afip.gob.ar/portal/login     -> sesión autenticada en Portal CF
  5. GET  https://portalcf.cloud.afip.gob.ar/portal/api/servicios/<CUIT>/servicio/<id>/autorizacion -> token y sign
  6. POST al servicio destino (CCMA / Mis Facilidades / SCT)
- Usa las mismas excepciones tipadas por etapa que Playwright (`ArcaNoDisponible`,
  `LoginNoConfirmado`, `ClaveIncorrecta`) y NO toma `PLAYWRIGHT_SEM`.
- Seguridad: NUNCA loguea clave fiscal, cookies, jwt, token ni sign.
"""

import html
import logging
import os
import re
from typing import Any, Dict, Optional

import httpx

from ..arca_errors import ArcaLoginError, ArcaNoDisponible, ClaveIncorrecta, LoginNoConfirmado

logger = logging.getLogger("impuesto.poc_http")

LOGIN_URL = "https://auth.afip.gob.ar/contribuyente_/login.xhtml"
PORTAL_LOGIN_URL = "https://portalcf.cloud.afip.gob.ar/portal/login"
PORTAL_AUTH_URL_TPL = "https://portalcf.cloud.afip.gob.ar/portal/api/servicios/{cuit}/servicio/{servicio_id}/autorizacion"

# Mapeo inicial de servicios ARCA (los IDs exactos de portalcf se validan capturando un HAR de Playwright)
SERVICIOS_ARCA_HTTP: Dict[str, Dict[str, str]] = {
    "ccma": {
        "servicio_id": "ccma",
        "post_url": "https://servicios1.afip.gob.ar/Tramites_con_clave_fiscal/ccma/index.aspx",
        "nombre": "CCMA - Cuenta Corriente de Monotributistas y Autónomos",
    },
    "mis_facilidades": {
        "servicio_id": "misfacilidades",
        "post_url": "https://servicios1.afip.gob.ar/MisFacilidades/index.aspx",
        "nombre": "Mis Facilidades",
    },
    "sct": {
        "servicio_id": "sct",
        "post_url": "https://servicios1.afip.gob.ar/SCT/index.aspx",
        "nombre": "Sistema de Cuentas Tributarias",
    },
}

_SENSITIVE_KEYS = ("password", "clave", "cookie", "set-cookie", "authorization", "token", "sign", "jwt")


class ServicioNoAutorizadoError(ArcaLoginError):
    """El CUIT no tiene adherido/autorizado el servicio solicitado en Portal CF (paso 5)."""


def is_http_login_enabled() -> bool:
    """Devuelve True solo si ARCA_HTTP_LOGIN=1 está explícitamente habilitado (apagado por defecto)."""
    return os.environ.get("ARCA_HTTP_LOGIN", "").strip() == "1"


def redactar_headers_y_payload(obj: Any) -> Any:
    """Redacta recursivamente clave, cookies, token, sign y jwt antes de guardar HAR o logs."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            kl = str(k).lower()
            if any(s in kl for s in _SENSITIVE_KEYS):
                out[k] = "[REDACTED]"
            else:
                out[k] = redactar_headers_y_payload(v)
        return out
    if isinstance(obj, list):
        return [redactar_headers_y_payload(x) for x in obj]
    return obj


def _extract_input_value(html_text: str, name_or_id: str) -> Optional[str]:
    """Extrae el atributo `value` de un <input> por `name` o `id` (ViewState, jwt, etc.)."""
    if not html_text:
        return None
    pat_tag = re.compile(
        rf"<input\b[^>]*(?:name|id)\s*=\s*['\"]{re.escape(name_or_id)}['\"][^>]*>",
        re.IGNORECASE,
    )
    m = pat_tag.search(html_text)
    if not m:
        return None
    tag = m.group(0)
    m_val = re.search(r"\bvalue\s*=\s*['\"]([^'\"]*)['\"]", tag, re.IGNORECASE)
    if not m_val:
        return None
    return html.unescape(m_val.group(1)).strip()


def _clasificar_rechazo_html(html_text: str) -> None:
    """Si la respuesta HTML tras enviar la contraseña indica rechazo explícito, lanza ClaveIncorrecta."""
    low = (html_text or "").lower()
    if "g-recaptcha" in low or "captcha" in low or "verificación de seguridad" in low:
        raise ClaveIncorrecta("ARCA solicitó CAPTCHA durante el login HTTP.", captcha=True)
    if "clave bloqueada" in low or "usuario bloqueado" in low or "bloqueada" in low:
        raise ClaveIncorrecta("CLAVE_FISCAL_BLOQUEADA: ARCA informó que la Clave Fiscal está bloqueada.", bloqueada=True)
    if "cambio de clave" in low or "cambiar su clave" in low or "debe cambiar" in low:
        raise ClaveIncorrecta("CAMBIO DE CLAVE obligatorio requerido por ARCA.", cambio_clave=True)
    if (
        "clave o usuario incorrecto" in low
        or "usuario o clave incorrecta" in low
        or "clave fiscal incorrecta" in low
        or "f1:msg" in low and "incorrect" in low
    ):
        raise ClaveIncorrecta("CLAVE_FISCAL_INCORRECTA: ARCA rechazó la Clave Fiscal.")


class ArcaHttpClient:
    """Cliente HTTP stateful (cookie jar en memoria, sin persistir cookies) para PoC Fase 3.2."""

    def __init__(
        self,
        *,
        timeout: float = 20.0,
        transport: Optional[httpx.BaseTransport] = None,
        require_flag: bool = True,
    ) -> None:
        self.timeout = timeout
        self.transport = transport
        self.require_flag = require_flag

    def _new_client(self) -> httpx.Client:
        return httpx.Client(
            timeout=self.timeout,
            follow_redirects=True,
            transport=self.transport,
            headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126.0.0.0 Safari/537.36",
                "Accept-Language": "es-AR,es;q=0.9",
            },
        )

    def autenticar_y_abrir_servicio(
        self,
        *,
        cuit: str,
        clave: str,
        servicio: str = "ccma",
    ) -> Dict[str, Any]:
        """Ejecuta los 6 pasos del login HTTP y abre el servicio ARCA solicitado.
        Respeta la clasificación por etapa (password_enviada=True desde el paso 3)."""
        if self.require_flag and not is_http_login_enabled():
            raise RuntimeError("ARCA_HTTP_LOGIN está deshabilitado (setear ARCA_HTTP_LOGIN=1 para la PoC).")

        cuit_clean = "".join(c for c in str(cuit or "") if c.isdigit())
        if len(cuit_clean) != 11:
            raise ValueError("CUIT inválido (debe tener 11 dígitos).")
        if servicio not in SERVICIOS_ARCA_HTTP:
            raise ValueError(f"Servicio desconocido '{servicio}'. Disponibles: {sorted(SERVICIOS_ARCA_HTTP)}")
        srv_cfg = SERVICIOS_ARCA_HTTP[servicio]

        password_enviada = False
        with self._new_client() as client:
            # --- Paso 1: GET login.xhtml -> ViewState ---
            try:
                r1 = client.get(LOGIN_URL)
                r1.raise_for_status()
            except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError) as exc:
                raise ArcaNoDisponible(f"ARCA no disponible en GET login.xhtml: {type(exc).__name__}") from exc

            vs1 = _extract_input_value(r1.text, "javax.faces.ViewState")
            if not vs1:
                raise ArcaNoDisponible("No se encontró javax.faces.ViewState en login.xhtml.")

            # --- Paso 2: POST F1:username + F1:btnSiguiente ---
            try:
                r2 = client.post(
                    LOGIN_URL,
                    data={
                        "F1": "F1",
                        "F1:username": cuit_clean,
                        "F1:btnSiguiente": "Siguiente",
                        "javax.faces.ViewState": vs1,
                    },
                )
                r2.raise_for_status()
            except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError) as exc:
                raise ArcaNoDisponible(f"ARCA no disponible en POST F1:username: {type(exc).__name__}") from exc

            vs2 = _extract_input_value(r2.text, "javax.faces.ViewState") or vs1

            # --- Paso 3: POST F1:password + F1:btnIngresar (a partir de acá password_enviada=True) ---
            password_enviada = True
            try:
                r3 = client.post(
                    LOGIN_URL,
                    data={
                        "F1": "F1",
                        "F1:password": clave,
                        "F1:btnIngresar": "Ingresar",
                        "javax.faces.ViewState": vs2,
                    },
                )
                r3.raise_for_status()
            except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError) as exc:
                raise LoginNoConfirmado(f"Timeout o error tras enviar contraseña en login.xhtml: {type(exc).__name__}") from exc

            # Verificar rechazo explícito (clave incorrecta, captcha, bloqueada, cambio obligatorio)
            _clasificar_rechazo_html(r3.text)

            # --- Paso 4: extraer jwt del form y POST portalcf.cloud.afip.gob.ar/portal/login ---
            jwt_val = _extract_input_value(r3.text, "jwt") or _extract_input_value(r3.text, "token")
            if not jwt_val:
                # Si todavía estamos en auth.afip sin jwt, no se confirmó el ingreso
                if "portalcf.cloud" not in str(r3.url).lower():
                    raise LoginNoConfirmado("Login enviado pero ARCA no devolvió formulario JWT ni redirigió a portalcf.")
            else:
                try:
                    r4 = client.post(PORTAL_LOGIN_URL, data={"jwt": jwt_val})
                    r4.raise_for_status()
                except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError) as exc:
                    raise LoginNoConfirmado(f"Error autenticando JWT en portalcf: {type(exc).__name__}") from exc

            # --- Paso 5: GET autorización del servicio -> token y sign ---
            auth_url = PORTAL_AUTH_URL_TPL.format(cuit=cuit_clean, servicio_id=srv_cfg["servicio_id"])
            try:
                r5 = client.get(auth_url)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                raise ArcaNoDisponible(f"Error pidiendo autorización del servicio '{servicio}': {type(exc).__name__}") from exc

            if r5.status_code in (401, 403, 404):
                raise ServicioNoAutorizadoError(
                    f"El CUIT {cuit_clean} no tiene autorizado el servicio '{servicio}' en Portal CF (HTTP {r5.status_code})."
                )
            try:
                r5.raise_for_status()
                auth_json = r5.json()
            except Exception as exc:
                raise ServicioNoAutorizadoError(f"Respuesta inválida de autorización para '{servicio}': {type(exc).__name__}") from exc

            srv_token = str(auth_json.get("token") or "").strip()
            srv_sign = str(auth_json.get("sign") or "").strip()
            if not srv_token or not srv_sign:
                raise ServicioNoAutorizadoError(f"Portal CF no devolvió token/sign para '{servicio}'.")

            # --- Paso 6: POST al servicio destino ---
            try:
                r6 = client.post(
                    srv_cfg["post_url"],
                    data={"token": srv_token, "sign": srv_sign},
                )
                r6.raise_for_status()
            except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError) as exc:
                raise ArcaNoDisponible(f"Error abriendo servicio '{servicio}': {type(exc).__name__}") from exc

            logger.info("[POC_HTTP] cuit=%s servicio=%s status=%s bytes=%s", cuit_clean, servicio, r6.status_code, len(r6.text))
            return {
                "ok": True,
                "cuit": cuit_clean,
                "servicio": servicio,
                "status_code": r6.status_code,
                "url_final": str(r6.url),
                "html": r6.text,
                "password_enviada": password_enviada,
                "fuente": "ARCA_HTTP_POC",
            }
