"""Configuración central del sitio. Cambiá acá y volvé a correr `python3 build.py`."""

# Dominio definitivo (sin barra final). Si impuestos.com.ar no está disponible, cambialo acá y nada más.
SITE_URL = "https://impuesto.com.ar"
SITE_NAME = "impuesto.com.ar"
SITE_TAGLINE = "Impuestos claros y el contador indicado para tu caso"
LOCALE = "es_AR"
LANG = "es-AR"

# Fecha de la última revisión editorial general (formato ISO).
UPDATED = "2026-11-23"
UPDATED_HUMAN = "23 de noviembre de 2026"

# Estudios aliados a los que se derivan consultas.
ALIADOS = []

# Profesional que revisa el contenido (E-E-A-T). Mientras esté en None, el sitio firma como
# "Equipo editorial" y NO publica datos de autor inventados. Completalo con datos reales:
# REVISOR = {
#     "nombre": "Nombre Apellido",
#     "titulo": "Contador Público (UBA)",
#     "matricula": "CPCECABA T° 000 F° 000",
#     "linkedin": "https://www.linkedin.com/in/...",
#     "bio": "Contador con 15 años de experiencia en impuestos para pymes.",
# }
REVISOR = None

# Contacto público (aparece en Quiénes somos y en el schema). Usá una casilla del dominio.
EMAIL_CONTACTO = "info@impuesto.com.ar"

# Plazo de respuesta que se promete al lead.
PLAZO_RESPUESTA = "1 día hábil"

# Analítica sin cookies (recomendado): token de Cloudflare Web Analytics. Vacío = desactivado.
CF_ANALYTICS_TOKEN = ""

# Verificación de Google Search Console por meta tag (opcional: con Cloudflare conviene verificar por DNS).
GOOGLE_SITE_VERIFICATION = "CqnmPejyQbi3L46aEja4R3UsO5b58FBlT1wth9qtWlI"
BING_SITE_VERIFICATION = ""

# Clave de IndexNow (Bing, Yandex, Seznam...). Se publica como archivo /<clave>.txt.
INDEXNOW_KEY = "7f3c9a1e5b2d4c8f9a0e6b1d3c5f7a9e"

# Redes / perfiles de la marca para "sameAs" (completar cuando existan).
SAME_AS = []

# Titular de la base de datos (Ley 25.326). Completar antes de publicar.
TITULAR = "[RAZÓN SOCIAL DEL TITULAR]"
CUIT = "[CUIT]"
