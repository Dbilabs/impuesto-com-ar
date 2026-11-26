#!/usr/bin/env bash
# Publica impuestos.com.ar en Cloudflare Pages de punta a punta:
# login → build → proyecto → base D1 → secretos → deploy → prueba.
# Uso (desde la carpeta del proyecto):  bash scripts/deploy.sh
# Requisitos: Node 18+, Python 3, openssl. Se puede volver a correr: lo que ya existe no se rehace.
set -euo pipefail
cd "$(dirname "$0")/.."
PROJECT="${PROJECT:-impuesto}"
DB_NAME="impuesto-iva"
W="npx --yes wrangler@4"

paso() { printf "\n\033[1;32m▶ %s\033[0m\n" "$1"; }
aviso() { printf "\033[1;33m%s\033[0m\n" "$1"; }

paso "1/7 Cuenta de Cloudflare"
if ! $W whoami 2>/dev/null | grep -q "associated with"; then
  aviso "Se va a abrir el navegador para que inicies sesión en Cloudflare."
  $W login
fi

paso "2/7 Generando el sitio"
python3 build.py

paso "3/7 Proyecto de Cloudflare Pages ($PROJECT)"
$W pages project create "$PROJECT" --production-branch main 2>/dev/null && echo "Proyecto creado." || echo "El proyecto ya existe: sigo."

paso "4/7 Base de datos D1 del IVA automático"
if grep -q "REEMPLAZAR-CON-EL-ID-DE-D1" wrangler.toml; then
  OUT=$($W d1 create "$DB_NAME" 2>&1 || true)
  ID=$(echo "$OUT" | grep -oE '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' | head -1)
  if [ -z "$ID" ]; then
    ID=$($W d1 list --json 2>/dev/null | python3 -c "import sys,json; print(next((d['uuid'] for d in json.load(sys.stdin) if d['name']=='$DB_NAME'),''))")
  fi
  [ -z "$ID" ] && { echo "$OUT"; echo "No pude crear ni encontrar la base D1."; exit 1; }
  sed -i.bak "s/REEMPLAZAR-CON-EL-ID-DE-D1/$ID/" wrangler.toml && rm -f wrangler.toml.bak
  echo "Base D1: $ID (guardada en wrangler.toml)"
fi
$W d1 execute "$DB_NAME" --remote --file=schema.sql --yes >/dev/null && echo "Tablas listas."

paso "5/7 Secretos"
EXIST=$($W pages secret list --project-name "$PROJECT" 2>/dev/null || true)
put() { printf "%s" "$2" | $W pages secret put "$1" --project-name "$PROJECT" >/dev/null && echo "  ✓ $1"; }
if ! echo "$EXIST" | grep -q CRED_KEY; then
  KEY=$(openssl rand -base64 32)
  BK="$HOME/impuestos-CRED_KEY-RESPALDO.txt"
  printf "%s\n" "$KEY" > "$BK"; chmod 600 "$BK"
  put CRED_KEY "$KEY"
  aviso "  Respaldo de la llave de cifrado en $BK. Guardala en un lugar seguro (gestor de contraseñas) y borrá el archivo."
fi
for S in AFIPSDK_TOKEN SHEETS_WEBHOOK_URL SHEETS_SECRET; do
  if ! echo "$EXIST" | grep -q "$S"; then
    eval "V=\${$S:-}"
    if [ -z "$V" ] && [ "${NO_PROMPT:-0}" != "1" ]; then
      read -r -s -p "  $S (Enter para dejarlo para después): " V; echo
    fi
    [ -n "$V" ] && put "$S" "$V" || aviso "  $S pendiente: cargalo después con: $W pages secret put $S --project-name $PROJECT"
  fi
done

paso "6/7 Publicando"
DEPLOY=$($W pages deploy dist --project-name "$PROJECT" --branch main --commit-dirty=true 2>&1 | tee /dev/stderr)
URL=$(echo "$DEPLOY" | grep -oE 'https://[a-z0-9.-]+\.pages\.dev' | tail -1)
URL="${URL:-https://$PROJECT.pages.dev}"

paso "7/7 Prueba rápida"
sleep 5
bash scripts/smoke.sh "$URL" || true

cat <<EOF

Listo. Sitio publicado en: $URL

Faltan los pasos que necesitan tu cuenta (están en LANZAMIENTO.md):
  • Pages → $PROJECT → Custom domains → agregar impuestos.com.ar y www (cuando el dominio esté delegado a Cloudflare).
  • Security → Bots: desactivar "Block AI bots".
  • Google Search Console y Bing Webmaster Tools → enviar /sitemap.xml.
EOF
