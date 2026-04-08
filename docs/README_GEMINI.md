# 🤖 Bot de Ventas - Versión Gemini

Versión del bot que usa **Google Gemini** en lugar de OpenAI.

## 🆚 Diferencias con Versión OpenAI

| Aspecto | OpenAI (ChatGPT) | Google Gemini |
|---------|------------------|---------------|
| **Archivo** | `bot_sales/bot.py` | `bot_sales/bot_gemini.py` |
| **Cliente** | `chatgpt.py` | `gemini.py` |
| **CLI** | `cli.py` | `cli_gemini.py` |
| **API Key** | `OPENAI_API_KEY` | `GEMINI_API_KEY` |
| **Modelo** | `gpt-4` | `gemini-1.5-pro` |
| **Lógica de Negocio** | **✅ COMPARTIDA** | **✅ COMPARTIDA** |
| **Database** | **✅ COMPARTIDA** | **✅ COMPARTIDA** |
| **Catálogo** | **✅ COMPARTIDO** | **✅ COMPARTIDO** |

**Ventaja:** Podés usar el mismo catálogo, database y lógica de negocio con ambas IAs.

---

## 🚀 Setup Rápido

### 1. Instalar dependencias

```bash
pip install google-generativeai
```

### 2. Obtener API Key de Gemini

1. Ir a: https://aistudio.google.com/app/apikey
2. Crear API key
3. Copiar la key

### 3. Configurar

```bash
export GEMINI_API_KEY="tu-api-key-aqui"
```

### 4. Ejecutar

```bash
python bot_sales/connectors/cli_gemini.py
```

---

## 📂 Archivos Nuevos

```
bot_sales/
├── core/
│   └── gemini.py           # Cliente Gemini API  
├── bot_gemini.py           # Bot orquestador (Gemini)
└── connectors/
    └── cli_gemini.py       # CLI para Gemini
```

---

## 🎯 Testing

```bash
# Test rápido (modo mock, sin API key)
python bot_sales/connectors/cli_gemini.py

# Con API key real
export GEMINI_API_KEY="..."
python bot_sales/connectors/cli_gemini.py
```

---

## 💡 Ventajas de Gemini

- ✅ **Gratis** hasta 60 requests/minuto
- ✅ **Rápido** (especialmente gemini-1.5-flash)
- ✅ **Multimodal** (texto, imágenes, video)
- ✅ **Context window grande** (hasta 2M tokens en Pro)

---

## ⚙️ Configuración Avanzada

Editar `bot_sales/config.py`:

```python
# Gemini Configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-1.5-pro"  # o "gemini-1.5-flash"
```

**Modelos disponibles:**
- `gemini-1.5-pro` - Más inteligente, más caro
- `gemini-1.5-flash` - Más rápido, más barato

---

## 🔄 Comparar ambas versiones

Podés tener ambos bots corriendo:

```bash
# Terminal 1: OpenAI
export OPENAI_API_KEY="sk-..."
python bot_sales/connectors/cli.py

# Terminal 2: Gemini
export GEMINI_API_KEY="..."
python bot_sales/connectors/cli_gemini.py
```

Ambos usan el mismo catálogo y database!

---

## ⚠️ Limitaciones

- **Gratis:** 15 requests/minuto, 1M tokens/day
- **Paid:** 360 requests/minuto, 4M tokens/day

Ver pricing: https://ai.google.dev/pricing

---

## 🐛 Troubleshooting

**Error: "google-generativeai not installed"**
```bash
pip install google-generativeai
```

**Error: "Invalid API key"**
- Verificar que la key esté correcta
- Ir a https://aistudio.google.com/app/apikey

**Bot no responde**
- Verificar que `GEMINI_API_KEY` esté configurada
- El modo mock funciona sin API key

---

## 📊 Pricing Comparison

| Proveedor | Modelo | Input | Output |
|-----------|--------|-------|--------|
| **OpenAI** | GPT-4 | $0.03/1K | $0.06/1K |
| **Gemini** | Pro | **GRATIS** | **GRATIS** |
| **Gemini** | Flash | **GRATIS** | **GRATIS** |

(Límites free tier: 15 RPM, 1M tokens/día)

---

## ✅ Lo que se mantiene igual

- ✅ Catálogo de 62 productos
- ✅ 5 categorías (Herramienta, Sierra Circular, Lijadora Orbital, Destornillador a Bateria, PlayStation)
- ✅ Cross-selling (Herramienta → Destornillador a Bateria 10% OFF)
- ✅ Function calling
- ✅ Base de datos SQLite
- ✅ Todas las políticas

**Solo cambia el proveedor de IA!**
