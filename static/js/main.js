(function () {
    const root = document.documentElement;
    const storedTheme = localStorage.getItem('iccp-theme');
    if (storedTheme === 'dark' || storedTheme === 'light') root.dataset.theme = storedTheme;

    function currentTheme() {
        if (root.dataset.theme) return root.dataset.theme;
        return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }

    function advancementTitle(category) {
        if (category === 'error' || category === 'danger') return '¡Desafío fallido!';
        if (category === 'warning') return '¡Atención!';
        return '¡Progreso realizado!';
    }

    function advancementIcon(category) {
        if (category === 'error' || category === 'danger') return '✕';
        if (category === 'warning') return '!';
        return '★';
    }

    const advancementSound = new Audio('/static/sounds/advancement.mp3');
    advancementSound.preload = 'auto';
    advancementSound.volume = 0.55;

    async function primeAdvancementSound() {
        const originalVolume = advancementSound.volume;
        advancementSound.volume = 0;
        try {
            await advancementSound.play();
            advancementSound.pause();
            advancementSound.currentTime = 0;
        } catch (error) {
            // La notificación visual sigue funcionando si el navegador bloquea el audio.
        } finally {
            advancementSound.volume = originalVolume || 0.55;
        }
    }

    function playAdvancementSound() {
        advancementSound.volume = 0.55;
        advancementSound.pause();
        advancementSound.currentTime = 0;
        advancementSound.play().catch(() => {});
    }

    function scheduleAdvancementRemoval(alert, delay = 1800) {
        window.setTimeout(() => {
            alert.classList.add('hide');
            window.setTimeout(() => alert.remove(), 320);
        }, delay);
    }

    function showMinecraftAdvancement(message, category = 'success', playSound = true) {
        let stack = document.querySelector('.flash-stack');
        if (!stack) {
            stack = document.createElement('div');
            stack.className = 'flash-stack';
            stack.setAttribute('aria-live', 'polite');
            stack.setAttribute('aria-atomic', 'true');
            document.body.appendChild(stack);
        }

        const alert = document.createElement('div');
        alert.className = `alert minecraft-advancement ${category}`;
        alert.setAttribute('role', 'status');

        const icon = document.createElement('div');
        icon.className = 'advancement-icon';
        icon.setAttribute('aria-hidden', 'true');
        icon.textContent = advancementIcon(category);

        const copy = document.createElement('div');
        copy.className = 'advancement-copy';
        const title = document.createElement('div');
        title.className = 'advancement-title';
        title.textContent = advancementTitle(category);
        const body = document.createElement('div');
        body.className = 'advancement-message';
        body.textContent = message;

        copy.append(title, body);
        alert.append(icon, copy);
        stack.appendChild(alert);
        scheduleAdvancementRemoval(alert);
        if (playSound) playAdvancementSound();
        return alert;
    }

    function navigateAfterAdvancement(url, delay = 1500) {
        if (!url) return;
        window.setTimeout(() => window.location.assign(url), delay);
    }

    function setBusy(element, busy) {
        const button = element.matches('form')
            ? element.querySelector('[type="submit"]')
            : element;
        if (!button) return;
        if (busy) {
            button.setAttribute('aria-busy', 'true');
            if ('disabled' in button) button.disabled = true;
        } else {
            button.removeAttribute('aria-busy');
            if ('disabled' in button) button.disabled = false;
        }
    }

    async function submitAjaxAdvancement(element) {
        const isForm = element.matches('form');
        const url = isForm
            ? (element.action || window.location.href)
            : element.href;
        const method = isForm
            ? (element.method || 'POST').toUpperCase()
            : (element.dataset.ajaxMethod || 'GET').toUpperCase();

        const options = {
            method,
            headers: { 'X-Requested-With': 'XMLHttpRequest' },
            credentials: 'same-origin'
        };
        if (isForm && method !== 'GET') options.body = new FormData(element);

        setBusy(element, true);
        try {
            const response = await fetch(url, options);
            const contentType = response.headers.get('content-type') || '';
            if (!contentType.includes('application/json')) {
                throw new Error('La acción no devolvió una respuesta válida.');
            }
            const data = await response.json();
            const category = data.category || (data.success ? 'success' : 'danger');

            if (!response.ok || !data.success) {
                showMinecraftAdvancement(data.message || 'No se pudo completar la acción.', category, false);
                return;
            }

            showMinecraftAdvancement(data.message || 'Acción completada.', category, true);
            navigateAfterAdvancement(data.redirect_url);
        } catch (error) {
            showMinecraftAdvancement(error.message || 'No se pudo completar la acción.', 'danger', false);
        } finally {
            setBusy(element, false);
        }
    }

    function showIncomingChatNotification(data) {
        if (!data || !data.chat_url || window.location.pathname === data.chat_url) return;

        document.querySelector('.incoming-chat-notification')?.remove();

        const banner = document.createElement('a');
        banner.className = 'incoming-chat-notification';
        banner.href = data.chat_url;
        banner.setAttribute('aria-label', `Abrir mensaje de ${data.sender || 'usuario'}`);

        const avatar = document.createElement('img');
        avatar.className = 'incoming-chat-avatar';
        avatar.src = data.avatar_url || '/static/uploads/default.png';
        avatar.alt = '';

        const copy = document.createElement('span');
        copy.className = 'incoming-chat-copy';

        const username = document.createElement('strong');
        username.className = 'incoming-chat-username';
        username.textContent = `@${data.sender || 'usuario'}`;

        const preview = document.createElement('span');
        preview.className = 'incoming-chat-preview';
        preview.textContent = data.preview || 'Nuevo mensaje';

        copy.append(username, preview);
        banner.append(avatar, copy);
        document.body.appendChild(banner);

        requestAnimationFrame(() => banner.classList.add('visible'));

        const removeBanner = () => {
            banner.classList.remove('visible');
            banner.classList.add('hide');
            window.setTimeout(() => banner.remove(), 280);
        };

        const timeout = window.setTimeout(removeBanner, 4300);
        banner.addEventListener('click', () => window.clearTimeout(timeout), { once: true });
    }

    document.addEventListener('DOMContentLoaded', () => {
        if (window.lucide) window.lucide.createIcons({ attrs: { 'stroke-width': 1.9 } });

        if (window.socket) {
            window.socket.on('chat_notification', showIncomingChatNotification);
        }

        const toggle = document.getElementById('themeToggle');
        if (toggle) toggle.addEventListener('click', () => {
            const next = currentTheme() === 'dark' ? 'light' : 'dark';
            root.dataset.theme = next;
            localStorage.setItem('iccp-theme', next);
        });

        document.querySelectorAll('.comments-toggle').forEach(button => button.addEventListener('click', () => {
            const target = document.getElementById(button.dataset.target);
            if (target) {
                target.classList.toggle('expanded');
                target.querySelector('input')?.focus();
            }
        }));

        document.querySelectorAll('.like-action').forEach(button => button.addEventListener('click', () => {
            button.classList.toggle('liked');
        }));

        const toast = document.getElementById('appToast');
        document.querySelectorAll('.demo-action').forEach(button => button.addEventListener('click', () => {
            if (!toast) return;
            toast.textContent = button.dataset.message || 'Próximamente';
            toast.classList.add('visible');
            clearTimeout(window.__iccpToast);
            window.__iccpToast = setTimeout(() => toast.classList.remove('visible'), 2400);
        }));

        document.querySelectorAll('.flash-stack .alert').forEach(alert => scheduleAdvancementRemoval(alert, 1800));

        document.querySelectorAll('[data-ajax-advancement]').forEach(element => {
            if (element.matches('form')) {
                element.addEventListener('submit', async event => {
                    event.preventDefault();
                    const confirmation = element.dataset.ajaxConfirm;
                    if (confirmation && !window.confirm(confirmation)) return;
                    await primeAdvancementSound();
                    await submitAjaxAdvancement(element);
                });
                return;
            }

            element.addEventListener('click', async event => {
                if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
                event.preventDefault();
                const confirmation = element.dataset.ajaxConfirm;
                if (confirmation && !window.confirm(confirmation)) return;
                await primeAdvancementSound();
                await submitAjaxAdvancement(element);
            });
        });
    });
})();
