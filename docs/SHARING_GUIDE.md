# 🌐 Cómo Compartir tu Dashboard Local

Tu dashboard corre en `localhost` (tu propia máquina), así que si le mandás el link `http://localhost:5001` a alguien, **NO le va a funcionar**.

Tenés 3 opciones para mostrarlo:

## Opción 1: Link Público (Ngrok) - ⭐ Recomendado
Crea un "túnel" temporal para que cualquiera pueda entrar desde su navegador.

1.  **Instalar ngrok**: [Descargar aquí](https://ngrok.com/download)
2.  **Ejecutar**:
    ```bash
    ngrok http 5001
    ```
3.  **Copiar el link**: Te dará algo como `https://random-name.ngrok-free.app`.
4.  **Enviar**: Pasale ese link a la otra persona.

## Opción 2: Video/Screenshot
Si solo querés mostrar cómo se ve:
- `Cmd + Shift + 5` en Mac para grabar pantalla.
- Navegá un poco por el dashboard mostrando los gráficos.

## Opción 3: Exportar HTML (Próximamente)
Podemos crear un script que genere un archivo `.html` estático con los datos actuales, que puedas mandar por mail.

---

> 💡 **Tip:** Ngrok es la herramienta estándar que usamos los desarrolladores para esto. Es gratis y segura (el túnel se cierra cuando cerrás la terminal).
