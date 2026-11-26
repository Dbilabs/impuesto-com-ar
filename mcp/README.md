# ARCA MCP Server (`impuesto-arca-mcp`)

Servidor de **Model Context Protocol (MCP)** desarrollado para **impuesto.com.ar**. Permite que asistentes de Inteligencia Artificial (**Claude Desktop, Cursor, ChatGPT, Antigravity**) se conecten directamente con **ARCA (AFIP)** para consultar comprobantes, estimar IVA, leer notificaciones oficiales y administrar empresas representadas.

---

## 🛠️ Herramientas Disponibles (MCP Tools)

### 1. `consultar_comprobantes_mes`
- **Descripción**: Consulta comprobantes emitidos y/o recibidos en ARCA (*Mis Comprobantes*) para un CUIT y período (`YYYY-MM`).
- **Devuelve**:
  - Débito Fiscal total (IVA Ventas).
  - Crédito Fiscal total (IVA Compras).
  - IVA Determinado preliminar a pagar.
  - Total de facturación de ventas y compras brutas.
  - Ranking de los 5 principales proveedores y clientes.
  - Listado de comprobantes detallados con fecha, emisor/receptor, alícuotas y CAE.

### 2. `leer_notificaciones_dfe`
- **Descripción**: Consulta la bandeja de comunicaciones en el **Domicilio Fiscal Electrónico (DFE)** para el CUIT solicitado o para todas las empresas representadas.
- **Utilidad**: Detección temprana de intimaciones, órdenes de intervención o avisos antes del vencimiento legal.

### 3. `listar_empresas`
- **Descripción**: Lista todas las personas físicas y jurídicas asociadas y autorizadas para operar bajo ese usuario en ARCA.

---

## 🚀 Instalación y Configuración

### 1. Requisitos
- Python 3.10 o superior.
- Google Chrome instalado (o Chromium de Playwright).
- Dependencias:
  ```bash
  pip install "mcp[cli]>=1.0.0" playwright
  playwright install chromium
  ```

---

### 2. Configuración en Claude Desktop

Edita el archivo de configuración de Claude Desktop:
- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

Agrega el servidor dentro de `mcpServers`:

```json
{
  "mcpServers": {
    "arca": {
      "command": "python3",
      "args": [
        "/Users/strat/Documents/IMPUESTO.COM.AR/mcp/server.py"
      ],
      "env": {
        "ARCA_CUIT": "TU_CUIT_OPERADOR",
        "ARCA_CLAVE": "TU_CLAVE_FISCAL"
      }
    }
  }
}
```

---

### 3. Configuración en Cursor / VS Code

En la raíz de tu proyecto o en tu configuración global de Cursor (`.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "arca": {
      "command": "python3",
      "args": ["/Users/strat/Documents/IMPUESTO.COM.AR/mcp/server.py"],
      "env": {
        "ARCA_CUIT": "TU_CUIT_OPERADOR",
        "ARCA_CLAVE": "TU_CLAVE_FISCAL"
      }
    }
  }
}
```

---

## 💬 Ejemplos de Prompts para la IA

Una vez conectado el MCP, podés hablarle a Claude o Cursor en lenguaje natural:

- *"¿Cuánto IVA tenemos acumulado para pagar en Distribuidora Andina S.R.L. este mes?"*
- *"Revisá el Domicilio Fiscal Electrónico de todas mis empresas y decime si llegó alguna notificación urgente."*
- *"Listame las empresas que represento en ARCA y mostrame los 5 principales proveedores a los que les compramos este mes."*
