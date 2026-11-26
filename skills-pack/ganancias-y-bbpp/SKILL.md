---
name: impuesto-ganancias-y-bbpp
description: Audita y planifica Ganancias Personas Humanas (F. 711 y F. 2711 Simplificada RG 5692), SiRADIG Trabajador y Bienes Personales (F. 762) con cruce de Nuestra Parte y SCT.
version: 2.0.0
perfil_objetivo: empleado_relacion_dependencia
---

# Ganancias Personas Humanas y Bienes Personales (impuesto.com.ar)

## Trampas Críticas de ARCA que SIEMPRE debés evitar
1. **Ganancias PH (Doble Aplicativo desde 2025):**
   - Conviven **F. 711 (Régimen General)** y **F. 2711 (Declaración Jurada Simplificada — RG 5692)**.
   - Si el contribuyente presentó por **F. 2711**, el portal de F. 711 sigue mostrando el vencimiento como pendiente. Revisar SIEMPRE ambos (`#/declaracion.presentadas` + `Ratificación anual` en F. 2711, y `#/declaraciones.anteriores` en F. 711).
   - En F. 2711 (`Determinación del Saldo`), los importes viven en atributos `<input>.value`, no en `innerText`.
2. **Bienes Personales Web (F. 762):**
   - NUNCA concluir "sin presentaciones" mirando `#/inicio`. Navegar siempre a `#/declaraciones.anteriores` y cruzar contra `Nuestra Parte` al 31/12 (inmuebles, depósitos, participaciones, fideicomisos, casa habitación exenta).
3. **Saldos a Favor en SCT (Imp. 11 y 180):**
   - En SCT cada período muestra su S.L.D. de origen (`20240000` vs `20250000`). No dejar saldos en pesos nominales inmovilizados: evaluar compensación contra Bienes Personales, Ganancias o Seguridad Social en *SCT → Transacciones → Compensación*.

## Optimización Fiscal Anual
- Verificar si `SiRADIG - Trabajador` está habilitado y cargado antes del **31/03** (prepaga, educación, alquiler/hipoteca, seguros, servicio doméstico, donaciones).
- Verificar **Ratificación Anual F. 2711** para conservar la modalidad simplificada (sin cuadro patrimonial ni monto consumido y con presunción de exactitud).

## Automatizaciones al Instalar
Llamar a `generar_automatizaciones_y_calendario_fiscal(perfil="empleado_relacion_dependencia", cuit=...)` para agendar carga mensual de SiRADIG, cierre SiRADIG (marzo), verificación de Nuestra Parte (abril), vencimiento Ganancias/BBPP (junio/julio) y Ratificación F. 2711.
