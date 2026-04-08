# 🎯 Resumen: Bot OpenAI vs Gemini

## 📁 Estructura del Proyecto

```
iphone-bot-demo/
├── 📱 CATÁLOGO Y DATA (COMPARTIDO)
│   ├── catalog_extended.csv       # 62 productos, 5 categorías
│   ├── policies.md                # Políticas de la tienda
│   └── iphone_store.db            # SQLite database (auto-creada)
│
├── 🤖 BOT VERSIÓN OPENAI (ChatGPT)
│   ├── bot_sales/bot.py           # Orquestador OpenAI
│   ├── bot_sales/core/chatgpt.py  # Cliente ChatGPT
│   └── bot_sales/connectors/cli.py
│
├── 🤖 BOT VERSIÓN GEMINI (Google AI)
│   ├── bot_sales/bot_gemini.py    # Orquestador Gemini
│   ├── bot_sales/core/gemini.py   # Cliente Gemini
│   └── bot_sales/connectors/cli_gemini.py
│
└── 🧠 LÓGICA COMPARTIDA (AMBOS BOTS)
    ├── bot_sales/core/database.py       # DB operations
    └── bot_sales/core/business_logic.py # Funciones de negocio
```

---

## ⚙️ Cómo Funcionan

### Versión OpenAI (ChatGPT)
```
Usuario → bot.py → chatgpt.py → GPT-4 → business_logic.py → database.py
                       ↓
                   API OpenAI ($$$)
```

### Versión Gemini (Google)
```
Usuario → bot_gemini.py → gemini.py → Gemini 1.5 Pro → business_logic.py → database.py
                              ↓
                         API Google (GRATIS*)
```

**Ambos comparten:** `business_logic.py`, `database.py`, `catalog_extended.csv`, `policies.md`

---

## 🚀 Cómo Ejecutar

### OpenAI (ChatGPT)
```bash
export OPENAI_API_KEY="sk-..."
python bot_sales/connectors/cli.py
```

### Gemini (Google)
```bash
export GEMINI_API_KEY="..."
python bot_sales/connectors/cli_gemini.py
```

---

## 💰 Comparación

| Aspecto | OpenAI (ChatGPT) | Google Gemini |
|---------|------------------|---------------|
| **Modelo** | GPT-4 | Gemini 1.5 Pro |
| **Costo** | $0.03-0.06 / 1K tokens | **Gratis** (15 RPM) |
| **Velocidad** | Normal | Rápido |
| **Context** | 128K tokens | 2M tokens |
| **Function Calling** | ✅ Sí | ✅ Sí |
| **Setup** | Tarjeta requerida | **Email gratis** |

---

## 🎯 Features Implementadas (AMBOS BOTS)

- ✅ **Multi-categoría** (iPhone, MacBook, iPad, AirPods, PlayStation)
- ✅ **Cross-selling** (iPhone → AirPods 10% OFF)
- ✅ **62 productos** en catálogo
- ✅ **9 funciones** callable (buscar_stock, confirmar_venta, etc.)
- ✅ **Reservas** de 30 minutos
- ✅ **Políticas** integradas en prompt
- ✅ **Modo mock** para testing sin API key

---

## 📖 Documentación

- `README.md` - Setup general y OpenAI
- `README_GEMINI.md` - Setup Gemini específico
- `README_DEMO_V2.md` - Demo automático

---

## 🧪 Testing

```bash
# Test setup sin API keys (modo mock)
python bot_sales/connectors/cli.py          # OpenAI mock
python bot_sales/connectors/cli_gemini.py   # Gemini mock

# Demo automático
python demo_automated_v2.py
```

---

## ✅ Próximos Pasos

1. **Elegir provider:**
   - OpenAI: Más conocido, más caro
   - Gemini: Gratis, más rápido

2. **Obtener API key:**
   - OpenAI: https://platform.openai.com/api-keys
   - Gemini: https://aistudio.google.com/app/apikey

3. **Configurar:**
   ```bash
   export GEMINI_API_KEY="..."  # o OPENAI_API_KEY
   ```

4. **Probar:**
   ```bash
   python bot_sales/connectors/cli_gemini.py
   ```

5. **Desplegar:**
   - Conectar a WhatsApp (usar template en `connectors/whatsapp.py`)
   - Web Chat (usar template en `connectors/webchat.py`)

---

## 🎉 Resultado

Ahora tenés:
- ✅ **2 bots** (OpenAI + Gemini) con la misma funcionalidad
- ✅ **Código compartido** (lógica de negocio)
- ✅ **Flexibilidad** para cambiar de provider
- ✅ **Testing** con modo mock
- ✅ **Production-ready**
