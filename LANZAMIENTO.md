# impuestos.com.ar: guía de lanzamiento

Tiempo estimado: 2 a 3 horas, más la espera del dominio en NIC Argentina.

---

## Atajo: publicar con un solo comando

Con Node 18+ y Python 3 instalados, desde la carpeta del proyecto:

```
bash scripts/deploy.sh
```

El script hace todo esto solo:

1. Abre el navegador para que inicies sesión en Cloudflare.
2. Genera el sitio.
3. Crea el proyecto de Pages y la base D1 con sus tablas.
4. Genera la llave de cifrado, guarda un respaldo y la carga como secreto.
5. Te pide los tokens de Afip SDK y de Google Sheets.
6. Publica el sitio.
7. Corre una prueba de punta a punta (`scripts/smoke.sh`).

Lo que no puede hacer por vos: registrar el dominio, crear las cuentas y conectar el dominio propio en Cloudflare (pasos 1 y 3.4 a 3.6 de esta guía).

---

## 0. Antes de publicar (obligatorio)

Completá estos datos en `src/config.py` y volvé a correr `python3 build.py`:

| Dato | Para qué | Dónde |
|---|---|---|
| `ALIADOS` | Confirmá por escrito el acuerdo de referidos con Auren y Calim (comisión, atribución, plazo de contacto). Hasta que lo tengas, no publiques sus nombres. | `config.py` |
| `REVISOR` | Nombre, matrícula y LinkedIn de un contador real que revise el contenido. **Es lo que más pesa para posicionar en temas de impuestos (E-E-A-T).** | `config.py` |
| `TITULAR` / `CUIT` | Responsable de la base de datos (Ley 25.326). | `config.py` |
| N° de registro AAIP | Inscribí la base "Leads" en el Registro Nacional de Bases de Datos (AAIP) y poné el número en la política de privacidad. | `src/pages/general.py`, buscá `[N° DE REGISTRO]` |
| `EMAIL_CONTACTO` | Una casilla del dominio (gratis con Cloudflare Email Routing). | `config.py` |

---

## 1. Registrar el dominio (NIC Argentina)

1. Entrá a **nic.ar** con tu clave fiscal (o la de la empresa titular) y buscá `impuestos.com.ar`.
2. Si está libre, registralo a nombre del titular definitivo, no a título personal si va a ser de una sociedad.
3. **Si está tomado:** buscá alternativas (`tusimpuestos.com.ar`, `impuestosclaros.com.ar`, `segundaopinionimpositiva.com.ar`) o consultá si el titular lo vende. Cambiá `SITE_URL` en `config.py` y listo: el sitio se regenera con el dominio nuevo.

---

## 2. Planilla de leads (Google Sheets)

1. Creá una planilla nueva: "Leads impuestos.com.ar".
2. Extensiones → Apps Script → pegá `integraciones/google-sheets-apps-script.gs`.
3. Cambiá `SECRET` por una clave larga. Opcional: poné tu email en `NOTIFICAR` para recibir un aviso por cada lead.
4. Implementar → Nueva implementación → **Aplicación web** → Ejecutar como: *Yo* → Acceso: *Cualquier usuario*.
5. Guardá la URL que termina en `/exec`.

Cada lead llega con: destino sugerido (**Auren** o **Calim**), puntaje de 0 a 100, tema, tamaño, facturación, provincia, página de origen y UTMs. La columna `estado` es para tu seguimiento (Nuevo → Derivado → Reunión → Cerrado). Así podés cobrar la comisión con trazabilidad.

**Regla de ruteo** (editable en `functions/api/lead.js`, función `rutear`):
- Empresa con 11 o más empleados, o facturación desde $500 millones, o tema de auditoría o precios de transferencia → **Auren**
- Responsable inscripto que factura más de $500 millones por año → **Auren**
- Resto de responsables inscriptos, monotributistas y empresas chicas → **Calim**

---

## 3. Publicar en Cloudflare Pages

1. Creá una cuenta en **cloudflare.com** → *Add a site* → `impuestos.com.ar` (plan Free).
2. Cloudflare te da 2 nameservers. En **nic.ar** → tu dominio → *Delegaciones* → reemplazá los DNS por esos 2. La propagación puede tardar unas horas.
3. Subí el proyecto a un repositorio privado de GitHub. En Cloudflare: **Workers & Pages → Create → Pages → Connect to Git**.
   - Build command: `python3 build.py`
   - Build output directory: `dist`
   - Variables de entorno (Production): `SHEETS_WEBHOOK_URL` (la URL `/exec`) y `SHEETS_SECRET` (la misma clave del paso 2).
   - **Servicio de IVA automático:** creá la base D1, cargá `CRED_KEY` y `AFIPSDK_TOKEN` y verificá el binding `DB`. El paso a paso está en **SERVICIO-IVA.md**.
   - *Alternativa sin GitHub:* `npx wrangler pages deploy dist --project-name impuestos`, corrido desde la carpeta raíz del proyecto para que incluya `functions/`.
4. En el proyecto de Pages → **Custom domains** → agregá `impuestos.com.ar` y `www.impuestos.com.ar`.
5. Redirigí `www` a la versión sin www: Rules → Redirect Rules → "Redirect from WWW to root" (plantilla), con código 301.
   **Subdominios `iva.`, `iibb.`, `ganancias.` y `retenciones.impuestos.com.ar`:** para cada uno, creá un registro DNS proxied (CNAME al dominio) y una Redirect Rule 301 hacia su sección: `/iva/`, `/iibb/`, `/ganancias/` y `/retenciones/`. Son direcciones fáciles para campañas y tarjetas, mientras el contenido vive en el dominio principal y suma autoridad SEO en un solo lugar. El panel privado ya funciona en `/iva/mi-cuenta/`.
6. Configuración de Cloudflare:
   - SSL/TLS → **Full (strict)**. Edge Certificates → **Always Use HTTPS**: activado.
   - Caching → Configuration → **Crawler Hints: activado**. Avisa a Bing y otros buscadores vía IndexNow cada vez que cambia algo.
   - ⚠️ **Security → Bots / AI Crawl Control:** asegurate de que **"Block AI bots" esté DESACTIVADO** y de que **no** esté activo el *Managed robots.txt*. Cloudflare bloquea los crawlers de IA por defecto en dominios nuevos, y eso te deja afuera de ChatGPT, Claude y Perplexity: **mata el GEO**.
   - Analytics → **Web Analytics** → agregá el sitio y pegá el token en `CF_ANALYTICS_TOKEN`. No usa cookies, así que no necesitás banner.
   - Email → **Email Routing** → creá `hola@impuestos.com.ar` y reenviala a tu casilla.
7. **Probá el formulario en producción** con un lead de prueba y verificá que llegue a la planilla.

---

## 4. Google Search Console

1. Entrá a **search.google.com/search-console** → *Agregar propiedad* → **Dominio** → `impuestos.com.ar`.
2. Verificación por DNS: Google te da un registro TXT. Con Cloudflare, el botón "Verificar automáticamente" lo carga solo; si no, agregalo en DNS → Records → TXT.
3. **Sitemaps** → enviá `https://impuestos.com.ar/sitemap.xml`.
4. **Inspección de URLs** → pedí la indexación de estas páginas, en este orden:
   `/`, `/iva/`, `/empresas/`, `/responsables-inscriptos/`, `/empresas/saldos-a-favor/`, `/empresas/auditoria-de-estados-contables/`, `/empresas/fiscalizacion-arca/`.
5. A los 7 días revisá *Páginas* (indexación) y *Mejoras* (breadcrumbs y datos estructurados).
6. Validá los datos estructurados de 2 o 3 páginas en **search.google.com/test/rich-results**.

## 5. Bing Webmaster Tools (importa para ChatGPT y Copilot)

1. **bing.com/webmasters** → *Importar desde Google Search Console*: trae la propiedad y el sitemap en un clic.
2. Después de cada publicación importante: `python3 scripts/indexnow.py`. Avisa a Bing al instante; Crawler Hints de Cloudflare también lo hace automáticamente.

---

## 6. Qué ya trae el sitio (SEO + GEO técnico)

- HTML estático, CSS inline y un solo JS de 12 KB diferido: Core Web Vitals en verde sin hacer nada.
- `title`, `description`, canonical, hreflang `es-AR`, Open Graph y Twitter Card en cada página.
- Schema.org en `@graph`: Organization, WebSite, Article (con `dateModified` y `reviewedBy` cuando cargás el revisor), BreadcrumbList, FAQPage, WebApplication (las calculadoras), Dataset (la tabla del monotributo) y DefinedTermSet (el glosario).
- Servicio de **IVA automático**: el cliente conecta su CUIT y un robot consulta ARCA (ver SERVICIO-IVA.md).
- Un bloque **"Respuesta rápida"** al principio de cada guía: 40 a 80 palabras con la cifra y la fecha de vigencia. Es el formato que más citan los motores de IA y los AI Overviews.
- Fechas de actualización visibles, fuentes oficiales al pie, byline editorial y páginas de confianza (metodología, cómo nos financiamos).
- `robots.txt` que habilita explícitamente a Googlebot, Bingbot, GPTBot, OAI-SearchBot, ClaudeBot, PerplexityBot, Google-Extended y otros.
- `llms.txt` (índice para modelos de IA) y `llms-full.txt` (todo el contenido en texto plano).
- `sitemap.xml` con `lastmod`, clave de IndexNow, 404 personalizada, redirecciones 301 y cabeceras de seguridad y caché.
- Enlazado interno: hubs → guías → herramientas → diagnóstico, migas de pan, "Seguí leyendo" y un índice en cada guía.

---

## 7. Plan de 90 días

**Semanas 1-2: indexación y autoridad**
- Publicar, indexar y cargar el revisor.
- Crear el perfil de LinkedIn de la marca y sumarlo a `SAME_AS`.
- Conseguir los primeros 5 a 10 enlaces: perfiles de los aliados ("socios" o "prensa"), directorios de pymes, cámaras empresarias y la red de ARNx.

**Semanas 3-8: contenido nuevo** (1 a 2 guías por semana, foco en responsables inscriptos y empresas)
- IVA: saldo técnico vs. libre disponibilidad, certificado de exclusión de retenciones y percepciones, IVA Simple paso a paso, crédito fiscal de bienes de uso.
- Ganancias sociedades: reducción de anticipos, gastos deducibles, ajuste por inflación.
- **Programático:** Ingresos Brutos por provincia (24 páginas con alícuotas, agente de recaudación y padrón) y vencimientos de IVA por terminación de CUIT.
- Empresas: auditoría bajo NIIF para filiales, due diligence fiscal, planificación de dividendos.
- Monotributo, solo como puerta de entrada al pase a responsable inscripto.

**Semanas 4-12: GEO y distribución**
- Cada mes, probá 20 preguntas en ChatGPT, Perplexity, Gemini y Google (AI Overviews), por ejemplo "¿cuánto se paga de monotributo?" o "¿qué estudio contable me conviene para una pyme?". Anotá si citan el sitio. Tenés HubSpot conectado, que trae una herramienta de AEO para medir esto.
- Respondé preguntas reales en Reddit (r/merval, r/argentina, r/devsarg para freelancers) y en LinkedIn, con enlace solo cuando aporta.
- Webinars con Auren sobre novedades para empresas. Cada uno se graba y se convierte en una guía.
- **Dato propio:** un relevamiento trimestral anonimizado a partir de los leads ("qué preocupa a las pymes en impuestos"). Los datos originales son lo que más citas genera.

**Mantenimiento fijo**
- **Antes de publicar:** reemplazá `src/static/assets/vendor/xlsx-0.18.5.min.js` por la versión 0.20.3 de SheetJS (cdn.sheetjs.com). La 0.18.5 de npm tiene vulnerabilidades conocidas al leer archivos manipulados; el riesgo es bajo porque solo procesa archivos del propio usuario en su navegador, pero conviene actualizarla. Ajustá el nombre en `src/assets/iva.js`.
- **Febrero y agosto:** actualizar `src/data/monotributo.json` con la nueva tabla de ARCA, `UPDATED` en `config.py`, rebuild y `indexnow.py`.
- **Calendario comercial:** monotributo en enero y julio (recategorización); auditoría de **septiembre a noviembre** (antes del cierre de diciembre); Ganancias y Bienes Personales en mayo y junio.

---

## 8. Cómo editar

- Textos: `src/pages/personas.py`, `src/pages/empresas.py`, `src/pages/general.py`. Cada página es un diccionario con `title`, `description`, `answer`, `body`, `faqs` y `sources`.
- Estilos: `src/assets/style.css`. Comportamiento (embudo y calculadoras): `src/assets/app.js`.
- Regenerar: `python3 build.py`. Imágenes de redes: `python3 scripts/images.py` (requiere Playwright).
