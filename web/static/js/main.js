/* ════════════════════════════════════════════════════════════════
   GenCourse v5 — premium animated UI
   ════════════════════════════════════════════════════════════════ */

'use strict';

const $ = id => document.getElementById(id);

/* ════════ STATE ════════ */
const App = {
    toc: [],
    workType: 'coursework',
    volume: 'standard',
    preset: 'standard',
    generating: false,
    stage: null,
    bodyTotal: 0,
    bodyDone: 0,
    _lastCost: 0,
};

const STAGES = ['plan', 'translate', 'blueprint', 'research', 'generate', 'review', 'save'];

const PRESET_MODEL = {
    economy: 'gpt-4o-mini',
    standard: 'gemini-2.5-flash',
    quality: 'gpt-4o',
};

const PRICING = {
    'gpt-4o-mini': { i: 0.15, o: 0.60 },
    'gpt-4o': { i: 2.50, o: 10.00 },
    'gemini-2.5-flash': { i: 0.30, o: 2.50 },
};

const VOLUME_TOKENS = { short: 700, standard: 1400, detailed: 2100 };
const VOLUME_HINTS = {
    short: '≈500 слів на підрозділ',
    standard: '≈1000 слів на підрозділ',
    detailed: '≈1500 слів на підрозділ',
};

const SPECIAL_KEYWORDS = ['вступ', 'резюме', 'висновк', 'додатк',
    'список використан', 'література', 'references', 'bibliography'];

const TYPE_OPTIONS = [
    ['auto', '🤖', 'авто (за назвою)'],
    ['intro', '📄', 'вступ'],
    ['conclusion', '🏁', 'висновки'],
    ['bibliography', '📚', 'список джерел'],
];

/* ════════ TOC TEMPLATES ════════ */
const TEMPLATES = {
    coursework: {
        label: '🎓 Курсова (3 розділи + підрозділи)',
        items: [
            { level: 0, title: 'ВСТУП', type: 'intro' },
            { level: 0, title: 'Теоретичні основи дослідження', type: 'auto' },
            { level: 1, title: 'Сутність та зміст поняття', type: 'auto' },
            { level: 1, title: 'Класифікація та підходи', type: 'auto' },
            { level: 1, title: 'Сучасний стан та тенденції', type: 'auto' },
            { level: 0, title: 'Аналіз практики', type: 'auto' },
            { level: 1, title: 'Загальна характеристика об\'єкта аналізу', type: 'auto' },
            { level: 1, title: 'Аналіз ключових показників', type: 'auto' },
            { level: 0, title: 'Шляхи вдосконалення', type: 'auto' },
            { level: 1, title: 'Виявлені проблеми', type: 'auto' },
            { level: 1, title: 'Запропоновані заходи', type: 'auto' },
            { level: 0, title: 'ВИСНОВКИ', type: 'conclusion' },
            { level: 0, title: 'СПИСОК ВИКОРИСТАНИХ ДЖЕРЕЛ', type: 'bibliography' },
        ],
    },
    courseworkSimple: {
        label: '📄 Курсова (без підрозділів)',
        items: [
            { level: 0, title: 'ВСТУП', type: 'intro' },
            { level: 0, title: 'Теоретичні аспекти теми', type: 'auto' },
            { level: 0, title: 'Аналіз стану та проблем', type: 'auto' },
            { level: 0, title: 'Рекомендації та шляхи вирішення', type: 'auto' },
            { level: 0, title: 'ВИСНОВКИ', type: 'conclusion' },
            { level: 0, title: 'СПИСОК ВИКОРИСТАНИХ ДЖЕРЕЛ', type: 'bibliography' },
        ],
    },
    report: {
        label: '🏢 Звіт з практики',
        items: [
            { level: 0, title: 'ВСТУП', type: 'intro' },
            { level: 0, title: 'Загальна характеристика підприємства', type: 'auto' },
            { level: 0, title: 'Аналіз основних напрямів діяльності', type: 'auto' },
            { level: 0, title: 'Виконані під час практики завдання', type: 'auto' },
            { level: 0, title: 'Пропозиції щодо вдосконалення', type: 'auto' },
            { level: 0, title: 'ВИСНОВКИ', type: 'conclusion' },
            { level: 0, title: 'СПИСОК ВИКОРИСТАНИХ ДЖЕРЕЛ', type: 'bibliography' },
        ],
    },
    essay: {
        label: '📝 Реферат',
        items: [
            { level: 0, title: 'ВСТУП', type: 'intro' },
            { level: 0, title: 'Перший аспект теми', type: 'auto' },
            { level: 0, title: 'Другий аспект теми', type: 'auto' },
            { level: 0, title: 'Третій аспект теми', type: 'auto' },
            { level: 0, title: 'ВИСНОВКИ', type: 'conclusion' },
            { level: 0, title: 'СПИСОК ВИКОРИСТАНИХ ДЖЕРЕЛ', type: 'bibliography' },
        ],
    },
    diploma: {
        label: '🎓 Дипломна робота',
        items: [
            { level: 0, title: 'ВСТУП', type: 'intro' },
            { level: 0, title: 'Теоретико-методологічні засади', type: 'auto' },
            { level: 1, title: 'Сутність та основні поняття', type: 'auto' },
            { level: 1, title: 'Зарубіжний і вітчизняний досвід', type: 'auto' },
            { level: 1, title: 'Методичні підходи до аналізу', type: 'auto' },
            { level: 0, title: 'Аналіз об\'єкта дослідження', type: 'auto' },
            { level: 1, title: 'Організаційно-економічна характеристика', type: 'auto' },
            { level: 1, title: 'Аналіз внутрішніх процесів', type: 'auto' },
            { level: 1, title: 'Оцінка ефективності', type: 'auto' },
            { level: 0, title: 'Стратегічні напрями вдосконалення', type: 'auto' },
            { level: 1, title: 'Виявлені проблеми та ризики', type: 'auto' },
            { level: 1, title: 'Розроблені пропозиції', type: 'auto' },
            { level: 1, title: 'Очікувана ефективність', type: 'auto' },
            { level: 0, title: 'ВИСНОВКИ', type: 'conclusion' },
            { level: 0, title: 'СПИСОК ВИКОРИСТАНИХ ДЖЕРЕЛ', type: 'bibliography' },
        ],
    },
};

/* ════════ HELPERS ════════ */
const esc = t => { const d = document.createElement('div'); d.textContent = t || ''; return d.innerHTML; };

function isSpecial(item) {
    if (item.type && item.type !== 'auto')
        return ['intro', 'conclusion', 'bibliography'].includes(item.type);
    const t = (item.title || '').toLowerCase().trim();
    return SPECIAL_KEYWORDS.some(k => t.includes(k));
}

function computeNumbers() {
    const counters = {};
    App.toc.forEach(it => {
        if (isSpecial(it)) {
            it._num = (it.title || '').trim().toUpperCase();
            it._display = '';
            it._special = true;
            return;
        }
        it._special = false;
        Object.keys(counters).forEach(k => { if (+k > it.level) delete counters[k]; });
        counters[it.level] = (counters[it.level] || 0) + 1;
        if (it.level === 0) {
            it._num = `Розділ ${counters[0]}`;
            it._display = `Розділ ${counters[0]}.`;
        } else {
            const parts = [];
            for (let l = 0; l <= it.level; l++) parts.push(counters[l] || 1);
            it._num = parts.join('.');
            it._display = it._num;
        }
    });
}

function tocToText() {
    computeNumbers();
    return App.toc.map(it => {
        const indent = '    '.repeat(it.level);
        if (it._special) return indent + (it.title || '');
        return indent + it._display + ' ' + (it.title || '');
    }).join('\n');
}

function findByFullTitle(ft) {
    ft = (ft || '').trim();
    let best = -1, bestLen = -1;
    App.toc.forEach((it, i) => {
        if (!it._num) return;
        if (it._special) {
            if (ft.toUpperCase() === it._num && it._num.length > bestLen) {
                best = i; bestLen = it._num.length;
            }
            return;
        }
        if (ft.startsWith(it._num)) {
            const ch = ft[it._num.length];
            if (ch === undefined || ch === ' ' || ch === '.') {
                if (it._num.length > bestLen) { best = i; bestLen = it._num.length; }
            }
        }
    });
    return best;
}

function findByNumber(num) {
    num = (num || '').trim();
    return App.toc.findIndex(it => it._num === num);
}

/* ════════ STORAGE ════════ */
const Store = {
    save() {
        try {
            localStorage.setItem('gc4', JSON.stringify({
                toc: App.toc.map(({ level, title, type }) => ({ level, title, type })),
                topic: $('topic-input').value,
                methodology: $('methodology-text').value,
                workType: App.workType,
                volume: App.volume,
                preset: App.preset,
            }));
        } catch (_) { }
    },
    load() {
        try { return JSON.parse(localStorage.getItem('gc4') || 'null'); }
        catch (_) { return null; }
    },
};

/* ════════ TOAST ════════ */
const Toast = (() => {
    let box;
    const show = (msg, type = 'info', ms = 4000) => {
        if (!box) { box = document.createElement('div'); box.className = 'toasts'; document.body.appendChild(box); }
        const t = document.createElement('div');
        t.className = `toast ${type}`;
        t.innerHTML = `<span>${esc(msg)}</span><span class="t-x">×</span>`;
        t.querySelector('.t-x').onclick = () => t.remove();
        box.appendChild(t);
        setTimeout(() => { t.classList.add('out'); setTimeout(() => t.remove(), 320); }, ms);
    };
    return {
        ok: m => show(m, 'ok'),
        err: m => show(m, 'err', 6000),
        warn: m => show(m, 'warn'),
        info: m => show(m, 'info'),
    };
})();

/* ════════ CONFETTI ════════ */
function confettiBurst() {
    const colors = ['#7c5cff', '#2dd4bf', '#5b7cfa', '#f472b6', '#fbbf24', '#34d399'];
    const box = document.createElement('div');
    box.className = 'confetti-box';
    document.body.appendChild(box);
    for (let i = 0; i < 56; i++) {
        const c = document.createElement('div');
        c.className = 'confetti';
        c.style.left = (8 + Math.random() * 84) + 'vw';
        c.style.background = colors[Math.floor(Math.random() * colors.length)];
        c.style.setProperty('--dx', (Math.random() * 160 - 80) + 'px');
        c.style.setProperty('--r0', Math.random() * 360 + 'deg');
        c.style.setProperty('--r1', (Math.random() * 900 - 450) + 'deg');
        c.style.setProperty('--dur', (1.4 + Math.random() * 1.3) + 's');
        c.style.animationDelay = Math.random() * 0.35 + 's';
        if (Math.random() < 0.4) { c.style.width = '6px'; c.style.height = '6px'; c.style.borderRadius = '50%'; }
        box.appendChild(c);
    }
    setTimeout(() => box.remove(), 3200);
}

/* ════════ COUNT-UP ════════ */
function animateCost(target, detail) {
    const el = $('est-cost');
    const from = App._lastCost || 0;
    App._lastCost = target;
    const t0 = performance.now();
    const dur = 450;
    (function tick(now) {
        const k = Math.min((now - t0) / dur, 1);
        const eased = 1 - Math.pow(1 - k, 3);
        el.textContent = `~$${(from + (target - from) * eased).toFixed(3)}`;
        if (k < 1) requestAnimationFrame(tick);
    })(t0);
    $('est-detail').textContent = detail;
}

/* ════════ SECTIONS RENDER ════════ */
function renderSections() {
    computeNumbers();
    const box = $('sections');
    box.innerHTML = '';

    if (!App.toc.length) {
        box.innerHTML = `
            <div class="sections-empty">
                <span class="se-ico">📄</span>
                Документ порожній — почни зі шаблону або додай розділ
                <div class="se-actions">
                    <button class="tool-btn" onclick="openModal('modal-template')">📚 Шаблони</button>
                    <button class="tool-btn" onclick="addItem(-1, 0)">+ Розділ</button>
                </div>
            </div>`;
        updateEstimate();
        return;
    }

    App.toc.forEach((it, idx) => {
        const el = document.createElement('div');
        const typeCls = (it.type && it.type !== 'auto') ? `type-${it.type}` : '';
        el.className = `sec level-${Math.min(it.level, 2)} ${typeCls}`;
        el.dataset.idx = idx;
        el.draggable = true;
        el.style.animationDelay = Math.min(idx * 32, 380) + 'ms';

        const typeOpts = TYPE_OPTIONS.map(([v, emoji, label]) =>
            `<option value="${v}"${v === (it.type || 'auto') ? ' selected' : ''} title="${label}">${emoji}</option>`
        ).join('');

        el.innerHTML = `
            <span class="sec-grip" title="Перетягнути">⠿</span>
            <span class="sec-num">${esc(it._display || (it._special ? '·' : ''))}</span>
            <input class="sec-title" value="${esc(it.title)}" placeholder="Назва…" spellcheck="false">
            <div class="sec-status"></div>
            <select class="sec-type" title="Тип секції">${typeOpts}</select>
            <div class="sec-tools">
                <button class="sec-out" title="Рівень ←">‹</button>
                <button class="sec-in" title="Рівень →">›</button>
                <button class="sec-add" title="Додати нижче">+</button>
                <button class="sec-del" title="Видалити">×</button>
                <button class="sec-regen" title="Перегенерувати цю секцію" hidden>↻</button>
            </div>`;

        const title = el.querySelector('.sec-title');
        title.addEventListener('input', e => { it.title = e.target.value; Store.save(); debouncedRefresh(); });
        title.addEventListener('keydown', e => {
            if (e.key === 'Enter') { e.preventDefault(); addItem(idx + 1, it.level); }
        });
        title.addEventListener('paste', e => handleMultilinePaste(e, idx));

        el.querySelector('.sec-type').addEventListener('change', e => {
            it.type = e.target.value;
            Store.save();
            renderSections();
        });

        el.querySelector('.sec-out').onclick = () => { if (it.level > 0) { it.level--; Store.save(); renderSections(); } };
        el.querySelector('.sec-in').onclick = () => { it.level = Math.min(it.level + 1, 2); Store.save(); renderSections(); };
        el.querySelector('.sec-add').onclick = () => addItem(idx + 1, it.level);
        el.querySelector('.sec-del').onclick = () => { App.toc.splice(idx, 1); Store.save(); renderSections(); };
        el.querySelector('.sec-regen').onclick = () => regenerateSection(it._num);

        el.addEventListener('dragstart', e => {
            App._dragIdx = idx;
            el.classList.add('dragging');
            e.dataTransfer.effectAllowed = 'move';
        });
        el.addEventListener('dragend', () => {
            el.classList.remove('dragging');
            box.querySelectorAll('.sec').forEach(s => s.classList.remove('drag-over'));
            App._dragIdx = null;
        });
        el.addEventListener('dragover', e => {
            e.preventDefault();
            if (App._dragIdx === null || App._dragIdx === idx) return;
            box.querySelectorAll('.sec').forEach(s => s.classList.remove('drag-over'));
            el.classList.add('drag-over');
        });
        el.addEventListener('drop', e => {
            e.preventDefault();
            if (App._dragIdx === null || App._dragIdx === idx) return;
            const [moved] = App.toc.splice(App._dragIdx, 1);
            App.toc.splice(idx, 0, moved);
            Store.save();
            renderSections();
        });

        box.appendChild(el);
    });

    updateEstimate();
}

let _refreshTimer;
function debouncedRefresh() {
    clearTimeout(_refreshTimer);
    _refreshTimer = setTimeout(() => {
        computeNumbers();
        document.querySelectorAll('.sec').forEach(el => {
            const it = App.toc[+el.dataset.idx];
            if (it) el.querySelector('.sec-num').textContent = it._display || (it._special ? '·' : '');
        });
        updateEstimate();
    }, 300);
}

function addItem(index, level) {
    if (index === -1) index = App.toc.length;
    App.toc.splice(index, 0, { level, title: '', type: 'auto' });
    Store.save();
    renderSections();
    const el = document.querySelector(`.sec[data-idx="${index}"] .sec-title`);
    if (el) el.focus();
}

function handleMultilinePaste(e, idx) {
    const data = (e.clipboardData || window.clipboardData).getData('Text');
    if (!data.includes('\n')) return;
    e.preventDefault();
    const lines = data.split(/\r?\n/).map(l => l.trim()).filter(Boolean);
    if (!lines.length) return;
    App.toc[idx].title = lines[0];
    const base = App.toc[idx].level;
    for (let i = 1; i < lines.length; i++) {
        App.toc.splice(idx + i, 0, { level: base, title: lines[i], type: 'auto' });
    }
    Store.save();
    renderSections();
}

/* ════════ SECTION STATUS ════════ */
function secEl(idx) { return document.querySelector(`.sec[data-idx="${idx}"]`); }

function setSecStatus(idx, state, extra = '') {
    const el = secEl(idx);
    if (!el) return;
    el.classList.remove('st-gen', 'st-done', 'st-skip', 'st-err');
    const status = el.querySelector('.sec-status');
    const regen = el.querySelector('.sec-regen');

    switch (state) {
        case 'planned':
            status.innerHTML = '';
            break;
        case 'skip':
            el.classList.add('st-skip');
            status.innerHTML = '<span>заголовок</span>';
            break;
        case 'gen':
            el.classList.add('st-gen');
            status.innerHTML = '<span class="spin"></span><span>генерація…</span>';
            break;
        case 'done':
            el.classList.add('st-done', 'flash');
            setTimeout(() => el.classList.remove('flash'), 950);
            status.innerHTML = `<span class="ok-txt">✓${extra ? ' ' + esc(extra) : ''}</span>`;
            if (regen && !App.toc[idx]?._special) regen.hidden = false;
            break;
        case 'err':
            el.classList.add('st-err');
            status.innerHTML = '<span style="color:var(--err)">помилка</span>';
            if (regen) regen.hidden = false;
            break;
        case 'issue': {
            const badge = document.createElement('span');
            badge.className = 'issue-badge';
            badge.textContent = '⚠';
            badge.title = extra;
            status.appendChild(badge);
            break;
        }
    }
}

function showRegenButtons() {
    App.toc.forEach((it, idx) => {
        const el = secEl(idx);
        if (!el) return;
        const regen = el.querySelector('.sec-regen');
        if (!regen) return;
        const isBib = it.type === 'bibliography' ||
            (it._special && (it._num || '').includes('СПИСОК'));
        const isParentSkip = el.classList.contains('st-skip');
        regen.hidden = isBib || isParentSkip;
    });
}

/* ════════ ESTIMATE ════════ */
function updateEstimate() {
    computeNumbers();
    let genCount = 0;
    App.toc.forEach((it, i) => {
        if (it.type === 'bibliography') return;
        if (it._special && (it._num || '').match(/СПИСОК|ЛІТЕРАТУР|ДОДАТК/)) return;
        if (it.level === 0 && !it._special) {
            const next = App.toc[i + 1];
            if (next && next.level > it.level) return;
        }
        genCount++;
    });

    if (!genCount) {
        $('est-cost').textContent = '—';
        $('est-detail').textContent = '';
        App._lastCost = 0;
        return;
    }

    const model = PRESET_MODEL[App.preset];
    const price = PRICING[model] || PRICING['gemini-2.5-flash'];
    const outT = VOLUME_TOKENS[App.volume] || 1400;
    const inT = genCount * 3000 + 6000;
    const cost = (inT / 1e6) * price.i + (genCount * outT / 1e6) * price.o;
    const mins = App.preset === 'quality' ? 1 : App.preset === 'economy' ? 1.5 : 2;

    animateCost(cost, `${genCount} секцій · ≈${mins} хв`);
}

/* ════════ PROGRESS / STAGES ════════ */
function setStage(stage, pct, label) {
    App.stage = stage;
    const i = STAGES.indexOf(stage);
    document.querySelectorAll('.sdot').forEach(d => {
        const di = STAGES.indexOf(d.dataset.stage);
        d.classList.remove('active', 'done');
        if (di < i) d.classList.add('done');
        else if (di === i) d.classList.add('active');
    });
    $('stage-line-fill').style.width = `${(i / (STAGES.length - 1)) * 100}%`;
    $('top-progress-fill').style.width = `${pct}%`;
    if (label) swapTickerLine(label);
}

function swapTickerLine(text) {
    const el = $('ticker-line');
    el.classList.add('swap');
    setTimeout(() => {
        el.textContent = text;
        el.classList.remove('swap');
    }, 160);
}

function finishStages(success) {
    document.querySelectorAll('.sdot').forEach(d => {
        d.classList.remove('active');
        if (success) d.classList.add('done');
    });
    $('stage-line-fill').style.width = success ? '100%' : '0%';
    $('top-progress-fill').style.width = success ? '100%' : '0%';
    if (success) setTimeout(() => {
        $('top-progress-fill').style.width = '0%';
        $('stage-line-fill').style.width = '0%';
        document.querySelectorAll('.sdot').forEach(d => d.classList.remove('done'));
    }, 2600);
}

function setPill(state, text) {
    const pill = $('status-pill');
    pill.className = 'status-pill' + (state ? ' ' + state : '');
    pill.innerHTML = `<i></i>${esc(text)}`;
}

/* ════════ GENERATE ════════ */
async function startGeneration() {
    if (App.generating) { Toast.warn('Генерація вже виконується'); return; }
    const topic = $('topic-input').value.trim();
    if (!topic) { Toast.warn('Введи тему роботи'); $('topic-input').focus(); return; }
    if (!App.toc.length) { Toast.warn('Додай зміст'); return; }

    Store.save();
    App.generating = true;
    App.bodyTotal = 0;
    App.bodyDone = 0;

    $('sections').classList.add('locked');
    $('btn-generate').disabled = true;
    $('btn-generate').classList.add('busy');
    $('btn-download').disabled = true;
    $('btn-download').classList.remove('attention');
    $('review-banner').hidden = true;
    setPill('run', 'генерація');
    setStage('plan', 4, 'Старт…');

    App.toc.forEach((_, i) => setSecStatus(i, 'planned'));

    try {
        const res = await fetch('/api/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                topic,
                toc_text: tocToText(),
                work_type: App.workType,
                methodology_text: $('methodology-text').value.trim(),
                section_types: App.toc.map(i => i.type || 'auto'),
                volume: App.volume,
                preset: App.preset,
            }),
        });
        const d = await res.json();
        if (d.error) throw new Error(d.error);
        Toast.info('Генерація розпочата');
    } catch (e) {
        Toast.err(String(e.message || e));
        endGeneration(false);
    }
}

function endGeneration(success) {
    App.generating = false;
    $('sections').classList.remove('locked');
    $('btn-generate').disabled = false;
    $('btn-generate').classList.remove('busy');
    finishStages(success);
    if (success) {
        setPill('done', 'готово');
        const dl = $('btn-download');
        dl.disabled = false;
        dl.classList.add('attention');
        setTimeout(() => dl.classList.remove('attention'), 6000);
        showRegenButtons();
        fetchReview();
        confettiBurst();
    } else {
        setPill('err', 'помилка');
    }
}

async function regenerateSection(num) {
    if (App.generating) { Toast.warn('Дочекайся завершення'); return; }
    if (!confirm(`Перегенерувати "${num}"? DOCX буде перезаписано.`)) return;

    App.generating = true;
    $('btn-generate').disabled = true;
    $('btn-generate').classList.add('busy');
    setPill('run', `regen ${num}`);
    const idx = findByNumber(num);
    if (idx >= 0) setSecStatus(idx, 'gen');

    try {
        const res = await fetch('/api/regenerate_section', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ section_number: num, volume: App.volume }),
        });
        const d = await res.json();
        if (d.error) throw new Error(d.error);
    } catch (e) {
        Toast.err(String(e.message || e));
        App.generating = false;
        $('btn-generate').disabled = false;
        $('btn-generate').classList.remove('busy');
        setPill('', 'готово');
        if (idx >= 0) setSecStatus(idx, 'err');
    }
}

/* ════════ REVIEW ════════ */
async function fetchReview() {
    try {
        const r = await fetch('/api/last_state');
        const d = await r.json();
        if (d.available && d.review) renderReview(d.review);
    } catch (_) { }
}

function renderReview(rev) {
    const banner = $('review-banner');
    banner.hidden = false;

    const score = Math.max(0, Math.min(10, Number(rev.score) || 0));
    const scoreBox = $('rb-score');
    scoreBox.className = 'rb-score ' + (score >= 8 ? 'good' : score >= 6 ? 'mid' : 'low');

    // число з count-up
    const numEl = $('rb-score-num');
    const t0 = performance.now();
    (function tick(now) {
        const k = Math.min((now - t0) / 900, 1);
        const eased = 1 - Math.pow(1 - k, 3);
        const v = score * eased;
        numEl.textContent = v.toFixed(v < 10 ? 1 : 0);
        if (k < 1) requestAnimationFrame(tick);
    })(t0);

    // кільце: C = 2πr = 2π·20 ≈ 125.7
    const C = 125.7;
    requestAnimationFrame(() => {
        $('rb-ring').style.strokeDashoffset = String(C * (1 - score / 10));
    });

    $('rb-verdict').textContent = rev.verdict || '';

    let html = '';
    if (rev.strengths?.length) {
        html += '<div class="rb-strengths">' +
            rev.strengths.map(s => `<span class="rb-chip">✓ ${esc(s)}</span>`).join('') +
            '</div>';
    }
    (rev.issues || []).forEach(it => {
        const sev = ['low', 'medium', 'high'].includes(it.severity) ? it.severity : 'medium';
        html += `<div class="rb-issue sev-${sev}">
            <span class="ri-sec">${esc(it.section || '—')}</span>
            <span class="ri-text">${esc(it.problem || '')}</span>
            ${it.section ? `<button data-regen="${esc(it.section)}" title="Перегенерувати">↻</button>` : ''}
        </div>`;
        const idx = findByNumber(it.section);
        if (idx >= 0) setSecStatus(idx, 'issue', it.problem || '');
    });
    $('rb-body').innerHTML = html;
    $('rb-body').querySelectorAll('[data-regen]').forEach(b =>
        b.onclick = () => regenerateSection(b.dataset.regen));
}

/* ════════ SSE LOGS ════════ */
function initLogs() {
    const evt = new EventSource('/api/logs');
    const out = $('log-output');

    evt.onmessage = e => {
        if (!e.data || e.data === ': keepalive') return;
        const msg = e.data;

        const line = document.createElement('div');
        line.className = 'log-line' +
            (msg.includes('ERROR') ? ' err' :
             msg.includes('WARNING') ? ' warn' :
             msg.includes('SUCCESS') ? ' ok' :
             msg.includes('INFO') ? ' info' : '');
        line.textContent = msg;
        out.appendChild(line);
        while (out.children.length > 500) out.removeChild(out.firstChild);
        out.scrollTop = out.scrollHeight;

        if (!App.generating) return;

        const short = msg.replace(/^[\d\-:,\s]+[-\s]*\w*\s*[-:]*\s*/, '').slice(0, 120);
        if (short && !App.stage) swapTickerLine(short);

        /* стейджі */
        if (msg.includes('ПЛАН:')) setStage('plan', 8, 'Планування секцій…');
        else if (msg.includes('План готовий:')) { applyPlanLine(msg); setStage('plan', 16, 'План готовий'); }
        else if (msg.includes('Translate [')) setStage('translate', 22, 'Переклад запитів EN…');
        else if (msg.includes('BLUEPRINTS:') || msg.includes('DISTRIBUTE:')) setStage('blueprint', 30, 'Content blueprint…');
        else if (msg.includes('RESEARCH:') && msg.includes('паралельних')) setStage('research', 38, 'Пошук джерел…');
        else if (msg.includes('RESEARCH: зібрано')) setStage('research', 52, 'Джерела зібрано');
        else if (msg.includes('GENERATE body:')) {
            const m = msg.match(/GENERATE body: (\d+)/);
            App.bodyTotal = m ? +m[1] : 0;
            App.bodyDone = 0;
            setStage('generate', 55, `Генерація 0/${App.bodyTotal}`);
        }
        else if (msg.includes('REVIEW: запуск')) setStage('review', 90, 'Рецензія ШІ…');
        else if (msg.includes('DOCX збережено')) setStage('save', 99, 'Збереження…');

        /* per-section статуси */
        let m;
        if ((m = msg.match(/→ GEN \[\w+\]\s+(.+?)\s*\|/)) || (m = msg.match(/→ GEN \[\w+\]\s+(.+)$/))) {
            const idx = findByFullTitle(m[1]);
            if (idx >= 0) setSecStatus(idx, 'gen');
        }
        if ((m = msg.match(/✓ GEN \[(.+?)\]\s+\d+ chars(?:, цитат=(\d+))?/))) {
            const idx = findByFullTitle(m[1]);
            if (idx >= 0) setSecStatus(idx, 'done', m[2] ? `${m[2]} цитат` : '');
            App.bodyDone++;
            if (App.bodyTotal) {
                const pct = 55 + Math.min(App.bodyDone / App.bodyTotal, 1) * 32;
                setStage('generate', pct, `Генерація ${App.bodyDone}/${App.bodyTotal}`);
            }
        }
        if ((m = msg.match(/✗ GEN FAIL \[(.+?)\]/))) {
            const idx = findByFullTitle(m[1]);
            if (idx >= 0) setSecStatus(idx, 'err');
        }

        /* завершення */
        if (msg.startsWith('FILE_READY') || msg.includes('SUCCESS - DONE') || msg.includes('SUCCESS - REGEN')) {
            endGeneration(true);
            Toast.ok(msg.includes('REGEN') ? 'Секцію перегенеровано' : 'Роботу згенеровано 🎉');
        } else if (msg.startsWith('ERROR') || msg.includes('Аварійне завершення')) {
            endGeneration(false);
            Toast.err('Збій під час генерації — дивись логи');
        }
    };

    evt.onerror = () => console.warn('SSE reconnect…');
}

function applyPlanLine(msg) {
    const m = msg.match(/План готовий:\s*(.+)$/);
    if (!m) return;
    m[1].split(',').map(s => s.trim()).forEach(token => {
        const p = token.match(/^(.+?)\[(\w+)(⊘)?\]$/);
        if (!p) return;
        const [, num, , skip] = p;
        const idx = findByNumber(num.trim());
        if (idx < 0) return;
        if (skip) setSecStatus(idx, 'skip');
    });
}

/* ════════ ACTIONS ════════ */
async function downloadDocx() {
    try {
        const res = await fetch('/api/download');
        if (!res.ok) {
            const d = await res.json().catch(() => ({}));
            Toast.err(d.error || `HTTP ${res.status}`);
            return;
        }
        const blob = await res.blob();
        const cd = res.headers.get('Content-Disposition') || '';
        const fm = cd.match(/filename\*?=(?:UTF-8'')?["']?([^"';\n]+)/i);
        const name = fm ? decodeURIComponent(fm[1]) : 'kursova.docx';
        const url = URL.createObjectURL(blob);
        const a = Object.assign(document.createElement('a'), { href: url, download: name });
        document.body.appendChild(a); a.click(); a.remove();
        URL.revokeObjectURL(url);
    } catch (e) { Toast.err('Помилка завантаження: ' + e); }
}

async function openFolder() {
    try {
        const r = await fetch('/api/open_folder', { method: 'POST' });
        const d = await r.json();
        if (d.error) Toast.err(d.error);
    } catch (e) { Toast.err(String(e)); }
}

async function uploadMethodology(file) {
    if (!file) return;
    const fd = new FormData();
    fd.append('file', file);
    try {
        const res = await fetch('/api/upload_methodology', { method: 'POST', body: fd });
        const d = await res.json();
        if (d.error) { Toast.err(d.error); return; }
        $('methodology-text').value = d.text || '';
        $('dropzone').classList.add('loaded');
        $('dropzone-text').textContent = `✓ ${d.filename}`;
        Store.save();
        Toast.ok(`Методичку завантажено (${(d.text || '').length} симв.)`);
    } catch (e) { Toast.err(String(e)); }
}

/* ════════ MODALS ════════ */
function openModal(id) { $(id).classList.add('show'); }
function closeModal(id) { $(id).classList.remove('show'); }

function renderTemplates() {
    const list = $('template-list');
    list.innerHTML = '';
    Object.values(TEMPLATES).forEach(tpl => {
        const b = document.createElement('button');
        b.innerHTML = `<span>${tpl.label}</span><span class="t-count">${tpl.items.length} пунктів</span>`;
        b.onclick = () => {
            App.toc = tpl.items.map(i => ({ ...i }));
            Store.save();
            renderSections();
            closeModal('modal-template');
            Toast.ok('Шаблон застосовано');
        };
        list.appendChild(b);
    });
}

async function applyImport() {
    const text = $('import-text').value;
    if (!text.trim()) return;
    try {
        const res = await fetch('/api/parse_toc', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text }),
        });
        const d = await res.json();
        if (d.items) {
            App.toc = d.items.map(i => ({ level: i.level, title: i.title, type: 'auto' }));
            Store.save();
            renderSections();
            closeModal('modal-import');
            Toast.ok(`Імпортовано ${App.toc.length} пунктів`);
        }
    } catch (e) { Toast.err('Помилка імпорту: ' + e); }
}

/* ════════ INIT ════════ */
function initControls() {
    $('worktype-seg').querySelectorAll('button').forEach(b => {
        b.onclick = () => {
            App.workType = b.dataset.value;
            $('worktype-seg').querySelectorAll('button').forEach(x => x.classList.toggle('active', x === b));
            Store.save();
        };
    });

    $('volume-seg').querySelectorAll('button').forEach(b => {
        b.onclick = () => {
            App.volume = b.dataset.value;
            $('volume-seg').querySelectorAll('button').forEach(x => x.classList.toggle('active', x === b));
            $('volume-hint').textContent = VOLUME_HINTS[App.volume];
            Store.save();
            updateEstimate();
        };
    });

    $('preset-stack').querySelectorAll('button').forEach(b => {
        b.onclick = () => {
            App.preset = b.dataset.preset;
            $('preset-stack').querySelectorAll('button').forEach(x => x.classList.toggle('active', x === b));
            Store.save();
            updateEstimate();
        };
    });

    const dz = $('dropzone');
    dz.onclick = () => $('methodology-file').click();
    $('methodology-file').onchange = e => uploadMethodology(e.target.files[0]);
    dz.addEventListener('dragover', e => { e.preventDefault(); dz.classList.add('drag'); });
    dz.addEventListener('dragleave', () => dz.classList.remove('drag'));
    dz.addEventListener('drop', e => {
        e.preventDefault();
        dz.classList.remove('drag');
        uploadMethodology(e.dataTransfer.files[0]);
    });

    $('btn-generate').onclick = startGeneration;
    $('btn-download').onclick = downloadDocx;
    $('btn-folder').onclick = openFolder;
    $('btn-template').onclick = () => openModal('modal-template');
    $('btn-import').onclick = () => openModal('modal-import');
    $('btn-apply-import').onclick = applyImport;
    $('btn-add-chapter').onclick = () => addItem(-1, 0);
    $('btn-add-sub').onclick = () => addItem(-1, 1);
    $('rb-close').onclick = () => { $('review-banner').hidden = true; };

    $('ticker-bar').onclick = () => $('ticker').classList.toggle('open');
    $('log-clear').onclick = e => {
        e.stopPropagation();
        $('log-output').innerHTML = '';
    };

    document.querySelectorAll('.modal').forEach(m => {
        m.addEventListener('click', e => { if (e.target === m) m.classList.remove('show'); });
        m.querySelectorAll('[data-close]').forEach(x => x.onclick = () => m.classList.remove('show'));
    });

    let t1;
    $('topic-input').addEventListener('input', () => { clearTimeout(t1); t1 = setTimeout(Store.save, 400); });
    let t2;
    $('methodology-text').addEventListener('input', () => { clearTimeout(t2); t2 = setTimeout(Store.save, 400); });

    document.addEventListener('keydown', e => {
        if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); startGeneration(); }
        if (e.key === 'Escape') document.querySelectorAll('.modal.show').forEach(m => m.classList.remove('show'));
    });

    window.addEventListener('beforeunload', e => {
        if (App.generating) { e.preventDefault(); e.returnValue = ''; }
    });
}

function applySaved(saved) {
    if (!saved) return;
    if (saved.toc?.length) App.toc = saved.toc.map(i => ({ type: 'auto', ...i }));
    if (saved.topic) $('topic-input').value = saved.topic;
    if (saved.methodology) $('methodology-text').value = saved.methodology;
    if (saved.workType) {
        App.workType = saved.workType;
        $('worktype-seg').querySelectorAll('button').forEach(b =>
            b.classList.toggle('active', b.dataset.value === App.workType));
    }
    if (saved.volume) {
        App.volume = saved.volume;
        $('volume-seg').querySelectorAll('button').forEach(b =>
            b.classList.toggle('active', b.dataset.value === App.volume));
        $('volume-hint').textContent = VOLUME_HINTS[App.volume];
    }
    if (saved.preset && PRESET_MODEL[saved.preset]) {
        App.preset = saved.preset;
        $('preset-stack').querySelectorAll('button').forEach(b =>
            b.classList.toggle('active', b.dataset.preset === App.preset));
    }
}

async function loadServerState() {
    try {
        const r = await fetch('/api/config');
        const cfg = await r.json();
        if (!$('topic-input').value && cfg.project_settings?.topic)
            $('topic-input').value = cfg.project_settings.topic;
        if (!$('methodology-text').value && cfg.project_settings?.methodology_summary)
            $('methodology-text').value = cfg.project_settings.methodology_summary;
    } catch (_) { }

    try {
        const r = await fetch('/api/last_state');
        const d = await r.json();
        if (d.available) {
            $('btn-download').disabled = false;
            if (d.review) renderReview(d.review);
        }
    } catch (_) { }
}

window.addEventListener('DOMContentLoaded', async () => {
    initControls();
    renderTemplates();
    applySaved(Store.load());
    renderSections();
    initLogs();
    await loadServerState();
});

window.openModal = openModal;
window.addItem = addItem;
