#!/usr/bin/env bash
set -euo pipefail

echo "⚡ Instalando Skill Pack oficial de impuesto.com.ar (5 skills ARCA + Double-Check)..."
SLUGS=(auditoria-deuda-real cierre-mensual-pyme estudio-contable-b2b ganancias-y-bbpp monotributo-y-recategorizacion onboarding-contador-de-cabecera)
TARGETS=()

[ -d "$HOME/.claude" ] && TARGETS+=("$HOME/.claude/skills")
[ -d "$HOME/.gemini/config" ] && TARGETS+=("$HOME/.gemini/config/skills")
[ -d "$HOME/.cursor" ] && TARGETS+=("$HOME/.cursor/skills")
[ -d "$HOME/.codex" ] && TARGETS+=("$HOME/.codex/skills")

if [ ${#TARGETS[@]} -eq 0 ]; then
  TARGETS=("$HOME/.claude/skills" "$HOME/.gemini/config/skills")
fi

for BASE in "${TARGETS[@]}"; do
  for SLUG in "${SLUGS[@]}"; do
    DIR="$BASE/impuesto-$SLUG"
    mkdir -p "$DIR"
    curl -fsSL "https://impuesto.com.ar/skills/$SLUG/SKILL.md" -o "$DIR/SKILL.md"
  done
  echo "✅ Instalado en: $BASE"
done

echo ""
echo "🎉 Listo. Conectá el MCP en tu asistente:"
echo "   • Claude:   https://claude.impuesto.com.ar"
echo "   • ChatGPT:  https://chatgpt.impuesto.com.ar"
echo "   • Gemini:   https://gemini.impuesto.com.ar"
echo "   • Copilot:  https://copilot.impuesto.com.ar"
