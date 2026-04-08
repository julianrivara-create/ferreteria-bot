# Quick Switch: LLM Configuration

## 🎯 Current Setup

Tenés **3 archivos .env** pre-configurados:

### 1. `.env.chatgpt` - Solo OpenAI
```bash
cp .env.chatgpt .env
# Editar OPENAI_API_KEY
```

### 2. `.env.ollama` - Solo Local (gratis)
```bash
cp .env.ollama .env
# Instalar: curl -fsSL https://ollama.com/install.sh | sh
# Download: ollama pull glm4:9b
```

### 3. `.env.hybrid` - Ambos (recomendado)
```bash
cp .env.hybrid .env
# Configurar ambas API keys
# Usa Ollama primero, fallback a OpenAI
```

---

## 🔀 Cambiar Rápido

```bash
# Probar con Ollama
ln -sf .env.ollama .env
python whatsapp_server.py

# Cambiar a ChatGPT
ln -sf .env.chatgpt .env
python whatsapp_server.py

# Usar híbrido
ln -sf .env.hybrid .env
python whatsapp_server.py
```

---

## 🧪 Ver Qué Está Disponible

```bash
python -m bot_sales.core.client_factory

# Output:
# ✅ Disponible - ollama
# ✅ Disponible - openai
# ✨ Recomendado usar: ollama
```

---

**Nota**: El código NO fue modificado. Solo agregamos nuevas opciones.
El `chatgpt.py` original sigue funcionando igual que siempre. 🎉
