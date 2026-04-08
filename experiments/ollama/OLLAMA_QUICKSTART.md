# 🤖 Quick Start - Open Source LLMs

## Setup Ollama (5 minutos)

```bash
# 1. Instalar Ollama (Mac/Linux)
curl -fsSL https://ollama.com/install.sh | sh

# 2. Descargar modelo (elegir uno)
ollama pull glm4:9b          # GLM-4 (4.7GB) - Recomendado para empezar
ollama pull llama3.3:70b     # Llama (40GB) - Mejor calidad (requiere GPU)
ollama pull mistral:7b       # Mistral (4.1GB) - Más rápido
ollama pull qwen2.5:32b      # Qwen (18GB) - Multilingüe

# 3. Correr servidor
ollama serve  # Corre en http://localhost:11434

# 4. Test
ollama run glm4:9b "Hola, cómo estás?"
```

## Configurar Bot

```bash
# 1. Configurar backend
cp .env.ollama .env

# O manualmente:
echo "LLM_BACKEND=ollama" >> .env
echo "OLLAMA_MODEL=glm4:9b" >> .env

# 2. Usar el bot
python whatsapp_server.py
```

## Modelos Recomendados

| Modelo | Tamaño | Requisitos | Best For |
|--------|--------|------------|----------|
| **glm4:9b** | 4.7GB | 8GB RAM | General, multilingüe |
| **llama3.1:8b** | 4.7GB | 8GB RAM | Rápido, inglés |
| **mistral:7b** | 4.1GB | 6GB RAM | Ultra rápido |
| **qwen2.5:14b** | 9GB | 16GB RAM | Mejor español |
| **llama3.3:70b** | 40GB | GPU 24GB | Production |

## Testing

```python
# Test desde Python
from bot_sales.core.universal_llm import create_llm_client

# Auto-detect backend
client = create_llm_client()

# Send message
messages = [
    {"role": "user", "content": "Hola, busco un Taladro Percutor 13mm"}
]

response = client.send_message(messages)
print(response['content'])
```

## Verificar Backend

```python
# Check current backend
from bot_sales.core.llm_backend import LLMFactory

backends = LLMFactory.list_available_backends()
for name, available in backends:
    status = "✅" if available else "❌"
    print(f"{status} {name}")
```

## Troubleshooting

### Ollama no se conecta
```bash
# Verificar que Ollama está corriendo
curl http://localhost:11434/api/tags

# Si no responde, arrancar servidor:
ollama serve
```

### Modelo no encontrado
```bash
# Listar modelos instalados
ollama list

# Descargar modelo
ollama pull glm4:9b
```

### Performance lenta
```bash
# Usar modelo más chico
ollama pull mistral:7b

# O cuantizado (más rápido, menos calidad)
ollama pull llama3.1:8b-q4_0
```

## Beneficios vs OpenAI

| Feature | OpenAI GPT-4 | Ollama (GLM-4) |
|---------|--------------|----------------|
| **Costo** | $50-150/mes | $0 (gratis) |
| **Speed** | ~30 tok/s | ~50 tok/s |
| **Privacy** | Cloud (data sale) | Local (privado) |
| **Offline** | ❌ No | ✅ Sí |
| **Calidad** | 98% | 90% |

## Próximos Pasos

1. ✅ Instalar Ollama
2. ✅ Descargar modelo
3. ✅ Configurar .env
4. ✅ Probar bot
5. ⏸️ Fine-tune con tus datos (opcional)

---

🎉 **Listo! Bot funcionando sin API keys, gratis, offline**.
