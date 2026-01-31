// GLOBAL STATE
const App = {
    config: {},
    isGenerating: false,
    processedCount: 0,
    totalItems: 0
};

// TOAST NOTIFICATIONS
const Toast = {
    container: null,

    init() {
        this.container = document.createElement('div');
        this.container.className = 'toast-container';
        document.body.appendChild(this.container);
    },

    show(message, type = 'info', duration = 4000) {
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;

        const icons = {
            success: '✅',
            error: '❌',
            info: 'ℹ️',
            warning: '⚠️'
        };

        toast.innerHTML = `
            <span class="toast-icon">${icons[type] || icons.info}</span>
            <span class="toast-message">${message}</span>
            <span class="toast-close" onclick="this.parentElement.remove()">×</span>
        `;

        this.container.appendChild(toast);

        setTimeout(() => {
            toast.style.animation = 'toastOut 0.3s ease forwards';
            setTimeout(() => toast.remove(), 300);
        }, duration);
    },

    success(msg) { this.show(msg, 'success'); },
    error(msg) { this.show(msg, 'error', 6000); },
    info(msg) { this.show(msg, 'info'); },
    warning(msg) { this.show(msg, 'warning'); }
};

// LOCAL STORAGE
const Storage = {
    key: 'gencourse_toc_draft',
    topicKey: 'gencourse_topic_draft',

    saveTOC(items) {
        try {
            localStorage.setItem(this.key, JSON.stringify(items));
        } catch (e) { console.warn('localStorage save failed', e); }
    },

    loadTOC() {
        try {
            const data = localStorage.getItem(this.key);
            return data ? JSON.parse(data) : null;
        } catch (e) { return null; }
    },

    saveTopic(topic) {
        try {
            localStorage.setItem(this.topicKey, topic);
        } catch (e) { }
    },

    loadTopic() {
        try {
            return localStorage.getItem(this.topicKey) || '';
        } catch (e) { return ''; }
    },

    clear() {
        localStorage.removeItem(this.key);
        localStorage.removeItem(this.topicKey);
    }
};

// TOC MODULE with Methods
const TOC = {
    items: [], // { level: 0, title: "", method: "auto" }
    draggedIdx: null,

    init() {
        // Try load from localStorage
        const saved = Storage.loadTOC();
        if (saved && saved.length > 0) {
            this.items = saved;
            Toast.info('Чернетку завантажено');
        }
        this.render();
    },

    save() {
        Storage.saveTOC(this.items);
    },

    addItem(index, level = 0) {
        if (index === -1) index = this.items.length;
        this.items.splice(index, 0, { level: level, title: "", method: "auto" });
        this.render();
        this.save();
    },

    addRoot() {
        this.addItem(-1, 0);
    },

    deleteItem(index) {
        this.items.splice(index, 1);
        this.render();
        this.save();
    },

    moveLevel(index, delta) {
        const item = this.items[index];
        const newLevel = item.level + delta;
        if (newLevel >= 0) {
            item.level = newLevel;
            this.render();
            this.save();
        }
    },

    updateTitle(index, value) {
        this.items[index].title = value;
        this.save();
    },

    updateMethod(index, value) {
        this.items[index].method = value;
        this.save();
    },

    // DRAG & DROP
    handleDragStart(e, index) {
        this.draggedIdx = index;
        e.target.classList.add('dragging');
        e.dataTransfer.effectAllowed = 'move';
    },

    handleDragEnd(e) {
        e.target.classList.remove('dragging');
        document.querySelectorAll('.toc-item').forEach(el => el.classList.remove('drag-over'));
        this.draggedIdx = null;
    },

    handleDragOver(e, index) {
        e.preventDefault();
        if (this.draggedIdx === null || this.draggedIdx === index) return;

        const items = document.querySelectorAll('.toc-item');
        items.forEach(el => el.classList.remove('drag-over'));
        items[index]?.classList.add('drag-over');
    },

    handleDrop(e, index) {
        e.preventDefault();
        if (this.draggedIdx === null || this.draggedIdx === index) return;

        const [draggedItem] = this.items.splice(this.draggedIdx, 1);
        this.items.splice(index, 0, draggedItem);
        this.render();
        this.save();
        Toast.info('Порядок змінено');
    },

    // SMART PASTE LOGIC
    handlePaste(e, index) {
        const clipboardData = e.clipboardData || window.clipboardData;
        const pastedData = clipboardData.getData('Text');

        if (pastedData.includes('\n')) {
            e.preventDefault();
            const lines = pastedData.split(/\r?\n/).filter(line => line.trim() !== '');
            if (lines.length === 0) return;

            this.items[index].title = lines[0];

            let insertIdx = index + 1;
            const baseLevel = this.items[index].level;

            for (let i = 1; i < lines.length; i++) {
                this.items.splice(insertIdx, 0, { level: baseLevel, title: lines[i], method: "auto" });
                insertIdx++;
            }
            this.render();
            this.save();
        }
    },

    // IMPORT LOGIC
    importDialog() {
        document.getElementById('modal-import').style.display = 'block';
    },

    async applyImport() {
        const text = document.getElementById('import-text-area').value;
        if (!text.trim()) return;

        try {
            const response = await fetch('/api/parse_toc', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: text })
            });
            const data = await response.json();

            if (data.items) {
                this.items = data.items.map(i => ({ level: i.level, title: i.title, method: "auto" }));
                this.render();
                this.save();
                closeModal('modal-import');
                Toast.success(`Імпортовано ${this.items.length} пунктів`);
            }
        } catch (err) {
            Toast.error("Помилка імпорту: " + err);
        }
    },

    getMethodsOverrides() {
        const overrides = {};
        const counters = {};

        this.items.forEach(item => {
            if (item.method && item.method !== 'auto') {
                // Build full title with number
                let fullTitle = '';
                const titleLower = item.title.toLowerCase().trim();
                const specials = ["вступ", "резюме", "висновки", "додатки", "список використаних джерел", "список літератури"];

                if (!specials.includes(titleLower)) {
                    Object.keys(counters).forEach(k => { if (k > item.level) delete counters[k]; });
                    counters[item.level] = (counters[item.level] || 0) + 1;

                    if (item.level === 0) {
                        fullTitle = `Розділ ${counters[item.level]}. ${item.title}`;
                    } else {
                        const parts = [];
                        for (let l = 0; l <= item.level; l++) parts.push(counters[l] || 1);
                        fullTitle = parts.join('.') + ' ' + item.title;
                    }
                } else {
                    fullTitle = item.title;
                }

                overrides[fullTitle] = item.method;
            }
        });

        return overrides;
    },

    render() {
        const container = document.getElementById('toc-editor');
        container.innerHTML = '';

        if (this.items.length === 0) {
            container.innerHTML = '<div class="empty-state">📝 Додайте пункти або імпортуйте текст</div>';
            return;
        }

        const counters = {};

        this.items.forEach((item, index) => {
            // Calc Number
            let numStr = "";
            const titleLower = item.title.toLowerCase().trim();
            const specials = ["вступ", "резюме", "висновки", "додатки", "список використаних джерел", "список літератури"];

            if (!specials.includes(titleLower)) {
                Object.keys(counters).forEach(k => { if (k > item.level) delete counters[k]; });
                counters[item.level] = (counters[item.level] || 0) + 1;

                if (item.level === 0) {
                    numStr = `Розділ ${counters[item.level]}.`;
                } else {
                    const parts = [];
                    for (let l = 0; l <= item.level; l++) parts.push(counters[l] || 1);
                    numStr = parts.join('.');
                }
            }

            const el = document.createElement('div');
            el.className = 'toc-item';
            el.style.paddingLeft = `${item.level * 20}px`;
            el.draggable = true;

            // Determine method label color
            const methodColors = {
                auto: '',
                theoretical: 'color: #60a5fa;',
                practical: 'color: #34d399;'
            };

            el.innerHTML = `
                <span class="drag-handle" title="Перетягніть для сортування">⠿</span>
                <div class="controls">
                    <button class="btn-icon" onclick="TOC.moveLevel(${index}, -1)" title="Зменшити рівень">&lt;</button>
                    <button class="btn-icon" onclick="TOC.moveLevel(${index}, 1)" title="Збільшити рівень">&gt;</button>
                </div>
                <div class="toc-input-wrapper">
                    <span class="toc-number">${numStr}</span>
                    <input type="text" class="toc-input" 
                           value="${this.escapeHtml(item.title)}" 
                           placeholder="Назва розділу..."
                           oninput="TOC.updateTitle(${index}, this.value)"
                           onkeydown="if(event.key === 'Enter') { TOC.addItem(${index + 1}, ${item.level}); }"
                    >
                </div>
                <select class="method-select" onchange="TOC.updateMethod(${index}, this.value)" title="Метод генерації">
                    <option value="auto" ${item.method === 'auto' ? 'selected' : ''}>🤖 авто</option>
                    <option value="theoretical" ${item.method === 'theoretical' ? 'selected' : ''}>📚 теорія</option>
                    <option value="practical" ${item.method === 'practical' ? 'selected' : ''}>📊 аналіз</option>
                </select>
                <div class="controls">
                    <button class="btn-icon" onclick="TOC.addItem(${index + 1}, ${item.level})" title="Додати нижче">+</button>
                    <button class="btn-icon btn-delete" onclick="TOC.deleteItem(${index})" title="Видалити">×</button>
                </div>
            `;

            // Drag & Drop Events
            el.addEventListener('dragstart', (e) => this.handleDragStart(e, index));
            el.addEventListener('dragend', (e) => this.handleDragEnd(e));
            el.addEventListener('dragover', (e) => this.handleDragOver(e, index));
            el.addEventListener('drop', (e) => this.handleDrop(e, index));

            // Bind Paste
            const input = el.querySelector('input');
            input.addEventListener('paste', (e) => this.handlePaste(e, index));

            container.appendChild(el);
        });
    },

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
};

// UI FUNCTIONS
function switchTab(tabName) {
    document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.nav-btn').forEach(el => el.classList.remove('active'));

    document.getElementById(`tab-${tabName}`).classList.add('active');

    const idx = ['dashboard', 'console', 'settings'].indexOf(tabName);
    const buttons = document.querySelectorAll('.nav-menu .nav-btn');
    if (buttons[idx]) buttons[idx].classList.add('active');
}

function closeModal(id) {
    document.getElementById(id).style.display = 'none';
}

async function openResultFile() {
    try {
        const res = await fetch('/api/open_folder', { method: 'POST' });
        const d = await res.json();
        if (d.error) Toast.error("Не вдалося відкрити папку: " + d.error);
    } catch (e) {
        Toast.error("Помилка: " + e);
    }
}

// API CALLS
async function loadConfig() {
    try {
        const res = await fetch('/api/config');
        App.config = await res.json();

        // Fill Settings
        document.getElementById('provider-select').value = App.config.active_provider || 'openai';
        const prov = App.config.providers[App.config.active_provider] || {};
        document.getElementById('api-key-input').value = prov.api_key || '';
        document.getElementById('model-input').value = prov.model || '';

        const dry = App.config.project_settings?.dry_run || false;
        document.getElementById('dry-run-switch').checked = dry;

        // Fill Topic - prefer localStorage, then config
        const savedTopic = Storage.loadTopic();
        const configTopic = App.config.project_settings?.topic || '';
        document.getElementById('topic-input').value = savedTopic || configTopic;

    } catch (e) {
        console.error("Config load error", e);
        Toast.error("Помилка завантаження конфігурації");
    }
}

async function saveConfig() {
    const prov = document.getElementById('provider-select').value;
    const key = document.getElementById('api-key-input').value;
    const model = document.getElementById('model-input').value;
    const dry = document.getElementById('dry-run-switch').checked;

    const payload = {
        active_provider: prov,
        providers: {
            [prov]: { api_key: key, model: model }
        },
        project_settings: {
            dry_run: dry,
            topic: document.getElementById('topic-input').value
        }
    };

    await fetch('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });

    Toast.success("Налаштування збережено!");
}

async function startGeneration() {
    if (App.isGenerating) {
        Toast.warning("Генерація вже виконується!");
        return;
    }

    const topic = document.getElementById('topic-input').value.trim();

    // Save topic to localStorage
    Storage.saveTopic(topic);

    // Reconstruct TOC text
    let tocLines = [];
    const counters = {};

    TOC.items.forEach(item => {
        let line = "    ".repeat(item.level);
        const titleLower = item.title.toLowerCase();

        let numStr = "";
        const specials = ["вступ", "резюме", "висновки", "додатки", "список використаних джерел", "список літератури"];

        if (!specials.includes(titleLower)) {
            Object.keys(counters).forEach(k => { if (k > item.level) delete counters[k]; });
            counters[item.level] = (counters[item.level] || 0) + 1;

            if (item.level === 0) {
                numStr = `Розділ ${counters[item.level]}. `;
            } else {
                const parts = [];
                for (let l = 0; l <= item.level; l++) parts.push(counters[l] || 1);
                numStr = parts.join('.') + " ";
            }
        }

        line += numStr + item.title;
        tocLines.push(line);
    });

    const tocText = tocLines.join('\n');

    if (!topic || !tocText.trim()) {
        Toast.warning("Заповніть тему та зміст!");
        return;
    }

    // Get method overrides from TOC
    const overrides = TOC.getMethodsOverrides();

    // PROGRESS INIT
    App.isGenerating = true;
    App.processedCount = 0;
    App.totalItems = TOC.items.length;

    // Show progress bar
    document.getElementById('progress-container').style.display = 'block';
    updateProgress(0, "Підготовка...");

    switchTab('console');
    document.getElementById('status-badge').innerText = "Генерація...";
    document.getElementById('status-badge').className = "badge active";
    document.getElementById('log-output').innerHTML = '';

    Toast.info("Генерація розпочата!");

    try {
        const res = await fetch('/api/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                topic: topic,
                toc_text: tocText,
                overrides: overrides
            })
        });
        const d = await res.json();
        if (d.error) {
            Toast.error(d.error);
            App.isGenerating = false;
        }
    } catch (e) {
        Toast.error("Помилка запуску: " + e);
        App.isGenerating = false;
    }
}

function updateProgress(percent, statusText) {
    document.getElementById('progress-fill').style.width = `${percent}%`;
    document.getElementById('progress-percent').innerText = `${Math.round(percent)}%`;
    if (statusText) document.getElementById('progress-status').innerText = statusText;
}

// LOGS
function initLogs() {
    const evtSource = new EventSource("/api/logs");
    const logDiv = document.getElementById('log-output');

    evtSource.onmessage = function (e) {
        if (!e.data || e.data === ": keepalive") return;

        const div = document.createElement('div');
        div.className = 'log-line';
        div.textContent = "> " + e.data;

        if (e.data.includes("ERROR")) div.classList.add('error');
        if (e.data.includes("SUCCESS")) div.classList.add('system');
        if (e.data.includes("INFO")) div.classList.add('info');

        logDiv.appendChild(div);
        logDiv.scrollTop = logDiv.scrollHeight;

        // Progress Parsing
        if (App.isGenerating) {
            if (e.data.includes("Обробка:")) {
                const match = e.data.match(/Обробка: (.+?)(?:\s*\[|$)/);
                if (match) {
                    const sectionTitle = match[1].trim();
                    App.processedCount++;
                    const pct = Math.min((App.processedCount / (App.totalItems || 1)) * 100, 95);
                    updateProgress(pct, `${App.processedCount}/${App.totalItems}: ${sectionTitle}`);
                }
            }

            if (e.data.includes("SUCCESS - DONE") || e.data.includes("SUCCESS - Готово")) {
                App.isGenerating = false;
                updateProgress(100, "✅ Завершено!");
                document.getElementById('status-badge').innerText = "Завершено";
                document.getElementById('status-badge').className = "badge success";
                document.getElementById('btn-open-file').disabled = false;
                Toast.success("Генерація завершена успішно!");

                // Clear draft after success
                Storage.clear();
            }

            if (e.data.includes("ERROR")) {
                App.isGenerating = false;
                document.getElementById('status-badge').innerText = "Помилка";
                document.getElementById('status-badge').className = "badge";
                Toast.error("Виникла помилка під час генерації");
            }
        }
    };

    evtSource.onerror = function () {
        console.warn("SSE connection error");
    };
}

// Topic input auto-save
function initTopicAutoSave() {
    const topicInput = document.getElementById('topic-input');
    let saveTimeout;

    topicInput.addEventListener('input', () => {
        clearTimeout(saveTimeout);
        saveTimeout = setTimeout(() => {
            Storage.saveTopic(topicInput.value);
        }, 500);
    });
}

// INIT
window.addEventListener('DOMContentLoaded', () => {
    Toast.init();
    loadConfig();
    TOC.init();
    initLogs();
    initTopicAutoSave();
});

// Close modal on outside click
window.onclick = function (event) {
    if (event.target.classList.contains('modal')) {
        event.target.style.display = "none";
    }
}

// Prevent accidental page close during generation
window.addEventListener('beforeunload', (e) => {
    if (App.isGenerating) {
        e.preventDefault();
        e.returnValue = 'Генерація ще не завершена!';
    }
});
