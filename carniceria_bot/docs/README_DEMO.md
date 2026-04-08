# 🎬 Cómo Grabar el Demo del Bot

## Opción 1: Demo Automático (RECOMENDADO para filmar)

```bash
cd /Users/julian/Desktop/iphone-bot-demo
python3 demo_automated.py
```

**Qué hace:** Ejecuta 3 conversaciones automáticas con delays naturales:
1. **Auto-advance** - Usuario da toda la info de una
2. **Upselling** - Muestra sugerencias de Pro/Max + Retiro
3. **Alternativas** - No-match → opciones + Cancel/Reset

**Perfecto para filmar** porque:
- ✅ Escribe automáticamente con efecto "typing"
- ✅ Delays entre mensajes (1.5 segundos)
- ✅ Muestra TODAS las features
- ✅ Dura ~2 minutos total

---

## Opción 2: Demo Manual

```bash
cd /Users/julian/Desktop/iphone-bot-demo
python3 demo_cli_offline.py
```

**Conversaciones sugeridas para filmar:**

### Conversación A: Todo en uno (Auto-advance)
```
15 Pro 256 Natural soy Pablo 1155667788 CABA Transfer
confirmar
```

### Conversación B: Upselling
```
hola
iphone 16
que tenes en stock?
[Bot muestra Pro/Max options]
256 azul
Maria 1122334455 Retiro Transfer
confirmar
```

### Conversación C: Alternativas
```
hola
16 pro 128 negro
[Bot muestra alternativas]
3
[selecciona opción]
Juan 1199887766 Interior MP
confirmar
```

---

## Tips para Grabar

1. **Pantalla completa** en terminal
2. **Fondo oscuro** (se ve más pro)
3. **Zoom 150%** para que se vea bien en video
4. **Graba horizontal** (landscape)
5. Usa el script automático para no tener errores

---

## Comandos Rápidos

```bash
# Limpiar y empezar de nuevo
rm -f iphone_store_utopia.db events.log

# Demo automático (para filmar)
python3 demo_automated.py

# Demo manual
python3 demo_cli_offline.py
```

---

## Archivos del Proyecto

- `demo_cli_offline.py` - Bot principal (V13 Final)
- `demo_automated.py` - Script de demo automático
- `catalog.csv` - 55 productos
- `policies.md` - Políticas de la tienda
