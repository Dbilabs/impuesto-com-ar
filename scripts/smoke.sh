#!/usr/bin/env bash
# Verifica un sitio publicado. Uso: bash scripts/smoke.sh https://impuestos.com.ar
URL="${1:?Uso: smoke.sh URL}"; URL="${URL%/}"; FAIL=0
ok() { printf "  \033[32m✓\033[0m %s\n" "$1"; }
ko() { printf "  \033[31m✗\033[0m %s\n" "$1"; FAIL=1; }
check() { local c; c=$(curl -s -o /dev/null -w "%{http_code}" "$URL$1"); [ "$c" = "$2" ] && ok "$1 → $c" || ko "$1 → $c (esperado $2)"; }

echo "Páginas"
for p in / /iva/ /iibb/ /ganancias/ /retenciones/ /empresas/ /diagnostico/ /iva/seguridad/; do check "$p" 200; done
check /esta-pagina-no-existe/ 404
echo "SEO / GEO"
for p in /robots.txt /sitemap.xml /llms.txt /llms-full.txt /og/default.png; do check "$p" 200; done
curl -s "$URL/" | grep -q 'application/ld+json' && ok "datos estructurados en la home" || ko "faltan datos estructurados"
curl -sI "$URL/" | grep -qi 'content-security-policy' && ok "cabeceras de seguridad" || ko "faltan cabeceras de seguridad (_headers)"
echo "APIs"
r=$(curl -s -X POST "$URL/api/lead" -H 'content-type: application/json' -d '{"perfil":"x"}'); echo "$r" | grep -q '"ok":false' && ok "/api/lead responde" || ko "/api/lead no responde: $r"
r=$(curl -s -X POST "$URL/api/iva/estado" -H 'content-type: application/json' -d '{"token":"prueba-inexistente-000000000000"}'); echo "$r" | grep -q 'Enlace inválido' && ok "/api/iva + base D1 responden" || ko "/api/iva/estado: $r (¿binding DB?)"
exit $FAIL
