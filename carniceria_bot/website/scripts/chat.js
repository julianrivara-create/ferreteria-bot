// Chat Widget Logic (tenant-aware)

document.addEventListener('DOMContentLoaded', () => {
    const toggleBtn = document.getElementById('chat-toggle-btn');
    const closeBtn = document.getElementById('chat-close-btn');
    const chatWindow = document.getElementById('chat-window');
    const sendBtn = document.getElementById('chat-send-btn');
    const input = document.getElementById('chat-input');
    const messagesContainer = document.getElementById('chat-messages');

    if (!toggleBtn || !chatWindow || !messagesContainer) return;

    const tenantSlug = window.__TENANT_SLUG || 'default';
    const chatApi = `/api/t/${tenantSlug}/chat`;

    toggleBtn.addEventListener('click', () => {
        chatWindow.classList.toggle('open');
        if (chatWindow.classList.contains('open')) input.focus();
    });

    closeBtn?.addEventListener('click', () => {
        chatWindow.classList.remove('open');
    });

    let sessionId = sessionStorage.getItem('chat_session_id');
    if (!sessionId) {
        sessionId = 'web_visitor_' + Math.floor(Math.random() * 1000000);
        sessionStorage.setItem('chat_session_id', sessionId);
    }

    setTimeout(() => {
        if (!chatWindow.classList.contains('open')) {
            chatWindow.classList.add('open');
            input.focus();
            if (messagesContainer.children.length === 0) {
                addBotMessage('Hola. Soy tu asistente de ventas. ¿Que estas buscando hoy?');
            }
        }
    }, 1200);

    async function sendMessage() {
        const text = input.value.trim();
        if (!text) return;

        addUserMessage(text);
        input.value = '';

        let loadingId;
        try {
            loadingId = addLoadingMessage();

            const response = await fetch(chatApi, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: text, user: sessionId })
            });

            const data = await response.json();
            removeLoadingMessage(loadingId);

            if (!response.ok || data.error) {
                addBotMessage('Lo siento, tuve un problema procesando tu mensaje.');
            } else {
                addBotMessage(data.content || 'Sin respuesta');
            }
        } catch (error) {
            console.error('Chat Error:', error);
            removeLoadingMessage(loadingId);
            addBotMessage('Error de red. Intenta nuevamente.');
        }
    }

    sendBtn?.addEventListener('click', sendMessage);
    input?.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendMessage();
    });

    function addUserMessage(text) {
        const div = document.createElement('div');
        div.className = 'message user';
        div.textContent = text;
        messagesContainer.appendChild(div);
        scrollToBottom();
    }

    function formatMessage(text) {
        let html = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        html = html.replace(/\*\*(.*?)\*\*/g, '<b>$1</b>');
        html = html.replace(/^### (.*$)/gim, '<h3>$1</h3>');
        html = html.replace(/^\- (.*$)/gim, '• $1');
        html = html.replace(/\n/g, '<br>');
        return html;
    }

    function addBotMessage(text) {
        const div = document.createElement('div');
        div.className = 'message bot';
        div.innerHTML = formatMessage(text);
        messagesContainer.appendChild(div);
        scrollToBottom();
    }

    function addLoadingMessage() {
        const id = 'loading-' + Date.now();
        const div = document.createElement('div');
        div.id = id;
        div.className = 'message bot loading';
        div.innerHTML = '<span class="dot">.</span><span class="dot">.</span><span class="dot">.</span>';
        messagesContainer.appendChild(div);
        scrollToBottom();
        return id;
    }

    function removeLoadingMessage(id) {
        const el = document.getElementById(id);
        if (el) el.remove();
    }

    function scrollToBottom() {
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }
});
