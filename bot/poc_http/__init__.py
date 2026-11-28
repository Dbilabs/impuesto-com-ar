"""PoC Fase 3.2: login HTTP directo contra ARCA (detrás de ARCA_HTTP_LOGIN=1, apagado por defecto)."""
from .arca_http import (
    ArcaHttpClient,
    ServicioNoAutorizadoError,
    SERVICIOS_ARCA_HTTP,
    is_http_login_enabled,
    redactar_headers_y_payload,
)

__all__ = [
    "ArcaHttpClient",
    "ServicioNoAutorizadoError",
    "SERVICIOS_ARCA_HTTP",
    "is_http_login_enabled",
    "redactar_headers_y_payload",
]
