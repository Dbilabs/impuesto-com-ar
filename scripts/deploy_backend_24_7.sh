#!/usr/bin/env bash
set -euo pipefail

# scripts/deploy_backend_24_7.sh
# Despliega el Motor Headless ARCA + Bóveda Cifrada 24/7 en Railway y conecta
# automáticamente BOT_API_URL y BOT_API_SECRET en Cloudflare Pages (impuesto.com.ar).

echo "🚀 1. Verificando sesión de Railway..."
if ! railway whoami >/dev/null 2>&1; then
  echo "🔐 Abrí el navegador para iniciar sesión en Railway:"
  railway login
fi

VAULT_KEY="${IMPUESTO_VAULT_KEY:-$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')}"
BOT_SECRET="${BOT_API_SECRET:-$(cat data/boveda/.bot_secret 2>/dev/null || python3 -c 'import secrets; print(secrets.token_urlsafe(32))')}"

echo "📦 2. Inicializando proyecto Railway (si no está vinculado aún)..."
if [ ! -f .railway/config.json ]; then
  railway init --name impuesto-arca-engine
fi

echo "🔑 3. Configurando variables seguras en Railway..."
railway variables --set "IMPUESTO_VAULT_KEY=${VAULT_KEY}" --set "BOT_API_SECRET=${BOT_SECRET}" --set "PUBLIC_BOT_URL=https://impuesto.com.ar"

echo "🐳 4. Desplegando contenedor Docker (Playwright Headless + FastAPI)..."
railway up --detach

echo "🌐 5. Generando/obteniendo dominio público HTTPS en Railway..."
RAILWAY_DOMAIN=$(railway domain 2>&1 | grep -Eo 'https://[a-zA-Z0-9.-]+' | head -n 1 || true)
if [ -z "$RAILWAY_DOMAIN" ]; then
  echo "⚠️ Copiá tu URL pública de Railway (https://xxx.up.railway.app) y pegala acá:"
  read -r RAILWAY_DOMAIN
fi

echo "☁️ 6. Conectando BOT_API_URL=${RAILWAY_DOMAIN} y BOT_API_SECRET en Cloudflare Pages..."
printf "%s" "$RAILWAY_DOMAIN" | npx wrangler pages secret put BOT_API_URL --project-name=impuesto
printf "%s" "$BOT_SECRET" | npx wrangler pages secret put BOT_API_SECRET --project-name=impuesto

echo "⚡ 7. Redesplegando Cloudflare Pages para activar el nuevo backend 24/7..."
npx wrangler pages deploy dist --project-name=impuesto --commit-dirty=true

echo ""
echo "✅ LISTO: impuesto.com.ar ahora corre 24/7 en la nube (${RAILWAY_DOMAIN}). Ya no necesitás dejar tu Mac prendida."
