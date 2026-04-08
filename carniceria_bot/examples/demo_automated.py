#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
DEMO PRO - 3 conversaciones automáticas (sin manos)
- Sincroniza por "prompts" del bot (patrones) en vez de enviar por silencio.
- Pausa fija: 2s entre turnos.
- Conversas diseñadas para verse humanas y alineadas al flujo real del bot.
"""

import subprocess
import time
import sys
import os
import threading
import queue
import re

PAUSE_SECONDS = 2.0
BOT_START_CMD = ['python3', '-u', 'demo_cli_offline.py']

class C:
    BOT = '\033[92m'
    USER = '\033[96m'
    BOLD = '\033[1m'
    GREY = '\033[90m'
    END = '\033[0m'

def type_print(text, delay=0.02):
    """Effect of typing"""
    sys.stdout.write(C.USER + "Vos: " + C.END)
    sys.stdout.flush()
    for char in text:
        sys.stdout.write(char)
        sys.stdout.flush()
        time.sleep(delay)
    print()

def read_output(process, q):
    """Reads stdout from process and puts lines in queue"""
    try:
        # Iteramos sobre el stream binario
        for line_bytes in iter(process.stdout.readline, b''):
            line = line_bytes.decode('utf-8', errors='replace')
            q.put(line)
    except Exception:
        pass
    finally:
        process.stdout.close()

def print_bot_line(line: str):
    # Fix: Remove "Vos:" prompt if it got attached to the line
    # The prompt might contain color codes, so we look for "Vos:" specifically
    if "Vos:" in line:
        line = line.split("Vos:")[-1]
    
    s = line.rstrip("\n")
    if not s.strip():
        return
    # Normalizamos colores
    if "Bot:" in s:
        # Sometimes the prompt echo leaves artifacts, clean up 
        s = s.strip()
        print(f"{C.BOT}{s}{C.END}")
    else:
        print(f"{C.GREY}{s}{C.END}")

def wait_for(proc, q, patterns, timeout=45):
    """
    Espera hasta que aparezca en stdout una línea que matchee alguno de los patrones.
    Mientras espera, imprime todo lo que salga del bot.
    patterns: list[str] regex
    """
    start = time.time()
    compiled = [re.compile(p, re.IGNORECASE) for p in patterns]

    while proc.poll() is None:
        if time.time() - start > timeout:
            raise TimeoutError(f"Timeout esperando patrones: {patterns}")

        try:
            line = q.get(timeout=0.2)

            # Filtramos eco "Vos:" si aparece (por seguridad)
            print_bot_line(line)

            for rx in compiled:
                if rx.search(line):
                    return line

        except queue.Empty:
            continue

    raise RuntimeError("El proceso del bot terminó antes de encontrar el patrón esperado.")

def send_user(proc, text, typing_delay=0.02):
    time.sleep(PAUSE_SECONDS)
    type_print(text, delay=typing_delay)
    # Enviar como bytes
    proc.stdin.write(text.encode('utf-8') + b"\n")
    proc.stdin.flush()
    time.sleep(PAUSE_SECONDS)

def run_one_demo(title, steps):
    print(f"\n{C.BOLD}{'='*60}{C.END}")
    print(f"{C.BOLD}{title}{C.END}")
    print(f"{C.BOLD}{'='*60}{C.END}\n")
    time.sleep(PAUSE_SECONDS)

    proc = subprocess.Popen(
        BOT_START_CMD,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=False,      # BINARY MODE
        bufsize=0        # UNBUFFERED
    )

    q = queue.Queue()
    t = threading.Thread(target=read_output, args=(proc, q), daemon=True)
    t.start()

    # Espera a que el bot esté listo (System message)
    # Dejamos que el paso 1 capture el saludo del bot
    wait_for(proc, q, patterns=[
        r"Loaded \d+ products",
        r"--- iPHONE BOT"
    ], timeout=10)

    for step in steps:
        # Cada step: espera un prompt concreto y recién ahí responde
        wait_for(proc, q, patterns=step["wait_for"], timeout=step.get("timeout", 45))
        send_user(proc, step["input"], typing_delay=step.get("typing_delay", 0.02))

    # Drenar un poco de output final para que se vea el cierre
    end_deadline = time.time() + 6
    while time.time() < end_deadline and proc.poll() is None:
        try:
            line = q.get(timeout=0.2)
            if "Vos:" in line:
                continue
            print_bot_line(line)
        except queue.Empty:
            pass

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    print(f"\n{C.GREY}✓ Demo completado{C.END}")
    time.sleep(PAUSE_SECONDS)

def run_demo():
    print(f"{C.BOLD}╔═══════════════════════════════════════════════════════════╗{C.END}")
    print(f"{C.BOLD}║          iPHONE BOT UTOPIA (V13) - DEMO PRO              ║{C.END}")
    print(f"{C.BOLD}╚═══════════════════════════════════════════════════════════╝{C.END}\n")

    os.system('rm -f iphone_store_utopia.db events.log')

    demos = [
        {
            "title": "🎁 DEMO 1: Compra rápida (humana) + Reserva + Confirmación",
            "steps": [
                # Bot pregunta qué iPhone -> respondemos.
                # El bot YA saludó en el arranque. Pero el script espera un patrón.
                # Si el patrón de arranque consumió el saludo, aquí fallará.
                # TRUCO: El 'wait_for' inicial consume hasta el saludo.
                # Entonces el primer input debe enviarse SIN esperar (o esperando algo genérico si quedó en buffer).
                # Mejor: Hacemos que el arranque espere "Loaded", y este paso espere el Saludo.
                {"wait_for": [
                    r"¿Qué iPhone estás buscando", 
                    r"¡Hola! Decime qué buscás", 
                    r"Buenas! 👋",
                    r"Hola, ¿en qué modelo estabas pensando"
                ], "input": "hola! busco un iphone 16 pro"},
                # Bot lista opciones -> elegimos capacidad/color
                {"wait_for": [r"¿Cuál preferís\?"], "input": "256 black"},
                # Bot pide nombre
                {"wait_for": [r"¿Tu nombre\?", r"¿C[oó]mo te agendo"], "input": "Pablo"},
                # Bot pide datos de reserva / contacto (depende tu bot: puede pedir teléfono o “cómo te agendo”)
                {"wait_for": [
                    r"tel[eé]fono|¿Cómo te agendo|¿Tu (n[uú]mero|celu)|¿Con qu[eé] datos",
                    r"WhatsApp",
                    r"email",
                    r"necesito un contacto"
                ], "input": "1155667788"},
                # Bot pide zona/envío (si aplica). Si tu bot no lo pide, igual lo soporta como input compuesto.
                {"wait_for": [r"CABA|zona|env[ií]o|¿De d[oó]nde sos|retiro|interior|¿(d[oó]nde|c[oó]mo) lo quer[eé]s"], "input": "CABA"},
                # Bot pide pago (o lo acepta en la misma línea)
                {"wait_for": [r"pago|¿(c[oó]mo|con qu[eé]) pag[aá]s|transfer|mp|mercado pago"], "input": "Transfer"},
                # Bot indica que escriba confirmar (el momento correcto)
                {"wait_for": [r"Escrib[ií] 'confirmar'|escrib[ií]\s+confirmar|para cerrar"], "input": "confirmar"},
            ]
        },
        {
            "title": "💎 DEMO 2: No encuentro exacto → elijo alternativa por número → cierro",
            "steps": [
                {"wait_for": [
                    r"¿Qué iPhone estás buscando",
                    r"¡Hola! Decime qué buscás",
                    r"Buenas! 👋",
                    r"Hola, ¿en qué modelo estabas pensando"
                ], "input": "hola, 16 pro 128 negro"},
                # Bot ofrece alternativas numeradas
                {"wait_for": [r"¿Te sirve alguno\? \(eleg[ií] n[uú]mero\)|eleg[ií]\s+n[uú]mero"], "input": "3"},
                {"wait_for": [r"¿C[oó]mo te agendo|¿Tu nombre\?"], "input": "María"},
                {"wait_for": [
                    r"tel[eé]fono|n[uú]mero",
                    r"WhatsApp",
                    r"email",
                    r"necesito un contacto"
                ], "input": "1122334455"},
                {"wait_for": [r"retiro|CABA|interior|env[ií]o|zona"], "input": "Retiro"},
                {"wait_for": [r"pago|transfer|mp|mercado pago|Perfecto, retir[aá]s en local"], "input": "Transfer"},
                {"wait_for": [r"Escrib[ií] 'confirmar'|para cerrar"], "input": "confirmar"},
            ]
        },
        {
            "title": "🔄 DEMO 3: Cambio de idea (cancelar bien) → nuevo modelo → confirmo",
            "steps": [
                {"wait_for": [
                    r"¿Qué iPhone estás buscando",
                    r"¡Hola! Decime qué buscás",
                    r"Buenas! 👋",
                    r"Hola, ¿en qué modelo estabas pensando"
                ], "input": "hola, quiero iphone 16"},
                {"wait_for": [r"¿Cuál preferís\?"], "input": "256 black"},
                # Bot pide nombre / datos
                {"wait_for": [r"¿Tu nombre\?|¿C[oó]mo te agendo"], "input": "Juan"},
                {"wait_for": [
                    r"tel[eé]fono|n[uú]mero",
                    r"WhatsApp",
                    r"email",
                    r"necesito un contacto"
                ], "input": "1199887766"},
                # En algún punto cancelamos (mostramos que el bot lo tolera)
                {"wait_for": [r"CABA|zona|env[ií]o|retiro|interior|pago|transfer|mp|Escrib[ií]"], "input": "cancelar"},
                # Volvemos con otro pedido
                {"wait_for": [r"¿Qué iPhone estás buscando|Decime modelo|¿Qu[eé] iPhone|¿Qu[eé] modelo busc[aá]s"], "input": "ok, cambié: 17 pro max 512 desert"},
                {"wait_for": [r"¿Te sirve alguno\? \(eleg[ií] n[uú]mero\)|¿Cuál preferís\?"], "input": "3"},
                {"wait_for": [r"¿C[oó]mo te agendo|¿Tu nombre\?"], "input": "Juan"},
                {"wait_for": [
                    r"tel[eé]fono|n[uú]mero",
                    r"WhatsApp",
                    r"email",
                    r"necesito un contacto"
                ], "input": "1199887766"},
                {"wait_for": [r"interior|CABA|zona|env[ií]o|retiro"], "input": "Interior"},
                {"wait_for": [r"pago|transfer|mp|mercado pago"], "input": "MP"},
                {"wait_for": [r"Escrib[ií] 'confirmar'|para cerrar"], "input": "confirmar"},
            ]
        }
    ]

    for d in demos:
        run_one_demo(d["title"], d["steps"])

if __name__ == "__main__":
    try:
        run_demo()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"{C.GREY}[ERROR] {e}{C.END}")