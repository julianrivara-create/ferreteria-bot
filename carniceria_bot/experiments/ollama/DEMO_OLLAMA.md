# 🎬 Ollama Demo - Cómo Ejecutar

## Ejecutar Demo

```bash
# Ver todas las demos
python demo_ollama.py --all

# Solo conversación (principal)
python demo_ollama.py --conversation

# Ver backends disponibles
python demo_ollama.py --backends

# Ver info de modelos
python demo_ollama.py --models

# Modo interactivo (menú)
python demo_ollama.py
```

## Output Esperado

### Demo 1: Backends Disponibles
```
🔍 DEMO: Backends Disponibles
============================================================

┌─────────────────────────────────────────────────────────┐
│                    LLM Backends                         │
├──────────┬────────────────────┬───────────────────────┤
│ Backend  │ Estado             │ Notas                 │
├──────────┼────────────────────┼───────────────────────┤
│ OPENAI   │ ✅ Disponible      │ GPT-4                 │
│ OLLAMA   │ ❌ No disponible   │ Run: ollama serve     │
│ LMSTUDIO │ ❌ No disponible   │ LM Studio app         │
└──────────┴────────────────────┴───────────────────────┘

✨ Puedes usar: openai
```

### Demo 2: Conversación Simulada

```
💬 SIMULACIÓN DE CONVERSACIÓN
============================================================

Usuario: Hola, buenos días
⏳ Bot pensando...
Bot: ¡Hola! 👋 Bienvenido. ¿En qué puedo ayudarte hoy?
⚡ Respondió en 0.45s

Usuario: Estoy buscando un iPhone 15  
⏳ Bot pensando...
Bot: Perfecto! Tenemos varios modelos de iPhone 15 disponibles. 
¿Buscas alguna capacidad de almacenamiento específica?
⚡ Respondió en 0.52s

...

📊 Estadísticas:
  • Mensajes: 5
  • Modelo: glm4:9b
  • Backend: Ollama (local, gratis)
  • Costo: $0 💸
```

## Prerequisitos

### 1. Instalar Ollama (si aún no)

```bash
# Mac/Linux
curl -fsSL https://ollama.com/install.sh | sh

# Verificar
ollama --version
```

### 2. Descargar Modelo

```bash
# GLM-4 (recomendado para empezar)
ollama pull glm4:9b

# O Llama 3.1 (alternativa rápida)
ollama pull llama3.1:8b

# Ver modelos instalados
ollama list
```

### 3. Iniciar Servidor

```bash
# En una terminal separada
ollama serve

# O en background
ollama serve &

# Verificar que está corriendo
curl http://localhost:11434/api/tags
```

### 4. Ejecutar Demo

```bash
# Demo completo
python demo_ollama.py --all

# Solo conversación
python demo_ollama.py --conversation
```

## Troubleshooting

### "Ollama no está instalado"
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

### "Ollama no está corriendo"
```bash
# Iniciar servidor
ollama serve
```

### "No hay modelos instalados"
```bash
ollama pull glm4:9b
```

### Error de importación
```bash
# Instalar requests si falta
pip install requests
```

## Comparación Visual

Una vez ejecutado, verás:

- ✅ **Verde**: Backend disponible y listo
- ❌ **Rojo**: Backend no disponible
- ⚡ **Tiempos**: Response times en segundos
- 💸 **Costo**: $0 con Ollama

## Demo Video

Si querés grabar la demo:
```bash
# Con asciinema (opcional)
asciinema rec ollama_demo.cast
python demo_ollama.py --all
exit
```

---

**¡El demo muestra el bot funcionando 100% offline y gratis!** 🎉
