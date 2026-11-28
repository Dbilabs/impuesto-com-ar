# impuesto.com.ar — Plataforma Contable Agéntica para ARCA (Argentina)

Servidor **Model Context Protocol (MCP v2.5.0)** con **50 herramientas fiscales**, **6 Skill Packs oficiales** sincronizados desde una única fuente de verdad (`skills-pack/`), motor híbrido ARCA (**Web Services oficiales WSFEv1/WSAA/Padrón A5 + Playwright Headless**) y **Bóveda Cifrada AES-256** para operar con **Claude, ChatGPT, Google Gemini, Microsoft Copilot, Cursor y Perplexity**.

---

## Endpoints MCP en Producción (8 subdominios)

| Asistente | URL MCP (Streamable HTTP / SSE) |
| :--- | :--- |
| **Claude** | `https://claude.impuesto.com.ar` |
| **ChatGPT** (`Complementos → Agregar → MCP → HTTP secuenciable`) | `https://chatgpt.impuesto.com.ar` |
| **Google Gemini / Antigravity** | `https://gemini.impuesto.com.ar` |
| **Microsoft Copilot** | `https://copilot.impuesto.com.ar` |
| **Cursor IDE** | `https://cursor.impuesto.com.ar` |
| **Perplexity** | `https://perplexity.impuesto.com.ar` |
| **Universal MCP** | `https://mcp.impuesto.com.ar` |
| **API / Integraciones** | `https://api.impuesto.com.ar` |

- **Hub de Skills Oficiales:** `https://impuesto.com.ar/skills/`
- **Instalador 1-línea (Claude Code / Gemini / Antigravity / Cursor / Codex):** `curl -fsSL https://impuesto.com.ar/skills/install.sh | bash`
- **Vinculación segura (Bóveda AES-256 / WSAA):** `https://impuesto.com.ar/vincular`

---

## Arquitectura del Repositorio

```
IMPUESTO.COM.AR/
├── functions/
│   ├── _middleware.js                # Enrutamiento de los 8 subdominios MCP
│   ├── mcp/
│   │   ├── [[path]].js               # Servidor MCP v2.5.0 (50 tools, 5 prompts, 6 resources, instructions)
│   │   └── skills_bundle.js          # Auto-generado desde skills-pack/ por scripts/sync_skills.py
│   ├── vincular.js                   # Proxy oficial https://impuesto.com.ar/vincular -> BOT_API_URL
│   └── api/v1/vincular/[[path]].js   # Proxy cifrado hacia la bóveda del backend
├── skills-pack/                      # ÚNICA FUENTE DE VERDAD de los 6 Skill Packs (SKILL.md)
│   ├── onboarding-contador-de-cabecera/
│   ├── auditoria-deuda-real/
│   ├── monotributo-y-recategorizacion/
│   ├── cierre-mensual-pyme/
│   ├── ganancias-y-bbpp/
│   └── estudio-contable-b2b/
├── bot/                              # Microservicio Backend Headless (FastAPI + Playwright + WSAA)
│   ├── main.py                       # API FastAPI (/api/v1/mcp/tool, /vincular, /health)
│   ├── boveda_segura.py              # Bóveda cifrada Fernet (AES + HMAC-SHA256)
│   ├── auditoria_unificada.py        # Auditoría 360° headless en 1 sola sesión ARCA
│   ├── doublecheck_arca.py           # Motor anti-falsos negativos y Sello de Verificación
│   ├── playbooks_servicios.py        # Protocolo Pre-Flight (7 pasos) y playbooks ARCA/AGIP/ARBA/SIFERE
│   ├── arca_ws.py                    # Web Services oficiales ARCA (WSAA, WSFEv1, Padrón A5, CSR)
│   ├── scraper*.py                   # Scrapers verificados (CCMA, BBPP F.762, Comprobantes, DFE, MiPyME)
│   ├── estudio_contable.py           # Modo Estudio Contable B2B (cartera, alertas >30%, Marca Blanca)
│   └── Dockerfile                    # Listo para Oracle Cloud (OCI) / Docker / Fly.io
├── mcp/server.py                     # Servidor FastMCP Python local equivalente
├── scripts/sync_skills.py            # Compila skills-pack/ -> skills_bundle.js + dist/skills/
└── src/ & dist/                      # Sitio estático Cloudflare Pages (landing + /estudios/ + /skills/)
```

---

## Cómo contribuir y desplegar cambios

### 1. Actualizar Skills (impacta automáticamente en los 8 MCP + `/skills/`)
```bash
# 1. Editá cualquier archivo en skills-pack/<slug>/SKILL.md
# 2. Compilá la única fuente de verdad:
python3 scripts/sync_skills.py
# 3. Desplegá a Cloudflare Pages:
npx wrangler pages deploy dist --project-name=impuesto
```

### 2. Correr el Backend Headless ARCA en local o en la nube (Oracle Cloud OCI / Docker)
```bash
pip install -r bot/requirements.txt
playwright install chromium
# Para correr en desarrollo local (relaja secretos obligatorios de producción):
export IMPUESTO_ENV=development
export PUBLIC_BOT_URL="https://impuesto.com.ar"
uvicorn bot.main:app --host 0.0.0.0 --port 8000
```
En Docker sobre Oracle Cloud (OCI), montar siempre volumen persistente para `/app/data/boveda` (bóveda, presupuesto de logins, idempotencia WSFE y tickets WSAA):
```bash
docker run -d --restart unless-stopped -p 8000:8000 \
  -v /var/lib/impuesto/boveda:/app/data/boveda \
  -e ORACLE_CLOUD=1 -e IMPUESTO_VAULT_KEY=... -e BOT_API_SECRET=... \
  --name impuesto-arca-engine impuesto-arca-engine
```
Luego en Cloudflare Pages (`impuesto` → Settings → Environment variables):
- `BOT_API_URL = https://bot.impuesto.com.ar` (tu VM Oracle Cloud detrás de Cloudflare Tunnel / HTTPS)
- `BOT_API_SECRET = <el-mismo-secreto>`

### 3. Reglas de Seguridad y Diseño Obligatorias
- **Cero secretos en Git:** `data/boveda/`, `.env*`, `*.key`, `*.pem`, `*.enc` están bloqueados por `.gitignore`.
- **Prohibición de falsos negativos (Double-Check):** Ninguna herramienta ni prompt puede afirmar *"Deuda $0"* o *"Al día"* mirando una sola pantalla de ARCA sin cruzar CCMA + Mis Facilidades + SCT + Monotributo.
- **Modo Solo Lectura por defecto:** Ninguna emisión de factura, DDJJ o plan se ejecuta sin `confirmado=true`.
