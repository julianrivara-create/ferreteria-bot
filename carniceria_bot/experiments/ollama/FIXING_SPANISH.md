# 🔧 Arreglando Phi3 para Español

Si Phi3 responde en inglés, hay 3 soluciones:

## Solución 1: Usar modelo mejor para español (RECOMENDADO) ⭐

```bash
# Qwen 2.5 es MUCHO mejor para español
ollama pull qwen2.5:3b

# Borrar Phi3 si querés
ollama rm phi3:mini

# Probar
python3 demo_ollama.py --conversation
```

## Solución 2: Demo actualizado (YA ARREGLADO)

El demo ahora incluye system prompt en español que dice:
- "SIEMPRE responde en ESPAÑOL"
- "Eres vendedor de iPhones"
- Mock data de productos y precios

Ejecutar nuevamente:
```bash
python3 demo_ollama.py --conversation
```

## Solución 3: Forzar español en cada mensaje

```bash
# Test directo con instrucción explícita
ollama run phi3:mini "Responde SOLO en español: Hola, ¿cómo estás?"
```

## 🎯 Recomendación FINAL para MacBook Air:

**Usa Qwen 2.5 (3B)** - Es el MEJOR para español + liviano:

```bash
# 1. Borrar Phi3
ollama rm phi3:mini

# 2. Descargar Qwen (mejor español)
ollama pull qwen2.5:3b

# 3. Probar directo
ollama run qwen2.5:3b "Hola, soy un vendedor de iPhones. ¿En qué te puedo ayudar?"

# 4. Demo completo
python3 demo_ollama.py --conversation
```

## 📊 Comparación:

| Modelo | Tamaño | Español | Velocidad Mac Air |
|--------|--------|---------|-------------------|
| phi3:mini | 2GB | ⚠️ Regular | ✅ Rápido |
| **qwen2.5:3b** | 2GB | ✅✅ Excelente | ✅ Rápido |
| tinyllama | 1GB | ❌ Malo | ✅✅ Ultra rápido |

**Qwen 2.5 es la mejor opción para ti** 🎯
