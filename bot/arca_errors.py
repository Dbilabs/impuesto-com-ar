"""
bot/arca_errors.py
Excepciones tipadas por etapa del login en ARCA (cierre N1-h).

Clasificación por etapa (no por texto genérico):
  - ArcaNoDisponible: fallo/timeout ANTES de enviar la contraseña (F1:btnIngresar).
    No descuenta presupuesto de fallos ni activa el circuit breaker de clave incorrecta.
  - LoginNoConfirmado: fallo/timeout DESPUÉS de enviar la contraseña sin llegar a portalcf.
    Descuenta presupuesto, pero para un owner validado NO activa el circuit breaker
    de 'CLAVE_FISCAL_INCORRECTA' y reporta estado LOGIN_NO_CONFIRMADO.
  - ClaveIncorrecta: ARCA rechazó explícitamente las credenciales (clave incorrecta,
    bloqueada, cambio obligatorio o captcha). Descuenta presupuesto y activa circuit breaker.
"""


class ArcaLoginError(RuntimeError):
    """Base para errores de login o disponibilidad de ARCA."""


class ArcaNoDisponible(ArcaLoginError):
    """Error o timeout ocurrido ANTES de enviar la contraseña (F1:btnIngresar)."""


class LoginNoConfirmado(ArcaLoginError):
    """Error o timeout ocurrido DESPUÉS de enviar la contraseña sin confirmar ingreso a portalcf."""


class ClaveIncorrecta(ArcaLoginError):
    """ARCA rechazó explícitamente la Clave Fiscal o exigió verificación/cambio."""

    def __init__(
        self,
        message: str,
        *,
        bloqueada: bool = False,
        cambio_clave: bool = False,
        captcha: bool = False,
    ) -> None:
        super().__init__(message)
        self.bloqueada = bloqueada
        self.cambio_clave = cambio_clave
        self.captcha = captcha
