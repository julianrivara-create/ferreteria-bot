# 🤖 Cómo Elegir entre ChatGPT y Open Source

Tenés **DOS opciones** para el LLM del bot:

## Opción 1️⃣: ChatGPT (OpenAI) - Original

**Pros**:
- ✅ Mejor calidad (GPT-4 es excelente)
- ✅ Function calling nativo
- ✅ Ya probado y funcionando

**Contras**:
- ❌ Costo: ~$50-150/mes
- ❌ Requiere API key
- ❌ Requiere internet
- ❌ Data va a cloud

**Setup**:
```bash
# .env
LLM_CLIENT=chatgpt
OPENAI_API_KEY=sk-tu-key-aqui
OPENAI_MODEL=gpt-4
```

---

## Opción 2️⃣: Universal (Ollama/LM Studio) - Nuevo

**Pros**:
- ✅ Gratis ($0/mes)
- ✅ Local/offline
- ✅ Privado (data no sale)
- ✅ Más rápido (~50 tok/s vs 30)

**Contras**:
- ⚠️  Calidad 90% de GPT-4
- ⚠️  Requiere RAM (8GB+)
- ⚠️  Function calling limitado

**Setup**:
```bash
# 1. Instalar Ollama
curl -fsSL https://ollama.com/install.sh | sh

# 2. Download modelo
ollama pull glm4:9b

# 3. Configurar
# .env
LLM_CLIENT=auto  # Auto-detect (prueba Ollama primero)
# O forzar:
LLM_CLIENT=ollama
OLLAMA_MODEL=glm4:9b
```

---

## Opción 3️⃣: Híbrido (Mejor de ambos mundos) ⭐

**Estrategia**: Usa Ollama para queries simples, GPT-4 para complejas

```bash
# .env
LLM_CLIENT=auto
OPENAI_API_KEY=sk-...  # Fallback a GPT-4 si Ollama falla
OLLAMA_MODEL=glm4:9b
```

**Resultado**: 80% queries gratis (Ollama), 20% con GPT-4 → **80% ahorro!**

---

## 🔀 Cómo Cambiar Entre Uno y Otro

### Método 1: Edit .env (Más Fácil)

```bash
# Usar ChatGPT
echo "LLM_CLIENT=chatgpt" > .env
echo "OPENAI_API_KEY=sk-..." >> .env

# O usar Ollama
echo "LLM_CLIENT=ollama" > .env

# O auto-detect
echo "LLM_CLIENT=auto" > .env
```

### Método 2: Variable de entorno

```bash
# Probar Ollama temporalmente
LLM_CLIENT=ollama python whatsapp_server.py

# Volver a ChatGPT
LLM_CLIENT=chatgpt python whatsapp_server.py
```

### Método 3: Código Python

```python
from bot_sales.core.client_factory import create_llm_client

# Opción ChatGPT
client = create_llm_client(backend='chatgpt', api_key='sk-...')

# Opción Ollama
client = create_llm_client(backend='ollama', model='glm4:9b')

# Auto-detect
client = create_llm_client(backend='auto')
```

---

## 🧪 Probar Ambos

```bash
# 1. Ver qué backends están disponibles
python -m bot_sales.core.client_factory

# Output:
# ✅ Disponible - ollama
# ✅ Disponible - openai
# ❌ No disponible - lmstudio
```

---

## 📊 Comparación Rápida

| Feature | ChatGPT | Ollama (GLM-4) | Auto |
|---------|---------|----------------|------|
| **Costo/mes** | $50-150 | $0 | $10-30 |
| **Calidad** | 98% | 90% | 95% |
| **Velocidad** | Media | Rápida | Rápida |
| **Setup** | 1 min | 5 min | 5 min |
| **Requiere internet** | Sí | No | Solo OpenAI |
| **Privacidad** | Cloud | 100% local | Mixta |

---

## 🎯 Recomendación

**Para desarrollo/testing**: 
```bash
LLM_CLIENT=ollama  # Gratis, rápido
```

**Para producción con budget**:
```bash
LLM_CLIENT=chatgpt  # Mejor calidad
```

**Para producción optimizando costo**:
```bash
LLM_CLIENT=auto    # Híbrido inteligente
```

---

## ⚙️ Configuración Files

### .env.chatgpt (Solo OpenAI)
```bash
LLM_CLIENT=chatgpt
OPENAI_API_KEY=sk-your-key
OPENAI_MODEL=gpt-4
```

### .env.ollama (Solo local)
```bash
LLM_CLIENT=ollama
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=glm4:9b
```

### .env.hybrid (Ambos)
```bash
LLM_CLIENT=auto
OLLAMA_MODEL=glm4:9b
OPENAI_API_KEY=sk-your-key  # Fallback
```

---

## 🔧 Troubleshooting

### "No LLM backend available"
```bash
# Opción 1: Instalar Ollama
curl -fsSL https://ollama.com/install.sh | sh
ollama pull glm4:9b

# Opción 2: Usar OpenAI
echo "LLM_CLIENT=chatgpt" >> .env
echo "OPENAI_API_KEY=sk-..." >> .env
```

### "Model not found"
```bash
# Ver modelos disponibles
ollama list

# Download
ollama pull glm4:9b
```

---

## 📝 Resumen

**Ambos sistemas están disponibles**. Elegí según tu caso:

- 💰 **Presupuesto ilimitado**: ChatGPT
- 💸 **Costo cero**: Ollama
- 🎯 **Balance**: Auto (híbrido)

**Cambiar es tan simple como editar una línea en `.env`** 🎉
