/* ──────────────────────────────────────────────────────────────────────
   app.js · Restored & Optimized Radial StarMap
──────────────────────────────────────────────────────────────────────── */
'use strict';

// ── DOM refs ─────────────────────────────────────────────────────────────
const queryInput    = document.getElementById('query-input');
const searchBtn     = document.getElementById('search-btn');
const vecMathBtn    = document.getElementById('vec-math-btn');
const randomBtn     = document.getElementById('random-btn');
const methodGroup   = document.getElementById('method-group');
const topkSelect    = document.getElementById('topk-select');
const categorySelect = document.getElementById('category-select');
const debugToggle   = document.getElementById('debug-toggle');
const debugPanel    = document.getElementById('debug-panel');
const statusBar     = document.getElementById('status-bar');
const statusText    = document.getElementById('status-text');
const methodBadge   = document.getElementById('method-badge');
const visualStatusNote = document.getElementById('visual-status-note');
const mmCompare     = document.getElementById('mm-compare');
const excludeBadge  = document.getElementById('exclude-badge');
const excludeCount  = document.getElementById('exclude-count');
const clearExclude  = document.getElementById('clear-exclude-btn');
const spinner       = document.getElementById('spinner');
const resultsGrid   = document.getElementById('results-grid');
const emptyState    = document.getElementById('empty-state');
const starSection   = document.getElementById('star-map-section');
const vecBar        = document.getElementById('vec-bar');
const vecResultBar  = document.getElementById('vec-result-bar');
const similarPanel  = document.getElementById('similar-panel');
const similarTitle  = document.getElementById('similar-title');
const similarGrid   = document.getElementById('similar-grid');
const similarClose  = document.getElementById('similar-close');
const historyBar    = document.getElementById('history-bar');
const historyRow    = document.getElementById('history-row');
const runEvalBtn    = document.getElementById('run-eval-btn');
const evalResults   = document.getElementById('eval-results');
const evalTableWrap = document.getElementById('eval-table-wrap');
const toast         = document.getElementById('toast');

const journeyFrom   = document.getElementById('journey-from');
const journeyTo     = document.getElementById('journey-to');
const journeyBtn    = document.getElementById('journey-btn');
const journeyRes    = document.getElementById('journey-result');

const storyInput    = document.getElementById('story-input');
const storyBtn      = document.getElementById('story-btn');
const storySequence = document.getElementById('story-sequence');
const storyAiToggle = document.getElementById('story-ai-toggle');
const storyReasoning = document.getElementById('story-reasoning-trace');
const magicBtns      = document.querySelectorAll('.magic-btn');
const mapLabelsContainer = document.getElementById('star-map-labels');

const pulseActive   = document.getElementById('pulse-active');
const pulseTrends   = document.getElementById('pulse-trends');

// ── state ────────────────────────────────────────────────────────────────
let currentMethod = 'hybrid';
let isVecMode     = false;
let excludeSet    = new Set();
let likedSet      = new Set();
let lastResults   = [];
let lastQuery     = '';
let _abortCtrl    = null;
let _feedbackRefreshTimer = null;
let evalChartObj  = null;
let evalRadarObj  = null;
let systemStatus   = null;
let visualIndexReady = true;
let mmCompareCache = { key: '', html: '' };

const VISUAL_METHODS = new Set(['visual', 'mm_hybrid']);
const EVAL_SAMPLE_SIZE = 100;

// ── toast ────────────────────────────────────────────────────────────────
let _toastTimer;
function showToast(msg, dur = 2500) {
    toast.textContent = msg;
    toast.classList.add('show');
    clearTimeout(_toastTimer);
    _toastTimer = setTimeout(() => toast.classList.remove('show'), dur);
}

function compactText(value, maxChars = 120) {
    const text = String(value || '').replace(/\s+/g, ' ').trim();
    return text.length > maxChars ? `${text.slice(0, maxChars).replace(/[，、；：,.。！？!? ]+$/, '')}。` : text;
}

// ── history ──────────────────────────────────────────────────────────────
const HISTORY_KEY = 'emojiSearchHistory_r3';
function loadHistory() { try { return JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]'); } catch { return []; } }
function pushHistory(q) {
    let h = loadHistory().filter(x => x !== q); h.unshift(q); h = h.slice(0, 8);
    localStorage.setItem(HISTORY_KEY, JSON.stringify(h)); renderHistory();
}
function renderHistory() {
    const h = loadHistory();
    if (!h.length) { historyBar.style.display = 'none'; return; }
    historyBar.style.display = 'block';
    const existing = historyRow.querySelectorAll('.history-chip'); existing.forEach(c => c.remove());
    h.forEach(q => {
        const chip = document.createElement('button'); chip.className = 'history-chip'; chip.textContent = q;
        chip.addEventListener('click', () => { queryInput.value = q; if(isVecMode)setVecMode(false); doSearch(); });
        historyRow.appendChild(chip);
    });
}
renderHistory();

async function loadCategories() {
    if (!categorySelect) return;
    try {
        const resp = await fetch('/api/categories');
        const data = await resp.json();
        (data.categories || []).forEach(cat => {
            const opt = document.createElement('option');
            opt.value = cat.name;
            opt.textContent = `${cat.name} (${cat.count})`;
            categorySelect.appendChild(opt);
        });
    } catch(e) {
        console.warn('category load failed', e);
    }
}
loadCategories();
if (categorySelect) {
    categorySelect.addEventListener('change', () => {
        if (queryInput.value.trim() && !isVecMode) doSearch();
    });
}
if (debugToggle) {
    debugToggle.addEventListener('change', () => {
        if (queryInput.value.trim() && !isVecMode) doSearch();
        if (!debugToggle.checked && debugPanel) debugPanel.style.display = 'none';
    });
}

// ── method pills ─────────────────────────────────────────────────────────
function syncMethodButtons() {
    methodGroup.querySelectorAll('.pill').forEach(b => {
        const isActive = b.dataset.method === currentMethod;
        b.classList.toggle('active', isActive);
        b.setAttribute('aria-pressed', isActive ? 'true' : 'false');
    });
}

function applyMethodAvailability() {
    if (!visualIndexReady && VISUAL_METHODS.has(currentMethod)) {
        currentMethod = 'hybrid';
    }
    methodGroup.querySelectorAll('.pill').forEach(b => {
        const needsVisual = VISUAL_METHODS.has(b.dataset.method);
        const unavailable = needsVisual && !visualIndexReady;
        b.disabled = isVecMode || unavailable;
        b.classList.toggle('unavailable', unavailable);
        b.title = unavailable ? '视觉索引未就绪，请先构建 CLIP 视觉索引' : '';
    });
    syncMethodButtons();
}

async function loadSystemStatus() {
    try {
        const resp = await fetch('/api/status');
        const data = await resp.json();
        systemStatus = data;
        visualIndexReady = !!data.visual_index_ready;
        if (visualStatusNote) {
            if (visualIndexReady) {
                visualStatusNote.style.display = 'none';
                visualStatusNote.textContent = '';
            } else {
                visualStatusNote.style.display = 'block';
                visualStatusNote.textContent = `Visual/MM-Hybrid 已禁用：${data.visual_index_message || '视觉索引未就绪'}`;
            }
        }
        applyMethodAvailability();
    } catch(e) {
        console.warn('status load failed', e);
    }
}
loadSystemStatus();

methodGroup.querySelectorAll('.pill').forEach(btn => {
    btn.addEventListener('click', () => {
        if (isVecMode || btn.disabled) return;
        currentMethod = btn.dataset.method;
        syncMethodButtons();
        if (queryInput.value.trim()) doSearch();
    });
});

function setVecMode(on) {
    isVecMode = on;
    vecMathBtn.classList.toggle('active', on);
    vecBar.classList.toggle('show', on);
    if (on) {
        applyMethodAvailability();
        queryInput.placeholder = 'try: smile - happy + cry';
        showToast('🧮 向量运算模式已开启');
        queryInput.focus();
    } else {
        queryInput.placeholder = 'Search emoji… 中文 / English / 日本語';
        vecResultBar.style.display = 'none';
        applyMethodAvailability();
    }
}
vecMathBtn.addEventListener('click', () => setVecMode(!isVecMode));
document.querySelectorAll('.vec-ex-tag').forEach(tag => { tag.addEventListener('click', () => { queryInput.value = tag.dataset.expr; doVecMath(); }); });

// ── triggers ─────────────────────────────────────────────────────────────
// Expanded query pools: pure English, pure Chinese, and some bilingual pairs.
const englishQueries = [
    'coffee','space','detective','rain','fire','fox','cat','dog','happy','music',
    'sun','moon','love','work','sleep','tree','ocean','book','computer','food',
    'mountain','river','city','sky','garden','flower','art','travel','movie','dessert'
];
const chineseQueries = [
    '咖啡','太空','侦探','下雨','火','狐狸','猫','狗','开心','音乐',
    '太阳','月亮','爱心','工作','睡觉','树木','海洋','书本','电脑','食物',
    '山脉','河流','城市','天空','花园','花朵','艺术','旅行','电影','甜点'
];
const bilingualPairs = [
    'coffee 咖啡','space 太空','detective 侦探','rain 下雨','fire 火','fox 狐狸',
    'cat 猫','dog 狗','happy 开心','music 音乐','sun 太阳','moon 月亮',
    'love 爱心','work 工作','sleep 睡觉','tree 树木','ocean 海洋','book 书本',
    'computer 电脑','food 食物'
];
let randomPool = [];
let lastRandomQuery = '';

function getNextRandomQuery() {
    if (randomPool.length === 0) {
        // Choose mode: roughly equal thirds -> English only, Chinese only, or mixed
        const r = Math.random();
        let pool = [];
        if (r < 0.33) {
            pool = [...englishQueries];
        } else if (r < 0.66) {
            pool = [...chineseQueries];
        } else {
            // combine both languages and some bilingual pairs for variety
            pool = [...englishQueries, ...chineseQueries, ...bilingualPairs];
        }

        // optional debug logging
        try { if (window && window.RANDOM_QUERY_DEBUG) console.debug('[getNextRandomQuery] mode r=', r, 'poolSize=', pool.length); } catch(e) {}

        // shuffle
        for (let i = pool.length - 1; i > 0; i--) {
            const j = Math.floor(Math.random() * (i + 1));
            [pool[i], pool[j]] = [pool[j], pool[i]];
        }

        // avoid repeating the very last shown query when possible
        if (pool[pool.length - 1] === lastRandomQuery && pool.length > 1) {
            [pool[pool.length - 1], pool[0]] = [pool[0], pool[pool.length - 1]];
        }
        randomPool = pool;
    }
    lastRandomQuery = randomPool.pop();
    return lastRandomQuery;
}

searchBtn.addEventListener('click', () => isVecMode ? doVecMath() : doSearch());
queryInput.addEventListener('keydown', e => { if (e.key === 'Enter') isVecMode ? doVecMath() : doSearch(); });
randomBtn.addEventListener('click', () => { queryInput.value = getNextRandomQuery(); if(isVecMode)setVecMode(false); doSearch(); });
document.querySelectorAll('.example-tag').forEach(tag => { tag.addEventListener('click', () => { queryInput.value = tag.dataset.q; if(isVecMode)setVecMode(false); doSearch(); }); });

// ── similar ──────────────────────────────────────────────────────────────
similarClose.addEventListener('click', () => { similarPanel.style.display = 'none'; });
async function openSimilar(char, enName) {
    similarTitle.textContent = `🔗 与 ${char} 最相似的 (Bi-Encoder)`;
    similarPanel.style.display = 'block'; similarGrid.innerHTML = `<span>⏳ 加载中…</span>`;
    similarPanel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    try {
        const resp = await fetch('/api/similar', { method: 'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ char, top_k: 12 }) });
        const data = await resp.json();
        if(!resp.ok) {
            similarGrid.innerHTML = `<span class="inline-error">⚠ ${escHtml(data.error)}</span>`;
            return;
        }
        similarGrid.innerHTML = '';
        data.results.forEach(item => {
            const chip = document.createElement('button'); chip.className = 'similar-chip';
            chip.innerHTML = `${item.char} ${escHtml(item.en)} <span class="sim-score">${item.score.toFixed(2)}</span>`;
            chip.onclick = () => { queryInput.value = item.en; setVecMode(false); doSearch(); similarPanel.style.display='none'; };
            similarGrid.appendChild(chip);
        });
    } catch(e) { similarGrid.innerHTML = `<span class="inline-error">Error</span>`; }
}

// ── journey ──────────────────────────────────────────────────────────────
async function fetchJourneyNarrative(path) {
    try {
        const resp = await fetch('/api/journey_narrative', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path })
        });
        const data = await resp.json();
        if (data.narrative) {
            const narDiv = document.createElement('div');
            narDiv.className = 'journey-narrative';
            narDiv.textContent = `💡 AI 释义: ${data.narrative}`;
            journeyRes.appendChild(narDiv);
        }
    } catch(e) {}
}

async function doJourney() {
    const f = journeyFrom.value.trim();
    const t = journeyTo.value.trim();
    if(!f || !t) return;
    journeyBtn.disabled = true;
    journeyRes.innerHTML = '<div class="spinner-ring"></div>';
    try {
        const resp = await fetch('/api/path', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({from_query: f, to_query: t, steps: 5}) });
        const data = await resp.json();
        if(!resp.ok) { journeyRes.innerHTML = `<span class="inline-error">⚠ ${escHtml(data.error)}</span>`; journeyBtn.disabled=false; return; }
        journeyRes.innerHTML = `<div class="journey-path">` + data.path.map((item, i) => `
            <div class="journey-node">
                <span class="jn-char">${item.char}</span>
                <span class="jn-name">${escHtml(item.en)}</span>
            </div>`).join(' → ') + `</div>`;
        
        // Add Phase 7: AI Narrative
        fetchJourneyNarrative(data.path);
        
    } catch(e) { journeyRes.innerHTML = `Error`; }
    journeyBtn.disabled = false;
}
journeyBtn.onclick = doJourney;
document.querySelectorAll('.journey-ex').forEach(btn => { btn.onclick = () => { journeyFrom.value = btn.dataset.from; journeyTo.value = btn.dataset.to; doJourney(); }; });

// ── results ──────────────────────────────────────────────────────────────
function renderModalityBars(scores) {
    if (!scores || typeof scores !== 'object') return '';
    const fields = [
        ['semantic', 'Text'],
        ['visual', 'Visual'],
        ['bm25', 'BM25'],
        ['lexical', 'Lex']
    ];
    const rows = fields.map(([key, label]) => {
        const raw = Number(scores[key]);
        if (!Number.isFinite(raw)) return '';
        const value = Math.max(0, Math.min(raw, 1));
        if (value <= 0.001) return '';
        return `<span class="modality-chip" title="${label}: ${raw.toFixed(3)}"><b>${label}</b>${Math.round(value * 100)}</span>`;
    }).filter(Boolean).join('');
    return rows ? `<div class="modality-bars">${rows}</div>` : '';
}

function renderCard(item, idx) {
    const card = document.createElement('div'); card.className = 'emoji-card';
    card.style.animationDelay = `${idx * 25}ms`; card.dataset.char = item.char;
    card.setAttribute('role', 'listitem');
    card.setAttribute('tabindex', '0');
    card.setAttribute('aria-label', `${item.char} ${item.en}${item.zh ? `，${item.zh}` : ''}，点击复制`);
    const isLiked = likedSet.has(item.char);
    const isExcluded = excludeSet.has(item.char);
    if (isLiked) card.classList.add('feedback-liked');
    if (isExcluded) card.classList.add('feedback-excluded');
    const confidence = Math.max(0, Math.min(Number(item.score) || 0, 1));
    const categoryLabel = item.semantic_category || item.category || '';
    const categoryTitle = item.semantic_category && item.category
        ? `语义分类：${item.semantic_category}；Unicode 分类：${item.category}`
        : categoryLabel;
    card.innerHTML = `
        <div class="card-rank">#${idx + 1}</div>
        <div class="card-char">${item.char}</div>
        <div class="card-en">${escHtml(item.en)}</div>
        <div class="card-zh">${escHtml(item.zh || '')}</div>
        <div class="card-cat" title="${escHtml(categoryTitle)}">${escHtml(categoryLabel)}</div>
        ${renderModalityBars(item.modality_scores)}
        <div class="card-score">${(confidence * 100).toFixed(1)}%</div>
        <div class="card-actions">
            <button class="card-btn like-btn${isLiked ? ' active' : ''}" title="标为相关 (Rocchio PRF)" aria-label="标为相关" aria-pressed="${isLiked ? 'true' : 'false'}">👍</button>
            <button class="card-btn explore-btn" title="查看语义相近" aria-label="查看语义相近">🔗</button>
            <button class="card-btn dislike-btn${isExcluded ? ' active' : ''}" title="去除此项" aria-label="去除此项" aria-pressed="${isExcluded ? 'true' : 'false'}">✕</button>
        </div>
        <div class="card-confidence" style="width: ${confidence * 100}%"></div>
    `;
    const copyEmoji = async () => {
        try {
            await navigator.clipboard.writeText(item.char);
            showToast(`📋 已复制 ${item.char}`);
        } catch(e) {
            showToast('当前浏览器不允许写入剪贴板');
        }
    };
    card.onclick = async e => { 
        if(!e.target.closest('.card-btn')) copyEmoji();
    };
    card.onkeydown = e => {
        if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            copyEmoji();
        }
    };
    
    const likeBtn = card.querySelector('.like-btn');
    if (likeBtn) likeBtn.onclick = e => { 
        e.stopPropagation(); 
        let message;
        if (likedSet.has(item.char)) {
            likedSet.delete(item.char);
            card.classList.remove('feedback-liked');
            likeBtn.classList.remove('active');
            likeBtn.setAttribute('aria-pressed', 'false');
            message = `已取消相关标记：${item.char}`;
        } else {
            likedSet.add(item.char); excludeSet.delete(item.char);
            card.classList.add('feedback-liked');
            card.classList.remove('feedback-excluded');
            likeBtn.classList.add('active');
            likeBtn.setAttribute('aria-pressed', 'true');
            if (dislikeBtn) {
                dislikeBtn.classList.remove('active');
                dislikeBtn.setAttribute('aria-pressed', 'false');
            }
            message = `已标为相关：${item.char}，正在重排`;
        }
        updateExcludeBadge();
        showToast(message);
        queueFeedbackRefresh();
    };
    
    const dislikeBtn = card.querySelector('.dislike-btn');
    if (dislikeBtn) dislikeBtn.onclick = e => { 
        e.stopPropagation(); 
        let message;
        if (excludeSet.has(item.char)) {
            excludeSet.delete(item.char);
            card.classList.remove('feedback-excluded');
            dislikeBtn.classList.remove('active');
            dislikeBtn.setAttribute('aria-pressed', 'false');
            message = `已恢复：${item.char}`;
        } else {
            excludeSet.add(item.char); likedSet.delete(item.char);
            card.classList.add('feedback-excluded');
            card.classList.remove('feedback-liked');
            dislikeBtn.classList.add('active');
            dislikeBtn.setAttribute('aria-pressed', 'true');
            if (likeBtn) {
                likeBtn.classList.remove('active');
                likeBtn.setAttribute('aria-pressed', 'false');
            }
            message = `已排除：${item.char}，正在重排`;
        }
        updateExcludeBadge();
        showToast(message);
        queueFeedbackRefresh();
    };
    
    const exploreBtn = card.querySelector('.explore-btn');
    if (exploreBtn) exploreBtn.onclick = e => { 
        e.stopPropagation(); openSimilar(item.char, item.en); 
    };
    
    return card;
}

function renderCompareHit(item, idx) {
    const score = Number(item.score);
    const scoreText = Number.isFinite(score) ? Math.max(0, Math.min(score, 1)).toFixed(2) : '--';
    return `
        <li class="mm-hit">
            <span class="mm-rank">${idx + 1}</span>
            <span class="mm-char">${item.char}</span>
            <span class="mm-name">${escHtml(item.en)}</span>
            <span class="mm-score">${scoreText}</span>
        </li>
    `;
}

function getMultimodalCompareKey(query) {
    const category = categorySelect ? categorySelect.value : 'all';
    return JSON.stringify({ query, category });
}

async function renderMultimodalComparison(query) {
    if (!mmCompare || !visualIndexReady || isVecMode) {
        if (mmCompare) mmCompare.style.display = 'none';
        return;
    }
    const cacheKey = getMultimodalCompareKey(query);
    if (mmCompareCache.key === cacheKey && mmCompareCache.html) {
        mmCompare.innerHTML = mmCompareCache.html;
        mmCompare.style.display = 'block';
        return;
    }
    mmCompare.style.display = 'block';
    mmCompare.innerHTML = `
        <div class="mm-compare-head">
            <span>多模态解释</span>
            <small>Text-only / Visual-only / MM-Hybrid Top-5</small>
        </div>
        <div class="mm-compare-loading">对比计算中...</div>
    `;
    try {
        const resp = await fetch('/api/multimodal_compare', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                query,
                top_k: 5,
                category: categorySelect ? categorySelect.value : 'all'
            })
        });
        const data = await resp.json();
        if (getMultimodalCompareKey(query) !== cacheKey) return;
        if (!resp.ok) {
            mmCompare.style.display = 'none';
            return;
        }
        const columns = (data.columns || []).map(col => `
            <div class="mm-column">
                <div class="mm-column-title">${escHtml(col.label)}</div>
                <ol class="mm-list">
                    ${(col.results || []).map(renderCompareHit).join('')}
                </ol>
            </div>
        `).join('');
        mmCompare.innerHTML = `
            <div class="mm-compare-head">
                <span>多模态解释</span>
                <small>Text-only / Visual-only / MM-Hybrid Top-5</small>
            </div>
            <div class="mm-columns">${columns}</div>
        `;
        mmCompareCache = { key: cacheKey, html: mmCompare.innerHTML };
    } catch(e) {
        mmCompare.style.display = 'none';
    }
}

function updateExcludeBadge() {
    if (!excludeBadge || !excludeCount) return;
    let totalFeedback = excludeSet.size + likedSet.size;
    if (totalFeedback > 0) { 
        excludeCount.textContent = `相关 ${likedSet.size} · 排除 ${excludeSet.size}`;
        excludeBadge.style.display = 'inline-flex'; 
    }
    else { excludeBadge.style.display = 'none'; }
}
function queueFeedbackRefresh() {
    clearTimeout(_feedbackRefreshTimer);
    _feedbackRefreshTimer = setTimeout(() => {
        if (queryInput.value.trim()) isVecMode ? doVecMath() : doSearch();
    }, 120);
}
if (clearExclude) {
    clearExclude.onclick = () => {
        excludeSet.clear();
        likedSet.clear();
        updateExcludeBadge();
        showToast('已清空反馈标记');
        if(lastQuery) queueFeedbackRefresh();
    };
}

// ── API logic ────────────────────────────────────────────────────────────
async function doSearch() {
    const query = queryInput.value.trim(); if (!query) return;
    if (_abortCtrl) _abortCtrl.abort();
    const compareKey = getMultimodalCompareKey(query);
    const keepMultimodal = mmCompareCache.key === compareKey && !!mmCompareCache.html && visualIndexReady && !isVecMode;
    _abortCtrl = new AbortController(); uiLoading({ keepMultimodal }); lastQuery = query;
    try {
        const resp = await fetch('/api/search', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({ query, method: currentMethod, top_k: parseInt(topkSelect.value), category: categorySelect ? categorySelect.value : 'all', debug: debugToggle ? debugToggle.checked : false, exclude: [...excludeSet], liked: [...likedSet] }), signal: _abortCtrl.signal });
        const data = await resp.json(); uiDone();
        if (!resp.ok) { showError(data.error); return; }
        pushHistory(query); renderResults(data.results, query, data.sim_matrix);
        renderMultimodalComparison(query);
        renderDebug(data.debug);
        if (methodBadge) methodBadge.textContent = (data.method || currentMethod).toUpperCase();
        statusText.textContent = `找到 ${data.count} 个 · ${data.elapsed}ms`; statusBar.style.display = 'flex';
    } catch (e) { if(e.name!=='AbortError') { uiDone(); showError(e.message); } }
}

async function doVecMath() {
    const expr = queryInput.value.trim(); if (!expr) return;
    if (_abortCtrl) _abortCtrl.abort();
    _abortCtrl = new AbortController(); uiLoading();
    try {
        const resp = await fetch('/api/vector_math', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({ expression: expr, top_k: parseInt(topkSelect.value), exclude: [...excludeSet], liked: [...likedSet] }), signal: _abortCtrl.signal });
        const data = await resp.json(); uiDone();
        if (!resp.ok) { showError(data.error); return; }
        renderResults(data.results, expr, data.sim_matrix);
        if (mmCompare) mmCompare.style.display = 'none';
        statusBar.style.display = 'flex';
    } catch (e) { if(e.name!=='AbortError') { uiDone(); showError(e.message); } }
}

function renderResults(results, query, sim_matrix) {
    resultsGrid.innerHTML = ''; lastResults = results;
    if (!results.length) { emptyState.style.display='block'; starSection.style.display='none'; return; }
    emptyState.style.display='none';
    results.forEach((item, i) => resultsGrid.appendChild(renderCard(item, i)));
    starSection.style.display = 'block';
    const starWrap = document.getElementById('star-map-wrap');
    if (starWrap) {
        if (window._starObserver) window._starObserver.disconnect();
        window._starObserver = new IntersectionObserver((entries) => {
            const target = entries[0].target;
            if (entries[0].isIntersecting && target.clientWidth > 100) {
                if(window._starMap) window._starMap.destroy();
                try {
                    window._starMap = new StarMapInteractive(target, results, query, sim_matrix);
                } catch(e) { console.error("StarMap init error:", e); }
                window._starObserver.disconnect();
            }
        }, { threshold: 0.1 });
        window._starObserver.observe(starWrap);
    }
}

function uiLoading(options = {}) {
    emptyState.style.display='none';
    statusBar.style.display='none';
    resultsGrid.innerHTML='';
    spinner.style.display='flex';
    starSection.style.display='none';
    if(mmCompare && !options.keepMultimodal) mmCompare.style.display='none';
    renderDebug(null);
}
function uiDone() { spinner.style.display='none'; }
function showError(m) { statusText.textContent=`⚠ ${m}`; statusBar.style.display='flex'; showToast(m); }
function escHtml(s) { return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function renderDebug(debug) {
    if (!debugPanel) return;
    if (!debug || !(debugToggle && debugToggle.checked)) {
        debugPanel.style.display = 'none';
        debugPanel.textContent = '';
        return;
    }
    debugPanel.style.display = 'block';
    debugPanel.textContent = JSON.stringify(debug, null, 2);
}

// ═════════════════════════════════════════════════════════════════════
//  ★ STABLE RADIAL STAR MAP (Redesigned: Semantic Galaxy)
// ═════════════════════════════════════════════════════════════════════
class StarMapInteractive {
    constructor(container, results, query, sim_matrix) {
        this.container = container;
        this.results   = results.slice(0, 40);
        this.query     = query || "Query";
        this.simMatrix = sim_matrix || [];
        this.nodes     = [];
        this.domNodes  = []; 
        this.w = this.container.clientWidth || 800; 
        this.h = this.container.clientHeight || 520;
        if (this.w < 100) { this.w = 800; this.h = 520; }
        this.cx = this.w / 2; this.cy = this.h / 2;
        this.initDOM();
        this.layout();
        this.updateLabels();
    }

    async updateLabels() {
        if (!mapLabelsContainer) return;
        mapLabelsContainer.innerHTML = '';
        if (this.results.length < 5) return;

        try {
            const resp = await fetch('/api/map_labels', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ results: this.results })
            });
            const data = await resp.json();
            if (data.labels && data.labels.length) {
                // Determine 3 distinct regions in the galaxy to place giant background text labels
                const regions = [
                    { x: this.w * 0.2, y: this.h * 0.25, rotate: -15, color: 'rgba(255, 255, 255, 0.08)' },
                    { x: this.w * 0.8, y: this.h * 0.3, rotate: 10, color: 'rgba(59, 130, 246, 0.08)' },
                    { x: this.w * 0.5, y: this.h * 0.75, rotate: -5, color: 'rgba(139, 92, 246, 0.08)' }
                ];

                data.labels.forEach((label, i) => {
                    const el = document.createElement('div');
                    el.textContent = label;
                    const r = regions[i % regions.length];
                    Object.assign(el.style, {
                        position: 'absolute',
                        left: `${r.x}px`,
                        top: `${r.y}px`,
                        transform: `translate(-50%, -50%) rotate(${r.rotate}deg)`,
                        fontSize: '3rem',
                        fontWeight: '900',
                        fontFamily: 'var(--font-sans)',
                        color: r.color,
                        whiteSpace: 'nowrap',
                        pointerEvents: 'none',
                        zIndex: '5',
                        textShadow: `0 0 20px ${r.color.replace('0.08', '0.2')}`,
                        letterSpacing: '5px',
                        animation: 'pulseGlow 8s infinite alternate'
                    });
                    mapLabelsContainer.appendChild(el);
                });
            }
        } catch(e) { console.error("Map labels error:", e); }
    }    destroy() { const w = this.container.querySelector('.starmap-content'); if(w) w.remove(); }
    initDOM() {
        this.destroy();
        this.wrapper = document.createElement('div');
        this.wrapper.className = 'starmap-content';
        Object.assign(this.wrapper.style, { position:'absolute', top:'0', left:'0', width:'100%', height:'100%', overflow:'hidden', pointerEvents:'none', zIndex:'10' });
        this.canvas = document.createElement('canvas');
        this.canvas.width = this.w; this.canvas.height = this.h;
        Object.assign(this.canvas.style, { position:'absolute', top:'0', left:'0', width:'100%', height:'100%', zIndex:'1' });
        this.ctx = this.canvas.getContext('2d');
        this.wrapper.appendChild(this.canvas);
        this.container.appendChild(this.wrapper);
    }
    layout() {
        if(!this.results.length) return;
        const inner = 85, outer = Math.min(this.cx, this.cy) - 45;
        
        let hasRealSim = this.simMatrix && this.simMatrix.length > 0;
        
        this.nodes = this.results.map((item, i) => {
            // Default to index-based norm if no matrix
            let simToQuery = 1 - (i / this.results.length);
            
            // If matrix exists, row 0 is query, so item i is index i+1
            if (hasRealSim && this.simMatrix[0] && this.simMatrix[0][i+1] !== undefined) {
                simToQuery = this.simMatrix[0][i+1];
            }
            
            // simToQuery is ~0.4 (far) to 1.0 (exact match)
            // Distance is inverted: high sim = low radius
            let distNorm = Math.max(0, Math.min(1, 1 - simToQuery)); 
            if (!hasRealSim) distNorm = i / this.results.length;

            return { 
                item, 
                r: inner + distNorm * (outer - inner), 
                angle: (i/this.results.length)*Math.PI*2, 
                idx: i, 
                size: 20 + (simToQuery)*10,
                sim: simToQuery
            };
        });
        if(this.simMatrix.length) {
            for(let it=0; it<20; it++) {
                this.nodes.forEach(n1 => {
                    this.nodes.forEach(n2 => {
                        if(n1===n2) return;
                const sim = this.simMatrix[n1.idx + 1]?.[n2.idx + 1] ?? 0;
                        if(sim > 0.7) {
                            let d = n2.angle - n1.angle;
                            while(d > Math.PI) d -= Math.PI*2; while(d < -Math.PI) d += Math.PI*2;
                            n1.angle += d*0.15*(sim-0.7); n2.angle -= d*0.15*(sim-0.7);
                        }
                    });
                });
            }
        }
        for(let it=0; it<15; it++) {
            this.nodes.forEach(n1 => {
                this.nodes.forEach(n2 => {
                    if(n1===n2) return;
                    const x1=Math.cos(n1.angle)*n1.r, y1=Math.sin(n1.angle)*n1.r, x2=Math.cos(n2.angle)*n2.r, y2=Math.sin(n2.angle)*n2.r;
                    const dx=x1-x2, dy=y1-y2, dist=Math.sqrt(dx*dx+dy*dy), minD=n1.size+n2.size+12;
                    if(dist<minD) { const p=(minD-dist)/n1.r*0.6; n1.angle+=p; n2.angle-=p; }
                });
            });
        }
        this.render();
    }
    render() {
        this.ctx.clearRect(0, 0, this.w, this.h);
        const c = document.createElement('div');
            Object.assign(c.style, { position:'absolute', left:`${this.cx-50}px`, top:`${this.cy-50}px`, width:'100px', height:'100px', borderRadius:'50%', background:'radial-gradient(circle, #1677ff 0%, #0057d966 100%)', display:'flex', alignItems:'center', justifyContent:'center', color:'#fff', fontSize:'13px', fontWeight:'700', zIndex:'100', textAlign:'center', pointerEvents:'none' });
        c.textContent = this.query; this.wrapper.appendChild(c);
        this.nodes.forEach(n => {
            const x = this.cx+Math.cos(n.angle)*n.r, y = this.cy+Math.sin(n.angle)*n.r;
            const el = document.createElement('div');
            el.className = 'star-node';
            Object.assign(el.style, { 
                position:'absolute', left:`${x-n.size}px`, top:`${y-n.size}px`, 
                width:`${n.size*2}px`, height:`${n.size*2}px`, 
                borderRadius:'50%', background:'#1e1932f2', 
                border:`2px solid hsla(${(n.r/this.cx)*240}, 70%, 70%, 0.8)`, 
                display:'flex', alignItems:'center', justifyContent:'center', 
                fontSize:`${n.size*0.9}px`, cursor:'pointer', pointerEvents:'auto', zIndex:'50',
                fontFamily: '"Apple Color Emoji", "Segoe UI Emoji", "Noto Color Emoji", sans-serif',
                textShadow: '0 0 2px rgba(255,255,255,0.5)'
            });
            el.textContent = n.item.char;
            el.onmouseenter = () => el.style.transform = 'scale(1.3)'; el.onmouseleave = () => el.style.transform = 'none';
            el.onclick = () => { const card = [...resultsGrid.querySelectorAll('.emoji-card')].find(c => c.dataset.char === n.item.char); if(card) { card.scrollIntoView({ behavior: 'smooth', block: 'center' }); card.classList.add('highlighted'); setTimeout(()=>card.classList.remove('highlighted'),2000); } };
            this.wrapper.appendChild(el);
            this.domNodes.push({ char: n.item.char, en: n.item.en.toLowerCase(), zh: n.item.zh, el });
            this.ctx.strokeStyle = `rgba(140, 100, 255, ${0.1 + (1 - n.r/this.cx)*0.3})`;
            this.ctx.beginPath(); this.ctx.moveTo(this.cx, this.cy); this.ctx.lineTo(x, y); this.ctx.stroke();
        });
    }
    triggerPulse(query) {
        this.domNodes.forEach(node => {
            if (node.en.includes(query) || node.zh.includes(query)) {
                node.el.classList.add('pulsing');
                setTimeout(() => node.el.classList.remove('pulsing'), 3000);
            }
        });
    }
}

// ── eval ─────────────────────────────────────────────────────────────────
runEvalBtn.onclick = () => {
    runEvalBtn.disabled = true; runEvalBtn.textContent = '🏁 激战中...'; 
    evalResults.style.display = 'block';
    
    // Clear previous results
    evalTableWrap.innerHTML = '';
    document.getElementById('arena-lanes').innerHTML = '';
    document.getElementById('stream-content').innerHTML = '';
    document.getElementById('ai-jury-results').style.display = 'none';
    if(evalChartObj) evalChartObj.destroy();
    if(window.evalRadarObj) window.evalRadarObj.destroy();

    const icons = { 'bm25': 'BM', 'tfidf': 'TF', 'dense': 'DE', 'bi_encoder': 'BE', 'hnsw': 'HS', 'rerank': 'RR', 'hybrid': 'HY', 'visual': 'VI', 'mm_hybrid': 'MM' };
    const lanesWrap = document.getElementById('arena-lanes');
    const statusText = document.getElementById('arena-status');
    const queryDisplay = document.getElementById('arena-current-query');
    const streamContent = document.getElementById('stream-content');
    statusText.textContent = '( 0 / ? )';
    queryDisplay.textContent = '正在连接评测流...';
    
    let totalQ = 0;
    let raceSeed = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    const es = new EventSource(`/api/eval?seed=${encodeURIComponent(raceSeed)}&sample_size=${EVAL_SAMPLE_SIZE}`);
    es.onopen = () => {
        queryDisplay.textContent = '评测流已连接，等待初始化...';
    };
    
    es.onmessage = (e) => {
        try {
            const data = JSON.parse(e.data);
            if (data.type === 'init') {
                totalQ = data.total_queries;
                raceSeed = data.race_seed || raceSeed;
                const breakdown = data.sample_breakdown || {};
                const breakdownText = Object.keys(breakdown).length
                    ? `; mm ${breakdown.multimodal || 0}, core ${breakdown.core || 0}, expanded ${breakdown.expanded || 0}`
                    : '';
                statusText.title = `Race seed: ${raceSeed}; ${data.order || 'sample'}; sample ${data.sample_size || totalQ}/${data.total_pool || totalQ}${breakdownText}`;
                statusText.textContent = `( 0 / ${totalQ} )`;
                queryDisplay.textContent = `Balanced sample ${data.sample_size || totalQ}/${data.total_pool || totalQ}${breakdownText}. Warming up first query...`;
                data.methods.forEach(m => {
                    lanesWrap.innerHTML += `
                        <div class="lane" id="lane-${m}">
                            <div class="lane-name">${icons[m] || '🤖'} ${m.toUpperCase()}</div>
                            <div class="lane-track">
                                <div class="lane-car car-${m}" id="car-${m}" style="width: 0%;">
                                    <span class="lane-emoji" id="emoji-${m}">🏎️</span>
                                </div>
                            </div>
                            <div class="lane-score" id="score-${m}">0.000</div>
                        </div>
                    `;
                });
            } else if (data.type === 'status') {
                queryDisplay.textContent = data.message || '评测运行中...';
            } else if (data.type === 'race_update') {
                statusText.textContent = `( ${data.query_idx + 1} / ${totalQ} )`;
                queryDisplay.textContent = `Target: "${data.query}"`;
                
                // Add to live stream
                let emojis = Object.keys(data.updates).map(m => data.updates[m].top_hit).join('');
                const pill = document.createElement('div');
                pill.className = 'stream-pill';
                pill.innerHTML = `<span class="pill-query">${escHtml(data.query)}</span><span class="pill-hit">${emojis}</span>`;
                streamContent.prepend(pill);
                if (streamContent.children.length > 20) streamContent.lastChild.remove();

                // Move cars
                const pct = Math.floor(((data.query_idx + 1) / totalQ) * 100);
                const methodNames = Object.keys(data.updates);
                const maxMap = Math.max(...methodNames.map(m => Number(data.updates[m].metrics.MAP) || 0), 0.0001);
                methodNames.forEach(m => {
                    const update = data.updates[m];
                    const mapScore = Number(update.metrics.MAP) || 0;
                    const relativeScore = maxMap > 0 ? mapScore / maxMap : 0;
                    const lanePct = Math.min(100, Math.max(4, pct * (0.25 + 0.75 * relativeScore)));
                    const car = document.getElementById(`car-${m}`);
                    const lane = document.getElementById(`lane-${m}`);
                    const score = document.getElementById(`score-${m}`);
                    const emojiNode = document.getElementById(`emoji-${m}`);
                    if(car) {
                        car.style.width = `${lanePct.toFixed(1)}%`;
                        if (lane) lane.classList.toggle('lane-leader', relativeScore >= 0.999 && mapScore > 0);
                        if (score) score.textContent = mapScore.toFixed(3);
                        if (emojiNode) emojiNode.textContent = update.top_hit || '🏎️';
                    }
                });

            } else if (data.type === 'done') {
                queryDisplay.textContent = '🏁 比赛结束！(Race Finished)';
                es.close();
                setTimeout(() => renderEvalResults(data), 500);
            } else if (data.type === 'error') {
                es.close();
                queryDisplay.textContent = `⚠ 引擎故障: ${data.error}`;
                runEvalBtn.disabled = false; runEvalBtn.textContent = '重新比赛 ✦';
            }
        } catch(err) {
            console.error('SSE parsing error:', err);
        }
    };
    
    es.onerror = (err) => {
        es.close();
        queryDisplay.textContent = `⚠ 赛道断开连接`;
        runEvalBtn.disabled = false; runEvalBtn.textContent = '🏁 开启算力角斗场 ✦';
    };
};

function renderEvalResults(data) {
    evalTableWrap.innerHTML = '';
    const t = document.createElement('table'); t.className = 'eval-table';
    
    const headers = ['Method', 'MAP', 'MRR', 'P@5', 'P@10', 'R@5', 'R@10', 'F1@5', 'F1@10', 'NDCG@5', 'NDCG@10'];
    const thead = document.createElement('thead');
    const trHead = document.createElement('tr');
    headers.forEach(h => { const th = document.createElement('th'); th.textContent = h; trHead.appendChild(th); });
    thead.appendChild(trHead); t.appendChild(thead);
    
    const tbody = document.createElement('tbody');
    
    // Find the max value for each metric column to highlight
    const maxVals = {};
    headers.forEach(h => {
        if (h !== 'Method') {
            maxVals[h] = Math.max(...data.results.map(r => r.metrics[h] || 0));
        }
    });

    data.results.forEach(r => {
        const tr = document.createElement('tr');
        headers.forEach(h => {
            const td = document.createElement('td');
            if (h === 'Method') { 
                td.textContent = r.method.toUpperCase(); 
            } else { 
                const val = r.metrics[h] || 0;
                td.textContent = val.toFixed(4);
                // Highlight if it's the max value in the column
                if (val >= maxVals[h] && val > 0) {
                    td.classList.add('best-cell');
                }
            }
            tr.appendChild(td);
        });
        tbody.appendChild(tr);
    });
    t.appendChild(tbody);
    evalTableWrap.appendChild(t);
    renderFailureCases(data.failure_cases || []);

    if(evalChartObj) evalChartObj.destroy();
    
    const labels = data.results.map(r => r.method.toUpperCase());
    const dsMRR = { type: 'bar', label: 'MRR', data: data.results.map(r=>r.metrics.MRR), backgroundColor: '#0071e3', yAxisID: 'y' };
    const dsMAP = { type: 'bar', label: 'MAP', data: data.results.map(r=>r.metrics.MAP), backgroundColor: '#10b981', yAxisID: 'y' };
    const dsF1_10 = { type: 'line', label: 'F1@10', data: data.results.map(r=>r.metrics['F1@10']), borderColor: '#8b5cf6', backgroundColor: '#8b5cf6', borderWidth: 2, fill: false, yAxisID: 'y' };
    const dsP_10 = { type: 'line', label: 'P@10', data: data.results.map(r=>r.metrics['P@10']), borderColor: '#f59e0b', backgroundColor: '#f59e0b', borderWidth: 2, fill: false, borderDash: [5,5], yAxisID: 'y' };
    
    evalChartObj = new Chart(document.getElementById('eval-bar-chart'), { 
        data: { labels, datasets: [dsMRR, dsMAP, dsF1_10, dsP_10] }, 
        options: { 
            responsive: true, maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            scales: { y: { beginAtZero: true, max: 1.0 } },
            plugins: { title: { display: true, text: '核心指标对比 (MAP / MRR / Precision)' } }
        } 
    });

    if(window.evalRadarObj) window.evalRadarObj.destroy();
    const radarDatasets = data.results.map((r, i) => {
        const colors = ['#0071e3', '#10b981', '#8b5cf6', '#f59e0b', '#ef4444'];
        return {
            label: r.method.toUpperCase(),
            data: [r.metrics.MAP, r.metrics.MRR, r.metrics['P@10'], r.metrics['R@10'], r.metrics['NDCG@10']],
            backgroundColor: colors[i % colors.length] + '33',
            borderColor: colors[i % colors.length],
            pointBackgroundColor: colors[i % colors.length]
        };
    });
    window.evalRadarObj = new Chart(document.getElementById('eval-radar-chart'), {
        type: 'radar',
        data: { labels: ['MAP', 'MRR', 'P@10', 'R@10', 'NDCG@10'], datasets: radarDatasets },
        options: {
            responsive: true, maintainAspectRatio: false,
            scales: { r: { min: 0, max: 1.0, ticks: { display: false } } },
            plugins: { title: { display: true, text: '综合能力雷达图' } }
        }
    });
    evalResults.style.display = 'block';
    
    // Phase 9: Global AI Committee Evaluation
    runAiCommittee(data.results, data.sample_query, data.race_seed);
    
    runEvalBtn.disabled = false; runEvalBtn.textContent = '重新评测 ✦';
}

function renderFailureCases(cases) {
    const wrap = document.getElementById('eval-failures');
    if (!wrap) return;
    if (!cases.length) {
        wrap.innerHTML = '';
        return;
    }
    const rows = cases.map(item => {
        const methods = item.methods || {};
        const methodText = Object.keys(methods).map(m => {
            const s = methods[m];
            const rank = s.first_rank || '-';
            return `${m}: hit=${s.hits_at_10}, first=${rank}`;
        }).join(' | ');
        return `<tr><td>${escHtml(item.id)}</td><td>${escHtml(item.bucket || '-')}</td><td>${escHtml(item.query)}</td><td>${item.relevant_count}</td><td>${escHtml(item.target_method || 'mm_hybrid')}</td><td>${escHtml(methodText)}</td></tr>`;
    }).join('');
    wrap.innerHTML = `
        <h4>失败案例分析 (Failure Analysis)</h4>
        <table class="eval-table failure-table">
            <thead><tr><th>ID</th><th>Bucket</th><th>Query</th><th>Relevant</th><th>Focus</th><th>Methods</th></tr></thead>
            <tbody>${rows}</tbody>
        </table>
    `;
}

async function runAiCommittee(results, query, raceSeed) {
    const box = document.getElementById('ai-jury-results');
    const loadingWrap = document.getElementById('jury-loading');
    const contentWrap = document.getElementById('jury-verdict-content');

    if(!box || !loadingWrap || !contentWrap) return;

    box.style.display = 'block';
    loadingWrap.style.display = 'flex';
    contentWrap.style.display = 'none';

    try {
        const resp = await fetch('/api/ai_committee_eval', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ metrics: results, query, race_seed: raceSeed })
        });
        const data = await resp.json();

        loadingWrap.style.display = 'none';
        contentWrap.style.display = 'block';

        if (data.verdict && typeof data.verdict === 'object' && !data.verdict.error) {
            const v = data.verdict;
            const mvp = v.mvp || {};
            const score = Number(mvp.score);
            const safeScore = Number.isFinite(score) ? score : 0;

            // Determine status class based on score
            let statusClass = 'status-neutral';
            if (safeScore > 0.7) statusClass = 'status-success';
            else if (safeScore < 0.35) statusClass = 'status-warning';
            const diagnostics = Array.isArray(v.diagnostics) ? v.diagnostics.slice(0, 3) : [];

            let html = `
                <div class="consensus-top-row">
                    <div class="query-profile-card mvp-card ${statusClass}">
                      <div class="qpc-header mvp-title">🏆 首席架构师钦定 MVP</div>
                      <div class="qpc-body mvp-body">
                        <div class="qpc-val mvp-name">
                            ${escHtml(mvp.name || '--')} 
                            <span class="mvp-score-pill">MAP: ${safeScore.toFixed(3)}</span>
                        </div>
                        <div class="qpc-reason">
                            " ${escHtml(compactText(mvp.reason || '--', 90))} "
                        </div>
                      </div>
                    </div>
                </div>
                <div class="jury-verdict jury-verdict-list">
            `;

            if (diagnostics.length) {
                diagnostics.forEach(diag => {
                    html += `
                        <div class="jury-card jury-card-wide">
                            <div class="jury-persona jury-persona-title">
                                ${escHtml(compactText(diag.title, 24))}
                            </div>
                            <div class="jury-opinion jury-opinion-copy">
                                ${escHtml(compactText(diag.content, 120))}
                            </div>
                        </div>
                    `;
                });
            }
            html += `</div>`;

            contentWrap.innerHTML = html;
        } else {
            const errText = data.verdict && data.verdict.error ? data.verdict.error : '架构师返回异常。';
            contentWrap.innerHTML = `<div class="jury-opinion diag-error">⚠️ ${escHtml(errText)}</div>`;
        }
    } catch(e) {
        loadingWrap.style.display = 'none';
        contentWrap.style.display = 'block';
        contentWrap.innerHTML = `<div class="jury-opinion diag-error">⚠️ 架构师连接失败 (${e.message})</div>`;
    }
}
async function prepareEvalDiagnosis(results, query) {
    const table = document.querySelector('.eval-table tbody');
    if(!table) return;
    const rows = table.querySelectorAll('tr');
    rows.forEach((row, i) => {
        const td = document.createElement('td');
        const btn = document.createElement('button');
        btn.className = 'mini-btn'; btn.textContent = 'AI 诊断';
        btn.onclick = async () => {
            btn.disabled = true; btn.textContent = '诊断中...';
            try {
                const methodA = results[i].method;
                const methodB = results[0].method;
                const res = await fetch('/api/eval_diagnose', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ query, method_a: methodA, results_a: results[i].results_sample || [], method_b: methodB, results_b: results[0].results_sample || [] })
                });
                const data = await res.json();
                if (data.diagnosis) {
                    showToast(`🤖 AI 诊断: ${data.diagnosis.substring(0, 50)}...`, 8000);
                    // Also console log the full report
                    console.log(`🤖 AI 诊断详细报告 (${methodA}):`, data.diagnosis);
                }
            } catch(e) { console.error(e); }
            btn.disabled = false; btn.textContent = 'AI 诊断';
        };
        td.appendChild(btn);
        row.appendChild(td);
    });
}

// ── storyboard ──────────────────────────────────────────────────────────
async function generateStoryboard() {
    const text = storyInput.value.trim();
    if (!text) return;
    const useAi = storyAiToggle.checked;
    
    storyBtn.disabled = true; storyBtn.textContent = '编演中...';
    storySequence.innerHTML = '';
    storyReasoning.classList.remove('show');
    storyReasoning.innerHTML = '';

    try {
        const resp = await fetch('/api/storyboard', { 
            method:'POST', 
            headers:{'Content-Type':'application/json'}, 
            body:JSON.stringify({ text, use_ai: useAi }) 
        });
        const data = await resp.json();
        if(!resp.ok) { storySequence.innerHTML = `<span class="inline-error">⚠ ${escHtml(data.error)}</span>`; }
        else {
            if (useAi && data.sequence.length) {
                storyReasoning.innerHTML = `<strong>🤖 Agentic IR 推理：</strong>AI 分镜师已将叙事提炼为 ${data.sequence.length} 个关键视觉分镜，每个分镜均通过语义检索引擎匹配最佳 Emoji。`;
                storyReasoning.classList.add('show');
            }
            data.sequence.forEach((item, i) => {
                setTimeout(() => {
                    const frame = document.createElement('div');
                    frame.className = 'story-frame';
                    const reasoningHint = item.reasoning ? `<span class="sf-reasoning" title="${escHtml(item.reasoning)}">🔍</span>` : '';
                    frame.innerHTML = `
                        <span class="sf-char">${item.emoji}</span>
                        <span class="sf-seg">${escHtml(item.segment)}</span>
                        ${reasoningHint}
                    `;
                    frame.onclick = () => { queryInput.value = item.en; doSearch(); };
                    storySequence.appendChild(frame);
                }, i * 150);
            });
        }
    } catch(e) { storySequence.innerHTML = `Error: ${e.message}`; }
    storyBtn.disabled = false; storyBtn.textContent = '编绘剧本 🎞️';
}
storyBtn.onclick = generateStoryboard;

// ── pulse ──────────────────────────────────────────────────────────────
async function updatePulse() {
    try {
        const resp = await fetch('/api/pulse');
        const data = await resp.json();
        if (data.pulse_active) {
            pulseActive.textContent = 'Active 🔥';
            pulseActive.style.color = 'var(--rose-lt)';
            if (data.recent_queries.length) {
                pulseTrends.innerHTML = data.recent_queries.reverse().map(q => `<span>#${escHtml(q)}</span> `).join(' ');
            }
            // Trigger pulses on star map nodes if they exist
            if (window._starMap && data.recent_queries.length) {
                const latest = data.recent_queries[0].toLowerCase();
                window._starMap.triggerPulse(latest);
            }
        }
    } catch(e) { console.error('Pulse error:', e); }
}
setInterval(updatePulse, 8000);
updatePulse();

queryInput.focus();

// ── Magic Inspiration ──
function initMagicButtons() {
    const btns = document.querySelectorAll('.magic-btn');
    btns.forEach(btn => {
        btn.onclick = async () => {
            const genre = btn.dataset.genre;
            const oldText = btn.textContent;
            btn.style.opacity = '0.5';
            btn.disabled = true;
            btn.textContent = '生成中...';
            try {
                const resp = await fetch('/api/magic_story', {
                    method:'POST',
                    headers:{'Content-Type':'application/json'},
                    body:JSON.stringify({ genre })
                });
                const data = await resp.json();
                if(data.story) {
                    storyInput.value = data.story;
                    showToast("✨ 灵感已注入");
                } else {
                    showToast(data.error || '灵感生成失败');
                }
            } catch(e) {
                showToast("灵感生成失败，请稍后重试");
            }
            btn.textContent = oldText;
            btn.disabled = false;
            btn.style.opacity = '1';
        };
    });
}
initMagicButtons();
