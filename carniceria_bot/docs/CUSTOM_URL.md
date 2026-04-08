# 🏷️ Cómo personalziar tu link de Ngrok

Por defecto, Ngrok te da una URL aleatoria cada vez (ej: `nonpantheistical-...`).
Para tener un nombre fijo (ej: `julian-iphone-bot.ngrok-free.app`), hay buenas noticias: **¡Ngrok regala 1 dominio estático en el plan gratuito!**

## Pasos para obtener tu link fijo:

1.  **Ir al Dashboard de Ngrok**:
    https://dashboard.ngrok.com/cloud-edge/domains

2.  **Crear Dominio**:
    - Click en **+ New Domain**.
    - Ngrok te va a sugerir uno (ej: `cat-funny-random.ngrok-free.app`).
    - A veces te deja elegir, otras veces te asigna uno fijo aleatorio pero que **nunca cambia**.

3.  **Usar tu nuevo dominio**:
    Una vez que tengas tu dominio (digamos `mi-dominio-fijo.ngrok-free.app`), lanzá ngrok así:

    ```bash
    ngrok http --domain=mi-dominio-fijo.ngrok-free.app 5001
    ```

## 💡 Alternativas

-   **Ngrok Pago**: Permite dominios 100% custom (`bot.miempresa.com`).
-   **Localtunnel**: `npx localtunnel --port 5001 --subdomain julianbot` (A veces inestable, pero gratis y permite elegir nombre).

**Recomendación**: Entra al dashboard de Ngrok y reclamá tu dominio estático gratis. Es lo más profesional sin pagar.
