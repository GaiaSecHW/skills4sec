/**
 * Skillstore Static Site - Client-side JS
 * Handles: SPA routing, search/filter, copy-to-clipboard, mobile menu, toast
 */

(function () {
  'use strict';

  /* ===================== DATA ===================== */
  let SKILLS    = [];
  let HARNESSES = [];
  let AGENTS    = [];
  let EVOL_SUMMARY = {};
  let EVOL_LOGS = [];

  /* ===================== ROUTER ===================== */
  function getRoute() {
    const hash = location.hash.replace(/^#\/?/, '');
    if (!hash) return { page: 'home' };
    if (hash === 'browse' || hash.startsWith('browse?')) return { page: 'browse' };
    if (hash.startsWith('skill/')) return { page: 'detail', slug: hash.slice(6) };
    if (hash === 'harnesses' || hash.startsWith('harnesses?')) return { page: 'harnesses' };
    if (hash.startsWith('harness/')) return { page: 'harness-detail', slug: hash.slice(8) };
    if (hash === 'agents' || hash.startsWith('agents?')) return { page: 'agents' };
    if (hash.startsWith('agent/')) return { page: 'agent-detail', slug: hash.slice(6) };
    if (hash === 'submit') return { page: 'submit' };
    if (hash === 'schema-spec') return { page: 'schema-spec' };
    if (hash === 'evolution') return { page: 'evolution' };
    return { page: 'home' };
  }

  // FIX: global delegated handler for ALL [data-href] elements (nav, footer, mobile menu, cards)
  document.addEventListener('click', function (e) {
    const link = e.target.closest('[data-href]');
    if (link) {
      e.preventDefault();
      const href = link.dataset.href;
      if (href !== undefined) {
        location.hash = href.replace(/^#\/?/, '');
      }
    }
  });

  window.addEventListener('hashchange', render);
  window.addEventListener('load', function () {
    Promise.all([loadSkills(), loadHarnesses(), loadAgents(), loadEvol()]).then(render);
  });

  /* ===================== DATA LOADING ===================== */
  async function loadSkills() {
    try {
      const res = await fetch('data/skills.json');
      SKILLS = await res.json();
    } catch (e) {
      console.error('Failed to load skills:', e);
      SKILLS = [];
    }
  }

  async function loadHarnesses() {
    try {
      const res = await fetch('data/harnesses.json');
      HARNESSES = await res.json();
    } catch (e) {
      HARNESSES = [];
    }
  }

  async function loadAgents() {
    try {
      const res = await fetch('data/agents.json');
      AGENTS = await res.json();
    } catch (e) {
      AGENTS = [];
    }
  }

  async function loadEvol() {
    try { const r = await fetch('data/evol/summary.json'); EVOL_SUMMARY = await r.json(); }
    catch (e) { EVOL_SUMMARY = {}; }
    try { const r = await fetch('data/evol/logs.json'); EVOL_LOGS = await r.json(); }
    catch (e) { EVOL_LOGS = []; }
  }

  /* ===================== RENDER DISPATCH ===================== */
  function render() {
    const route = getRoute();
    const main = document.getElementById('main-content');
    if (!main) return;

    updateNavActive(route.page);

    if (route.page === 'home') {
      main.innerHTML = renderHomePage();
      bindHomeEvents();
    } else if (route.page === 'browse') {
      main.innerHTML = renderBrowsePage();
      bindBrowseEvents();
    } else if (route.page === 'detail') {
      const skill = SKILLS.find(s => s.slug === route.slug);
      main.innerHTML = skill ? renderDetailPage(skill) : renderNotFound();
      if (skill) bindDetailEvents();
    } else if (route.page === 'harnesses') {
      main.innerHTML = renderHarnessesPage();
      bindHarnessesEvents();
    } else if (route.page === 'harness-detail') {
      const h = HARNESSES.find(x => x.slug === route.slug);
      main.innerHTML = h ? renderHarnessDetailPage(h) : renderNotFound('harness');
    } else if (route.page === 'agents') {
      main.innerHTML = renderAgentsPage();
      bindAgentsEvents();
    } else if (route.page === 'agent-detail') {
      const a = AGENTS.find(x => x.slug === route.slug);
      main.innerHTML = a ? renderAgentDetailPage(a) : renderNotFound('agent');
      if (a) bindDetailEvents();
    } else if (route.page === 'submit') {
      main.innerHTML = renderSubmitPage();
      bindSubmitEvents();
    } else if (route.page === 'schema-spec') {
      main.innerHTML = renderSchemaSpecPage();
      loadSchemaSpecContent();
    } else if (route.page === 'evolution') {
      main.innerHTML = renderEvolutionPage();
      bindEvolutionEvents();
    }

    window.scrollTo(0, 0);
  }

  function updateNavActive(page) {
    document.querySelectorAll('.nav-link').forEach(link => link.classList.remove('active'));
    const navMap = {
      home: 'home', browse: 'browse', detail: 'browse',
      harnesses: 'harnesses', 'harness-detail': 'harnesses',
      agents: 'agents', 'agent-detail': 'agents',
      submit: 'submit',
      evolution: 'evolution',
    };
    const nav = navMap[page];
    if (nav) document.querySelector(`[data-nav="${nav}"]`)?.classList.add('active');
  }

  /* ===================== HELPERS ===================== */
  function riskBadge(level) {
    const labels = { safe: '安全', low: '低风险', medium: '中风险', high: '高风险' };
    const icons = {
      safe: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>',
      low:  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>',
      medium: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 9v4m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/></svg>',
      high: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>',
    };
    const l = level || 'safe';
    return `<span class="badge badge-${l}">${icons[l] || icons.safe}${labels[l] || l}</span>`;
  }

  function toolBadges(tools) {
    if (!tools || !tools.length) return '';
    return tools.map(t => {
      if (t === 'claude')      return `<span class="tool-badge tool-badge-claude">Claude</span>`;
      if (t === 'codex')       return `<span class="tool-badge tool-badge-codex">Codex</span>`;
      if (t === 'claude-code') return `<span class="tool-badge tool-badge-cc">Claude Code</span>`;
      return `<span class="tool-badge">${escHtml(t)}</span>`;
    }).join('');
  }

  function skillCard(skill, size) {
    const isLarge = size === 'large';
    return `
<a class="skill-card page-enter" data-href="#skill/${escHtml(skill.slug)}">
  <div class="skill-card-header">
    <div class="skill-icon${isLarge ? ' skill-icon-lg' : ''}">${skill.icon || '📦'}</div>
    <div style="flex:1;min-width:0">
      <div class="skill-name-row">
        <span class="skill-name text-sm font-semibold line-clamp-1">${escHtml(skill.name)}</span>
        ${riskBadge(skill.risk_level)}
      </div>
      <p class="skill-short-desc line-clamp-1">${escHtml(skill.summary || '')}</p>
      <p class="skill-author text-xs">by ${escHtml(skill.author || 'unknown')}</p>
    </div>
  </div>
  ${isLarge ? `<p class="skill-desc line-clamp-2">${escHtml(skill.value_statement || skill.summary || '')}</p>` : ''}
  <div class="skill-card-footer">
    <div class="skill-card-tools">${toolBadges(skill.supported_tools)}</div>
    <span class="card-category">${escHtml(skill.category || '')}</span>
  </div>
</a>`;
  }

  function escHtml(str) {
    return String(str || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function catIcon(cat) {
    const icons = {
      productivity: '⚡',
      documentation: '📝',
      development: '🛠️',
      security: '🔒',
      data: '📊',
    };
    return icons[cat] || '📦';
  }

  function riskOrder(r) {
    return { safe: 0, low: 1, medium: 2, high: 3 }[r] ?? 99;
  }

  function envTypeBadge(type) {
    const labels = { image: '镜像', ssh: 'SSH' };
    const label = labels[type] || escHtml(type || '');
    // Whitelist CSS class fragment to prevent attribute injection (escHtml doesn't escape spaces)
    const safeClass = /^[a-z0-9-]+$/.test(type || '') ? type : 'unknown';
    return `<span class="env-badge env-badge-${safeClass}">${label}</span>`;
  }

  function harnessCard(h) {
    return `
<a class="skill-card page-enter" data-href="#harness/${escHtml(h.slug)}">
  <div class="skill-card-header">
    <div class="skill-icon">${h.icon || '🖥️'}</div>
    <div style="flex:1;min-width:0">
      <div class="skill-name-row">
        <span class="skill-name text-sm font-semibold line-clamp-1">${escHtml(h.name)}</span>
        ${envTypeBadge(h.env_type)}
      </div>
      <p class="skill-short-desc line-clamp-1">${escHtml(h.summary || '')}</p>
      <p class="skill-author text-xs">by ${escHtml(h.author || 'unknown')}</p>
    </div>
  </div>
  <p class="skill-desc line-clamp-2">${escHtml(h.value_statement || h.summary || '')}</p>
  <div class="skill-card-footer">
    <div class="skill-card-tools">${toolBadges(h.supported_tools)}</div>
  </div>
</a>`;
  }

  function skillTypeBadge(skill) {
    if (!skill) return '';
    const type = skill.type || '';
    const safeClass = /^[a-z0-9-]+$/.test(type) ? type : 'unknown';
    return `<span class="skill-type-badge skill-type-badge-${safeClass}">${escHtml(type.toUpperCase())}</span>`;
  }

  function agentCard(agent) {
    return `
<a class="skill-card page-enter" data-href="#agent/${escHtml(agent.slug)}">
  <div class="skill-card-header">
    <div class="skill-icon">${escHtml(agent.icon || '🤖')}</div>
    <div style="flex:1;min-width:0">
      <div class="skill-name-row">
        <span class="skill-name text-sm font-semibold line-clamp-1">${escHtml(agent.name)}</span>
        ${skillTypeBadge(agent.skill)}
      </div>
      <p class="skill-short-desc line-clamp-1">${escHtml(agent.description || '')}</p>
      <p class="skill-author text-xs">by ${escHtml(agent.author || 'unknown')}</p>
    </div>
  </div>
  <p class="skill-desc line-clamp-2">${escHtml(agent.description || '')}</p>
  <div class="skill-card-footer">
    <div class="skill-card-tools">${(agent.tags || []).slice(0, 3).map(t => `<span class="tool-badge">${escHtml(t)}</span>`).join('')}</div>
  </div>
</a>`;
  }

  /* ===================== HOME PAGE ===================== */
  function renderHomePage() {
    // FIX: deduplicate — show featured (first 4), popular = remaining; skip popular if no extras
    const featured = SKILLS.slice(0, 4);
    const popular  = SKILLS.length > 4 ? SKILLS.slice(4, 10) : [];
    const categories = [...new Set(SKILLS.map(s => s.category).filter(Boolean))];

    // FIX: use data-cat attribute instead of inline onclick to avoid quote injection
    const catPills = categories.map(c => `
      <button class="pill" data-cat="${escHtml(c)}">
        ${catIcon(c)} ${escHtml(c)}
      </button>`).join('');

    return `
<section class="hero">
  <div class="hero-gradient"></div>
  <div class="px-container max-w-7xl">
    <div class="hero-content">
      <div style="display:inline-flex;align-items:center;gap:.5rem;padding:.375rem .75rem;border-radius:9999px;background:var(--accent-bg);color:var(--accent-foreground);font-size:.75rem;font-weight:600;margin-bottom:1rem">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>
        SecAgentHub
      </div>
      <h1>构建更强大的 <span class="gradient-text">AI for ICSL安全应用</span></h1>
      <p>技能(Skills) · 运行时(Harness) · 原子智能体(Agent)，一站式发现与接入</p>
      <div class="search-box">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
        <input type="text" id="hero-search" placeholder="搜索技能…" autocomplete="off">
      </div>
      <div class="category-pills" id="category-pills">${catPills}</div>
      <div class="hero-cta-btns">
        <a class="hero-cta-btn" data-href="#browse">⚡ 浏览技能</a>
        <a class="hero-cta-btn hero-cta-btn-alt" data-href="#harnesses">🖥 浏览运行时</a>
        <a class="hero-cta-btn hero-cta-btn-alt" data-href="#agents">🤖 浏览智能体</a>
        <a class="hero-cta-btn hero-cta-btn-ghost" data-href="#submit">+ 提交技能</a>
      </div>
    </div>
  </div>
</section>

<div class="px-container max-w-7xl" style="padding-bottom:4rem">
  ${featured.length ? `
  <section style="padding:3rem 0 2rem">
    <div class="section-header">
      <div>
        <h2>精选技能</h2>
        <p>由官方维护者精心整理的高质量技能</p>
      </div>
      <a class="section-link" data-href="#browse">
        查看全部
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14m-7-7 7 7-7 7"/></svg>
      </a>
    </div>
    <div class="skills-grid cols-4">${featured.map(s => skillCard(s, 'small')).join('')}</div>
  </section>` : ''}

  ${popular.length ? `
  <section class="section" style="padding:3rem 0 2rem">
    <div class="section-header">
      <div>
        <h2>热门技能</h2>
        <p>社区最喜爱的技能集合</p>
      </div>
      <a class="section-link" data-href="#browse">
        查看全部
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14m-7-7 7 7-7 7"/></svg>
      </a>
    </div>
    <div class="skills-grid">${popular.map(s => skillCard(s, 'large')).join('')}</div>
  </section>` : ''}

  ${AGENTS.length ? `
  <section class="section" style="padding:3rem 0 2rem">
    <div class="section-header">
      <div>
        <h2>精选原子智能体</h2>
        <p>开箱即用的 AI 智能体，内置系统提示词与工具配置</p>
      </div>
      <a class="section-link" data-href="#agents">
        查看全部
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14m-7-7 7 7-7 7"/></svg>
      </a>
    </div>
    <div class="skills-grid cols-4">${AGENTS.slice(0, 4).map(a => agentCard(a)).join('')}</div>
  </section>` : ''}

  ${HARNESSES.length ? `
  <section class="section" style="padding:3rem 0 2rem">
    <div class="section-header">
      <div>
        <h2>精选运行时</h2>
        <p>经过验证的 Agent 运行时（Harness），镜像与 SSH 类型均可一键接入</p>
      </div>
      <a class="section-link" data-href="#harnesses">
        查看全部
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14m-7-7 7 7-7 7"/></svg>
      </a>
    </div>
    <div class="skills-grid cols-4">${HARNESSES.slice(0, 4).map(h => harnessCard(h)).join('')}</div>
  </section>` : ''}

  <section class="${featured.length ? 'section ' : ''}" style="padding:3rem 0 2rem">
    <div class="section-header" style="margin-bottom:2rem">
      <div>
        <h2>为什么选择 SecAgentHub？</h2>
        <p>构建更安全、更智能的 AI 工作流</p>
      </div>
    </div>
    <div class="features">
      <div class="feature-item">
        <div class="feature-icon green">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
        </div>
        <div>
          <h3 class="font-semibold" style="margin-bottom:.25rem">全面安全审计</h3>
          <p class="text-sm text-muted">每个技能均经过自动化安全扫描，风险等级清晰可见，让你放心使用。</p>
        </div>
      </div>
      <div class="feature-item">
        <div class="feature-icon blue">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>
        </div>
        <div>
          <h3 class="font-semibold" style="margin-bottom:.25rem">一键安装</h3>
          <p class="text-sm text-muted">简洁的安装命令，支持多个 AI 平台，几秒钟即可开始使用新技能。</p>
        </div>
      </div>
      <div class="feature-item">
        <div class="feature-icon amber">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>
        </div>
        <div>
          <h3 class="font-semibold" style="margin-bottom:.25rem">持续更新</h3>
          <p class="text-sm text-muted">技能库持续扩充，紧跟 AI 工具最新发展，始终保持最佳状态。</p>
        </div>
      </div>
    </div>
  </section>
</div>
`;
  }

  function bindHomeEvents() {
    // Hero search — Enter key navigates to browse with query
    const heroSearch = document.getElementById('hero-search');
    if (heroSearch) {
      heroSearch.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' && this.value.trim()) {
          location.hash = 'browse?' + new URLSearchParams({ q: this.value.trim() }).toString();
        }
      });
    }

    // FIX: category pills use data-cat + delegation (no inline onclick)
    const pillsContainer = document.getElementById('category-pills');
    if (pillsContainer) {
      pillsContainer.addEventListener('click', function (e) {
        const pill = e.target.closest('[data-cat]');
        if (pill) {
          location.hash = 'browse?' + new URLSearchParams({ cat: pill.dataset.cat }).toString();
        }
      });
    }
  }

  /* ===================== BROWSE PAGE ===================== */
  function renderBrowsePage() {
    const categories = [...new Set(SKILLS.map(s => s.category).filter(Boolean))];
    const catItems = categories.map(c => `
      <div class="sidebar-item" data-sidebar-cat="${escHtml(c)}">
        <span style="width:1rem;text-align:center">${catIcon(c)}</span>
        <span>${escHtml(c)}</span>
      </div>`).join('');

    const riskLevels = ['safe', 'low', 'medium', 'high'];
    const riskDotColor = { safe: '#16a34a', low: '#16a34a', medium: '#d97706', high: '#dc2626' };
    const riskLabels   = { safe: '安全', low: '低风险', medium: '中风险', high: '高风险' };
    const riskItems = riskLevels.map(r => `
      <div class="sidebar-item" data-sidebar-risk="${r}">
        <span style="width:.625rem;height:.625rem;border-radius:50%;background:${riskDotColor[r]};display:inline-block;flex-shrink:0"></span>
        <span>${riskLabels[r]}</span>
      </div>`).join('');

    return `
<div class="browse-layout px-container max-w-7xl">
  <!-- Sidebar -->
  <aside class="browse-sidebar">
    <div class="sidebar-search">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
      <input type="text" id="browse-search" placeholder="搜索技能…" autocomplete="off">
    </div>

    <div class="sidebar-section">
      <p class="sidebar-title">分类</p>
      <div class="sidebar-item active" data-sidebar-cat="all">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>
        <span>全部</span>
      </div>
      ${catItems}
    </div>

    <div class="sidebar-section">
      <p class="sidebar-title">安全级别</p>
      ${riskItems}
    </div>
  </aside>

  <!-- Main -->
  <div class="browse-main" style="padding:1.5rem 0 4rem">
    <div class="browse-header">
      <span class="browse-count" id="browse-count">${SKILLS.length} 个技能</span>
      <select class="sort-select" id="browse-sort">
        <option value="default">默认排序</option>
        <option value="name">名称 A-Z</option>
        <option value="risk">风险等级</option>
        <option value="author">作者</option>
      </select>
    </div>
    <div class="skills-grid" id="browse-grid">
      ${SKILLS.map(s => skillCard(s, 'large')).join('')}
    </div>
    <p id="browse-empty" class="text-center text-muted" style="display:none;padding:3rem 0">没有找到匹配的技能</p>
  </div>
</div>
`;
  }

  function bindBrowseEvents() {
    // Parse initial state from hash (e.g. #browse?cat=productivity&q=foo)
    const rawQuery = location.hash.replace(/^#\/?browse\??/, '');
    const params = new URLSearchParams(rawQuery);
    let activeCategory = params.get('cat') || 'all';
    let activeRisk     = null;
    let searchQ        = params.get('q') || '';

    const main        = document.getElementById('main-content');
    const searchInput = document.getElementById('browse-search');
    const sortSelect  = document.getElementById('browse-sort');

    // FIX: apply initial sidebar highlight from URL params
    if (activeCategory !== 'all') {
      main.querySelectorAll('[data-sidebar-cat]').forEach(el => el.classList.remove('active'));
      const target = main.querySelector(`[data-sidebar-cat="${CSS.escape(activeCategory)}"]`);
      if (target) target.classList.add('active');
    }

    if (searchInput) {
      searchInput.value = searchQ;
      searchInput.addEventListener('input', function () {
        searchQ = this.value;
        updateGrid();
      });
    }

    // Sidebar clicks — single listener on the sidebar element
    main.addEventListener('click', function (e) {
      // Sidebar category
      const catEl = e.target.closest('[data-sidebar-cat]');
      if (catEl) {
        activeCategory = catEl.dataset.sidebarCat;
        main.querySelectorAll('[data-sidebar-cat]').forEach(el => el.classList.remove('active'));
        catEl.classList.add('active');
        // Clear risk filter when switching category
        main.querySelectorAll('[data-sidebar-risk]').forEach(el => el.classList.remove('active'));
        activeRisk = null;
        updateGrid();
        return;
      }

      // Sidebar risk toggle
      const riskEl = e.target.closest('[data-sidebar-risk]');
      if (riskEl) {
        const clicked = riskEl.dataset.sidebarRisk;
        if (activeRisk === clicked) {
          activeRisk = null;
          riskEl.classList.remove('active');
        } else {
          main.querySelectorAll('[data-sidebar-risk]').forEach(el => el.classList.remove('active'));
          activeRisk = clicked;
          riskEl.classList.add('active');
        }
        updateGrid();
      }
    });

    if (sortSelect) {
      sortSelect.addEventListener('change', updateGrid);
    }

    // Trigger initial grid render if filters came from URL
    if (searchQ || activeCategory !== 'all') updateGrid();

    function updateGrid() {
      const q = searchQ.toLowerCase();
      let filtered = SKILLS.filter(s => {
        const matchCat  = activeCategory === 'all' || s.category === activeCategory;
        const matchRisk = !activeRisk || s.risk_level === activeRisk;
        const matchQ    = !q
          || s.name.toLowerCase().includes(q)
          || (s.summary || '').toLowerCase().includes(q)
          || (s.author || '').toLowerCase().includes(q)
          || (s.tags || []).some(t => t.toLowerCase().includes(q));
        return matchCat && matchRisk && matchQ;
      });

      const sort = sortSelect?.value || 'default';
      if (sort === 'name')   filtered.sort((a, b) => a.name.localeCompare(b.name));
      else if (sort === 'risk')   filtered.sort((a, b) => riskOrder(a.risk_level) - riskOrder(b.risk_level));
      else if (sort === 'author') filtered.sort((a, b) => (a.author || '').localeCompare(b.author || ''));

      const grid  = document.getElementById('browse-grid');
      const empty = document.getElementById('browse-empty');
      const count = document.getElementById('browse-count');

      // FIX: no bindCardClicks(grid) here — the global document listener handles all [data-href] clicks
      if (grid)  grid.innerHTML = filtered.map(s => skillCard(s, 'large')).join('');
      if (empty) empty.style.display = filtered.length ? 'none' : 'block';
      if (count) count.textContent = filtered.length + ' 个技能';
    }
  }

  /* ===================== DETAIL PAGE ===================== */
  function renderDetailPage(skill) {
    const tools        = toolBadges(skill.supported_tools);
    const capabilities = (skill.actual_capabilities || []).map(c => `<li>${escHtml(c)}</li>`).join('');
    const useCases     = (skill.use_cases || []).map(u => `
      <div style="padding:1rem;border:1px solid var(--border);border-radius:var(--radius);background:var(--muted)">
        <p class="text-xs text-muted" style="margin-bottom:.25rem">${escHtml(u.target_user || '')}</p>
        <p class="font-semibold text-sm" style="margin-bottom:.25rem">${escHtml(u.title || '')}</p>
        <p class="text-sm text-muted">${escHtml(u.description || '')}</p>
      </div>`).join('');

    // FIX: build install command without escaping for display/clipboard (slug is [a-z0-9-])
    const installCmd = `gh skill install ${skill.slug}`;

    const prompts = (skill.prompt_templates || []).map(p => `
      <div style="padding:1rem;border:1px solid var(--border);border-radius:var(--radius);margin-bottom:.75rem">
        <p class="font-semibold text-sm" style="margin-bottom:.25rem">${escHtml(p.title || '')}</p>
        <p class="text-xs text-muted" style="margin-bottom:.5rem">${escHtml(p.scenario || '')}</p>
        <div class="clone-cmd" data-copy="${escHtml(p.prompt || '')}">
          <code>${escHtml(p.prompt || '')}</code>
          <svg class="copy-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>
        </div>
      </div>`).join('');

    const sourceUrl = skill.source_url || '';

    const diffs = skill.diffs || [];
    const diffSection = diffs.length ? `
    <div class="install-steps diff-section">
      <h2 class="font-semibold" style="margin-bottom:1rem">版本变更对比</h2>
      <div style="display:flex;gap:.75rem;flex-wrap:wrap;margin-bottom:1rem">
        ${diffs.map((f, i) => `<button class="diff-tab${i === diffs.length - 1 ? ' diff-tab-active' : ''}" data-diff-file="${escHtml(f)}" data-diff-slug="${escHtml(skill.slug)}">${escHtml(f.replace(/^\d+-/, '').replace(/\.diff$/, ''))}</button>`).join('')}
      </div>
      <div id="diff-render-box"></div>
    </div>` : '';

    return `
<div class="detail-page px-container max-w-7xl" style="padding-bottom:4rem">
  <nav class="breadcrumb" aria-label="面包屑">
    <a data-href="#">首页</a>
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m9 18 6-6-6-6"/></svg>
    <a data-href="#browse">技能</a>
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m9 18 6-6-6-6"/></svg>
    <span>${escHtml(skill.name)}</span>
  </nav>

  <!-- Header Card -->
  <div class="detail-header">
    <div class="detail-top">
      <div class="skill-icon skill-icon-lg">${skill.icon || '📦'}</div>
      <div class="detail-info">
        <div style="display:flex;align-items:center;gap:.75rem;flex-wrap:wrap;margin-bottom:.5rem">
          <h1>${escHtml(skill.name)}</h1>
          ${riskBadge(skill.risk_level)}
        </div>
        <p class="detail-meta">v${escHtml(skill.version || '1.0.0')} · by <strong>${escHtml(skill.author || 'unknown')}</strong> · ${escHtml(skill.license || '')} · ${escHtml(skill.category || '')}</p>
        <p class="detail-desc">${escHtml(skill.value_statement || skill.summary || '')}</p>
        <div class="detail-tools">
          <span class="text-xs text-muted">支持平台：</span>
          ${tools}
        </div>
      </div>
    </div>
    <div class="install-box">
      <div class="clone-cmd" data-copy="${escHtml(installCmd)}" style="flex:1" role="button" tabindex="0" aria-label="复制安装命令">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="flex-shrink:0;color:var(--muted-foreground)"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>
        <code>$ ${escHtml(installCmd)}</code>
        <svg class="copy-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>
      </div>
      ${sourceUrl ? `
      <a class="btn-secondary" href="${escHtml(sourceUrl)}" target="_blank" rel="noopener noreferrer">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M12 0C5.37 0 0 5.37 0 12c0 5.3 3.44 9.8 8.2 11.38.6.11.82-.26.82-.57v-2c-3.34.73-4.04-1.61-4.04-1.61-.55-1.39-1.34-1.76-1.34-1.76-1.09-.75.08-.73.08-.73 1.2.08 1.84 1.24 1.84 1.24 1.07 1.83 2.81 1.3 3.5 1 .1-.78.42-1.3.76-1.6-2.67-.3-5.47-1.33-5.47-5.93 0-1.31.47-2.38 1.24-3.22-.12-.3-.54-1.52.12-3.17 0 0 1.01-.32 3.3 1.23a11.5 11.5 0 016 0c2.3-1.55 3.3-1.23 3.3-1.23.66 1.65.24 2.87.12 3.17.77.84 1.24 1.91 1.24 3.22 0 4.61-2.81 5.63-5.48 5.92.43.37.81 1.1.81 2.22v3.29c0 .32.22.69.83.57C20.57 21.8 24 17.3 24 12c0-6.63-5.37-12-12-12z"/></svg>
        查看源码
      </a>` : ''}
    </div>
  </div>

  <div style="display:grid;grid-template-columns:1fr;gap:1.5rem">
    ${capabilities ? `
    <div class="install-steps">
      <h2 class="font-semibold" style="margin-bottom:1rem">功能特性</h2>
      <ul style="padding-left:1.25rem;color:var(--secondary-foreground)">
        ${capabilities}
      </ul>
    </div>` : ''}

    ${useCases ? `
    <div class="install-steps">
      <h2 class="font-semibold" style="margin-bottom:1rem">使用场景</h2>
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:.75rem">
        ${useCases}
      </div>
    </div>` : ''}

    ${prompts ? `
    <div class="install-steps">
      <h2 class="font-semibold" style="margin-bottom:1rem">提示词模板</h2>
      ${prompts}
    </div>` : ''}

    ${diffSection}
  </div>
</div>
`;
  }

  function bindDetailEvents() {
    // Copy command boxes (install command + prompt templates)
    document.querySelectorAll('.clone-cmd[data-copy]').forEach(el => {
      el.addEventListener('click', function () {
        copyText(this.dataset.copy);
      });
      // Keyboard accessibility
      el.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          copyText(this.dataset.copy);
        }
      });
    });

    // Diff tabs
    function loadDiff(slug, file) {
      const box = document.getElementById('diff-render-box');
      if (!box) return;
      box.innerHTML = '<p class="text-sm text-muted" style="padding:.5rem">加载中…</p>';
      fetch(`data/diffs/${slug}/${file}`)
        .then(r => { if (!r.ok) throw new Error(r.status); return r.text(); })
        .then(text => {
          box.innerHTML = '';
          new Diff2HtmlUI(box, text, { outputFormat: 'side-by-side', drawFileList: false }).draw();
        })
        .catch(() => { box.innerHTML = '<p class="text-sm text-muted" style="padding:.5rem">加载失败</p>'; });
    }

    document.querySelectorAll('.diff-tab').forEach(btn => {
      btn.addEventListener('click', function () {
        document.querySelectorAll('.diff-tab').forEach(b => b.classList.remove('diff-tab-active'));
        this.classList.add('diff-tab-active');
        loadDiff(this.dataset.diffSlug, this.dataset.diffFile);
      });
    });

    const activeTab = document.querySelector('.diff-tab-active');
    if (activeTab) loadDiff(activeTab.dataset.diffSlug, activeTab.dataset.diffFile);
  }

  /* ===================== HARNESSES BROWSE PAGE ===================== */
  function renderHarnessesPage() {
    const envTypes = ['image', 'ssh'];
    const envLabels = { image: '🐳 镜像', ssh: '🔐 SSH' };
    const envItems = envTypes.map(t => `
      <div class="sidebar-item" data-h-type="${t}">
        <span>${envLabels[t]}</span>
      </div>`).join('');

    return `
<div class="browse-layout px-container max-w-7xl">
  <aside class="browse-sidebar">
    <div class="sidebar-search">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
      <input type="text" id="h-search" placeholder="搜索运行时…" autocomplete="off">
    </div>
    <div class="sidebar-section">
      <p class="sidebar-title">运行时类型</p>
      <div class="sidebar-item active" data-h-type="all">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>
        <span>全部</span>
      </div>
      ${envItems}
    </div>
  </aside>
  <div class="browse-main" style="padding:1.5rem 0 4rem">
    <div class="browse-header">
      <span class="browse-count" id="h-count">${HARNESSES.length} 个运行时</span>
    </div>
    <div class="skills-grid" id="h-grid">
      ${HARNESSES.map(h => harnessCard(h)).join('')}
    </div>
    <p id="h-empty" class="text-center text-muted" style="display:none;padding:3rem 0">没有找到匹配的运行时</p>
  </div>
</div>`;
  }

  function bindHarnessesEvents() {
    const main = document.getElementById('main-content');
    const searchInput = document.getElementById('h-search');
    let activeType = 'all';
    let searchQ = '';

    if (searchInput) {
      searchInput.addEventListener('input', function () {
        searchQ = this.value;
        updateHGrid();
      });
    }

    main.addEventListener('click', function (e) {
      const typeEl = e.target.closest('[data-h-type]');
      if (typeEl) {
        activeType = typeEl.dataset.hType;
        main.querySelectorAll('[data-h-type]').forEach(el => el.classList.remove('active'));
        typeEl.classList.add('active');
        updateHGrid();
      }
    });

    function updateHGrid() {
      const q = searchQ.toLowerCase();
      const filtered = HARNESSES.filter(h => {
        const matchType = activeType === 'all' || h.env_type === activeType;
        const matchQ = !q
          || h.name.toLowerCase().includes(q)
          || (h.summary || '').toLowerCase().includes(q)
          || (h.author || '').toLowerCase().includes(q)
          || (h.tags || []).some(t => t.toLowerCase().includes(q));
        return matchType && matchQ;
      });
      const grid  = document.getElementById('h-grid');
      const empty = document.getElementById('h-empty');
      const count = document.getElementById('h-count');
      if (grid)  grid.innerHTML = filtered.map(h => harnessCard(h)).join('');
      if (empty) empty.style.display = filtered.length ? 'none' : 'block';
      if (count) count.textContent = filtered.length + ' 个运行时';
    }
  }

  /* ===================== HARNESS DETAIL PAGE ===================== */
  function renderHarnessDetailPage(h) {
    const caps = (h.capabilities || []).map(c => `<li>${escHtml(c)}</li>`).join('');
    const uses = (h.use_cases || []).map(u => `
      <div style="padding:1rem;border:1px solid var(--border);border-radius:var(--radius);background:var(--muted)">
        <p class="font-semibold text-sm" style="margin-bottom:.25rem">${escHtml(u.title || '')}</p>
        <p class="text-sm text-muted">${escHtml(u.description || '')}</p>
      </div>`).join('');

    const connInfo = h.env_type === 'ssh'
      ? `<div class="clone-cmd" style="cursor:default"><code>ssh ${escHtml(h.ssh_user || 'agent')}@${escHtml(h.ssh_host || '')}</code></div>`
      : h.base_image
        ? `<div class="clone-cmd" style="cursor:default"><code>docker pull ${escHtml(h.base_image)}</code></div>`
        : '';

    return `
<div class="detail-page px-container max-w-7xl" style="padding-bottom:4rem">
  <nav class="breadcrumb" aria-label="面包屑">
    <a data-href="#">首页</a>
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m9 18 6-6-6-6"/></svg>
    <a data-href="#harnesses">运行时</a>
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m9 18 6-6-6-6"/></svg>
    <span>${escHtml(h.name)}</span>
  </nav>

  <div class="detail-header">
    <div class="detail-top">
      <div class="skill-icon skill-icon-lg">${h.icon || '🖥️'}</div>
      <div class="detail-info">
        <div style="display:flex;align-items:center;gap:.75rem;flex-wrap:wrap;margin-bottom:.5rem">
          <h1>${escHtml(h.name)}</h1>
          ${envTypeBadge(h.env_type)}
        </div>
        <p class="detail-meta">v${escHtml(h.version || '1.0.0')} · by <strong>${escHtml(h.author || 'unknown')}</strong></p>
        <p class="detail-desc">${escHtml(h.value_statement || h.summary || '')}</p>
        <div class="detail-tools">
          <span class="text-xs text-muted">支持平台：</span>
          ${toolBadges(h.supported_tools)}
        </div>
      </div>
    </div>
    ${connInfo ? `<div class="install-box">${connInfo}</div>` : ''}
  </div>

  <div style="display:grid;grid-template-columns:1fr;gap:1.5rem">
    ${caps ? `
    <div class="install-steps">
      <h2 class="font-semibold" style="margin-bottom:1rem">运行时能力</h2>
      <ul style="padding-left:1.25rem;color:var(--secondary-foreground)">${caps}</ul>
    </div>` : ''}
    ${uses ? `
    <div class="install-steps">
      <h2 class="font-semibold" style="margin-bottom:1rem">使用场景</h2>
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:.75rem">${uses}</div>
    </div>` : ''}
  </div>
</div>`;
  }

  /* ===================== AGENTS BROWSE PAGE ===================== */
  function renderAgentsPage() {
    const skillTypes = ['github', 'npx'];
    const typeLabels = { github: '🐙 GitHub', npx: '📦 NPX' };
    const typeItems = skillTypes.map(t => `
      <div class="sidebar-item" data-a-type="${t}">
        <span>${typeLabels[t]}</span>
      </div>`).join('');

    return `
<div class="browse-layout px-container max-w-7xl">
  <aside class="browse-sidebar">
    <div class="sidebar-search">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
      <input type="text" id="a-search" placeholder="搜索智能体…" autocomplete="off">
    </div>
    <div class="sidebar-section">
      <p class="sidebar-title">技能类型</p>
      <div class="sidebar-item active" data-a-type="all">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>
        <span>全部</span>
      </div>
      ${typeItems}
    </div>
  </aside>
  <div class="browse-main" style="padding:1.5rem 0 4rem">
    <div class="browse-header">
      <span class="browse-count" id="a-count">${AGENTS.length} 个智能体</span>
    </div>
    <div class="skills-grid" id="a-grid">
      ${AGENTS.map(a => agentCard(a)).join('')}
    </div>
    <p id="a-empty" class="text-center text-muted" style="display:none;padding:3rem 0">没有找到匹配的智能体</p>
  </div>
</div>`;
  }

  function bindAgentsEvents() {
    const main = document.getElementById('main-content');
    const searchInput = document.getElementById('a-search');
    let activeType = 'all';
    let searchQ = '';

    if (searchInput) {
      searchInput.addEventListener('input', function () {
        searchQ = this.value;
        updateAGrid();
      });
    }

    main.addEventListener('click', function (e) {
      const typeEl = e.target.closest('[data-a-type]');
      if (typeEl) {
        activeType = typeEl.dataset.aType;
        main.querySelectorAll('[data-a-type]').forEach(el => el.classList.remove('active'));
        typeEl.classList.add('active');
        updateAGrid();
      }
    });

    function updateAGrid() {
      const q = searchQ.toLowerCase();
      const filtered = AGENTS.filter(a => {
        const matchType = activeType === 'all' || (a.skill && a.skill.type === activeType);
        const matchQ = !q
          || a.name.toLowerCase().includes(q)
          || (a.description || '').toLowerCase().includes(q)
          || (a.author || '').toLowerCase().includes(q)
          || (a.tags || []).some(t => t.toLowerCase().includes(q));
        return matchType && matchQ;
      });
      const grid  = document.getElementById('a-grid');
      const empty = document.getElementById('a-empty');
      const count = document.getElementById('a-count');
      if (grid)  grid.innerHTML = filtered.map(a => agentCard(a)).join('');
      if (empty) empty.style.display = filtered.length ? 'none' : 'block';
      if (count) count.textContent = filtered.length + ' 个智能体';
    }
  }

  /* ===================== AGENT DETAIL PAGE ===================== */
  function renderAgentDetailPage(agent) {
    const tags = (agent.tags || []).map(t => `<span class="tool-badge">${escHtml(t)}</span>`).join('');
    const mcpList = (agent.mcp || []).map(m => `
      <div style="padding:.75rem;border:1px solid var(--border);border-radius:var(--radius);background:var(--muted);margin-bottom:.5rem">
        <p class="font-semibold text-sm">${escHtml(m.name || '')}</p>
        <p class="text-xs text-muted">${escHtml(m.type || '')}${m.package ? ' · ' + escHtml(m.package) : ''}</p>
      </div>`).join('');

    const skillCmd = agent.skill
      ? (agent.skill.type === 'github'
          ? `gh skill install ${escHtml(agent.skill.source || '')}`
          : `npx ${escHtml(agent.skill.package || agent.skill.source || '')}`)
      : '';

    return `
<div class="detail-page px-container max-w-7xl" style="padding-bottom:4rem">
  <nav class="breadcrumb" aria-label="面包屑">
    <a data-href="#">首页</a>
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m9 18 6-6-6-6"/></svg>
    <a data-href="#agents">智能体</a>
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m9 18 6-6-6-6"/></svg>
    <span>${escHtml(agent.name)}</span>
  </nav>

  <div class="detail-header">
    <div class="detail-top">
      <div class="skill-icon skill-icon-lg">${escHtml(agent.icon || '🤖')}</div>
      <div class="detail-info">
        <div style="display:flex;align-items:center;gap:.75rem;flex-wrap:wrap;margin-bottom:.5rem">
          <h1>${escHtml(agent.name)}</h1>
          ${skillTypeBadge(agent.skill)}
        </div>
        <p class="detail-meta">v${escHtml(agent.version || '1.0.0')} · by <strong>${escHtml(agent.author || 'unknown')}</strong></p>
        <p class="detail-desc">${escHtml(agent.description || '')}</p>
        ${tags ? `<div class="detail-tools">${tags}</div>` : ''}
      </div>
    </div>
    ${skillCmd ? `
    <div class="install-box">
      <div class="clone-cmd" data-copy="${escHtml(skillCmd)}" style="flex:1" role="button" tabindex="0" aria-label="复制安装命令">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="flex-shrink:0;color:var(--muted-foreground)"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>
        <code>$ ${escHtml(skillCmd)}</code>
        <svg class="copy-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>
      </div>
    </div>` : ''}
  </div>

  <div style="display:grid;grid-template-columns:1fr;gap:1.5rem">
    ${mcpList ? `
    <div class="install-steps">
      <h2 class="font-semibold" style="margin-bottom:1rem">MCP 配置</h2>
      ${mcpList}
    </div>` : ''}

    ${agent.agent_md ? `
    <div class="install-steps">
      <h2 class="font-semibold" style="margin-bottom:1rem">系统提示词 (AGENT.md)</h2>
      <pre style="white-space:pre-wrap;word-break:break-word;background:var(--muted);border:1px solid var(--border);border-radius:var(--radius);padding:1rem;font-size:.8rem;line-height:1.6;color:var(--secondary-foreground);overflow:auto">${escHtml(agent.agent_md)}</pre>
    </div>` : ''}
  </div>
</div>`;
  }

  /* ===================== SUBMIT PAGE ===================== */
  function renderSubmitPage() {
    return `
<div class="submit-layout px-container max-w-7xl">
  <div style="text-align:center;padding:3rem 0 2rem">
    <div style="display:inline-flex;align-items:center;gap:.5rem;padding:.375rem .75rem;border-radius:9999px;background:var(--accent-bg);color:var(--accent-foreground);font-size:.75rem;font-weight:600;margin-bottom:1rem">
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>
      提交技能
    </div>
    <h1 style="font-size:2rem;font-weight:700;margin-bottom:.75rem">分享你的 <span class="gradient-text">AI 技能</span></h1>
    <p class="text-muted">将你开发的技能提交到 SecAgentHub，让更多人受益。</p>
  </div>

  <div class="submit-steps">
    <div class="submit-step">
      <div class="submit-step-num">1</div>
      <div>
        <h3>准备 skill-report.json</h3>
        <p class="text-sm text-muted">按照 <a data-href="#schema-spec" style="color:var(--accent-foreground);cursor:pointer">Schema 规范</a> 准备技能描述文件，包含名称、分类、安全审计信息等字段。</p>
      </div>
    </div>
    <div class="submit-step">
      <div class="submit-step-num">2</div>
      <div>
        <h3>填写提交信息</h3>
        <p class="text-sm text-muted">在下方表单中填写技能基本信息，系统将自动生成 GitHub Issue。</p>
      </div>
    </div>
    <div class="submit-step">
      <div class="submit-step-num">3</div>
      <div>
        <h3>等待审核合并</h3>
        <p class="text-sm text-muted">维护者审核通过后，技能将出现在 SecAgentHub 平台，并自动进行安全评级。</p>
      </div>
    </div>
  </div>

  <div class="submit-form">
    <h2 style="font-size:1.125rem;font-weight:600;margin-bottom:1.5rem">填写提交信息</h2>
    <div class="form-group">
      <label class="form-label" for="s-name">技能名称 *</label>
      <input class="form-input" id="s-name" type="text" placeholder="例：git-commit-helper">
    </div>
    <div class="form-group">
      <label class="form-label" for="s-repo">GitHub 仓库地址 *</label>
      <input class="form-input" id="s-repo" type="url" placeholder="https://github.com/yourname/yourskill">
    </div>
    <div class="form-group">
      <label class="form-label" for="s-cat">分类</label>
      <select class="form-input" id="s-cat">
        <option value="">请选择分类</option>
        <option value="productivity">⚡ productivity</option>
        <option value="documentation">📝 documentation</option>
        <option value="development">🛠️ development</option>
        <option value="security">🔒 security</option>
        <option value="data">📊 data</option>
      </select>
    </div>
    <div class="form-group">
      <label class="form-label" for="s-desc">简短描述 *</label>
      <textarea class="form-input" id="s-desc" rows="3" placeholder="一两句话描述技能的用途和亮点…"></textarea>
    </div>
    <div class="form-group">
      <label class="form-label" for="s-contact">联系方式（可选）</label>
      <input class="form-input" id="s-contact" type="text" placeholder="GitHub 用户名或邮箱">
    </div>
    <p id="submit-error" class="text-sm" style="color:var(--danger);display:none;margin-bottom:.75rem"></p>
    <button class="submit-btn" id="submit-btn">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>
      在 GitHub 提交 Issue
    </button>
  </div>
</div>`;
  }

  function bindSubmitEvents() {
    const btn = document.getElementById('submit-btn');
    if (!btn) return;
    btn.addEventListener('click', function () {
      const name    = document.getElementById('s-name')?.value.trim();
      const repo    = document.getElementById('s-repo')?.value.trim();
      const desc    = document.getElementById('s-desc')?.value.trim();
      const cat     = document.getElementById('s-cat')?.value;
      const contact = document.getElementById('s-contact')?.value.trim();
      const errEl   = document.getElementById('submit-error');

      if (!name || !repo || !desc) {
        if (errEl) { errEl.textContent = '请填写技能名称、仓库地址和描述。'; errEl.style.display = 'block'; }
        return;
      }
      if (errEl) errEl.style.display = 'none';

      const body = [
        `## 技能名称\n${name}`,
        `## 仓库地址\n${repo}`,
        cat ? `## 分类\n${cat}` : '',
        `## 描述\n${desc}`,
        contact ? `## 联系方式\n${contact}` : '',
      ].filter(Boolean).join('\n\n');

      const url = 'https://github.com/cxm95/skills4sec/issues/new?'
        + new URLSearchParams({ title: `[技能提交] ${name}`, body, labels: 'skill-submission' });
      window.open(url, '_blank', 'noopener,noreferrer');
    });
  }

  /* ===================== SCHEMA SPEC PAGE ===================== */
  function renderSchemaSpecPage() {
    return `
<div class="detail-page px-container max-w-7xl">
  <div style="margin-bottom:1.5rem">
    <a data-href="#submit" style="color:var(--accent-foreground);cursor:pointer;font-size:.875rem">&larr; 返回提交技能</a>
  </div>
  <div id="schema-spec-content" style="padding:2rem;border-radius:var(--radius-xl);border:1px solid var(--border);background:var(--card)">
    <p class="text-muted">加载中...</p>
  </div>
</div>`;
  }

  function loadSchemaSpecContent() {
    var container = document.getElementById('schema-spec-content');
    if (!container) return;
    fetch('md/secskills.rules.v0.1.md')
      .then(function(res) { if (!res.ok) throw new Error(res.status); return res.text(); })
      .then(function(md) {
        if (typeof marked !== 'undefined' && marked.parse) {
          container.innerHTML = '<div class="markdown-body">' + marked.parse(md) + '</div>';
        } else {
          container.innerHTML = '<pre style="white-space:pre-wrap;font-size:.875rem">' + md.replace(/</g, '&lt;') + '</pre>';
        }
      })
      .catch(function() {
        container.innerHTML = '<p class="text-muted">无法加载规范文档。</p>';
      });
  }

  /* ===================== EVOLUTION PAGE ===================== */
  function renderEvolutionPage() {
    const s = EVOL_SUMMARY;
    const improvement = s.original_accuracy && s.improved_accuracy
      ? '+' + Math.round((s.improved_accuracy - s.original_accuracy) * 100) + '%'
      : 'N/A';

    const logItems = EVOL_LOGS.map(l => {
      const time = l.ts ? new Date(l.ts).toLocaleString('zh-CN', { hour12: false }) : '';
      const badgeCls = l.type === 'optimize' ? 'evol-log-badge-optimize' : 'evol-log-badge-invoke';
      const badgeLabel = l.type === 'optimize' ? '优化' : '调用';
      const resultCls = (l.result === 'pass' || l.result === 'success') ? 'evol-log-result-ok' : 'evol-log-result-fail';
      return `<div class="evol-log-item">
        <span class="evol-log-time">${escHtml(time)}</span>
        <span class="evol-log-badge ${badgeCls}">${badgeLabel}</span>
        <span class="evol-log-skill">${escHtml(l.skill || '')}</span>
        <span class="evol-log-agent">${escHtml(l.agent || '')}</span>
        <span class="evol-log-harness">${escHtml(l.harness || '')}</span>
        <span class="evol-log-detail">${escHtml(l.detail || '')}</span>
        <span class="evol-log-badge ${resultCls}">${escHtml(l.result || '')}</span>
      </div>`;
    }).join('');

    return `
<div class="detail-page px-container max-w-7xl page-enter" style="padding-bottom:4rem">
  <div style="text-align:center;padding:2rem 0 1.5rem">
    <div style="display:inline-flex;align-items:center;gap:.5rem;padding:.375rem .75rem;border-radius:9999px;background:var(--accent-bg);color:var(--accent-foreground);font-size:.75rem;font-weight:600;margin-bottom:1rem">
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>
      Memento-S
    </div>
    <h1 style="font-size:2rem;font-weight:700;margin-bottom:.75rem">技能<span class="gradient-text">自进化</span>系统</h1>
    <p class="text-muted" style="max-width:36rem;margin:0 auto">基于 Memento-S 飞轮迭代，优化和验证 AI 技能，持续提升任务成功率。</p>
  </div>

  <!-- Explanation (3 columns) -->
  <div class="evol-explain">
    <div class="evol-explain-grid">
      <div class="evol-explain-card" style="border-top:3px solid #a78bfa">
        <div class="step-number">1</div>
        <div class="step-content">
          <h3>执行与评判</h3>
          <p>Task Executor 使用当前版本的技能执行任务，Answer Judge 自动判定结果是否正确。正确则记录成功日志；失败则进入归因阶段。</p>
        </div>
      </div>
      <div class="evol-explain-card" style="border-top:3px solid #60a5fa">
        <div class="step-number">2</div>
        <div class="step-content">
          <h3>失败归因</h3>
          <p>Failure Attribution 分析失败根因，Utility Tracker 评估技能历史表现，决定是优化已有技能（OPTIMIZE）还是发现新技能（DISCOVER）。</p>
        </div>
      </div>
      <div class="evol-explain-card" style="border-top:3px solid #4ade80">
        <div class="step-number">3</div>
        <div class="step-content">
          <h3>进化与验证</h3>
          <p>LLM Skill Rewriter 重写技能代码，Unit Test Gate 运行单元测试。通过则重试原始任务；失败则回滚到上一版本。</p>
        </div>
      </div>
    </div>

    <!-- Core concept + collapsible diagram -->
    <div class="evol-core-idea" id="evol-toggle-diagram">
      <p style="font-size:.875rem;color:var(--secondary-foreground);line-height:1.6;margin:0;flex:1"><strong>核心理念：</strong>学习不发生在模型权重中，而是发生在外部技能代码的迭代重写中。</p>
      <span class="evol-toggle-btn" id="evol-toggle-btn">
        <svg class="evol-toggle-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m9 18 6-6-6-6"/></svg>
        查看流程图
      </span>
    </div>
    <div class="evol-diagram-collapse" id="evol-diagram-box">
      <div class="evol-principle" id="evol-diagram-content"></div>
    </div>
  </div>

  <!-- Stats Board -->
  <div style="margin-top:2.5rem">
    <h2 style="font-size:1.25rem;font-weight:600;margin-bottom:1rem">运行状态</h2>
    <div class="evol-stats">
      <div class="evol-stat-card">
        <div class="evol-stat-value">${escHtml(String(s.total_rounds || 0))}</div>
        <div class="evol-stat-label">进化轮数</div>
      </div>
      <div class="evol-stat-card">
        <div class="evol-stat-value">${escHtml(String(s.evolved_skills || 0))}</div>
        <div class="evol-stat-label">进化技能数</div>
      </div>
      <div class="evol-stat-card">
        <div class="evol-stat-value">${escHtml(improvement)}</div>
        <div class="evol-stat-label">成功率提升</div>
        <div class="evol-stat-sub">${escHtml(Math.round((s.original_accuracy || 0) * 100) + '% → ' + Math.round((s.improved_accuracy || 0) * 100) + '%')}</div>
      </div>
      <div class="evol-stat-card">
        <div class="evol-stat-value">${escHtml(String(s.running_instances || 0))}</div>
        <div class="evol-stat-label">运行实例</div>
      </div>
    </div>
  </div>

  <!-- Auto-scroll Log -->
  <div style="margin-top:2.5rem">
    <h2 style="font-size:1.25rem;font-weight:600;margin-bottom:1rem">实时日志</h2>
    <div class="evol-log-wrapper" id="evol-log-wrapper">
      <div class="evol-log-track" id="evol-log-track">
        ${logItems}
        ${logItems}
      </div>
    </div>
  </div>
</div>`;
  }

  function bindEvolutionEvents() {
    // Collapsible diagram: click to toggle, lazy-load SVG on first open
    var toggle = document.getElementById('evol-toggle-diagram');
    var box = document.getElementById('evol-diagram-box');
    var content = document.getElementById('evol-diagram-content');
    var loaded = false;
    if (toggle && box) {
      toggle.addEventListener('click', function () {
        var open = box.classList.toggle('open');
        toggle.classList.toggle('open', open);
        if (open && !loaded) {
          loaded = true;
          fetch('assets/evol-diagram.svg')
            .then(function (r) { return r.text(); })
            .then(function (svg) { if (content) content.innerHTML = svg; });
        }
      });
    }
  }

  function renderNotFound(type) {
    const isHarness = type === 'harness';
    const isAgent   = type === 'agent';
    const label    = isHarness ? '运行时' : isAgent ? '智能体' : '技能';
    const backHref = isHarness ? '#harnesses' : isAgent ? '#agents' : '#browse';
    return `<div style="text-align:center;padding:8rem 1rem">
      <p style="font-size:4rem;margin-bottom:1rem">🔍</p>
      <h2 style="font-size:1.5rem;font-weight:700;margin-bottom:.5rem">${label}未找到</h2>
      <p class="text-muted" style="margin-bottom:1.5rem">该${label}可能已被移除或链接有误。</p>
      <a class="btn-install" data-href="${backHref}" style="padding:.75rem 1.5rem;font-size:.875rem">浏览所有${label}</a>
    </div>`;
  }

  /* ===================== COPY ===================== */
  function copyText(text) {
    if (navigator.clipboard) {
      navigator.clipboard.writeText(text).then(() => showToast('已复制到剪贴板'));
    } else {
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.cssText = 'position:fixed;opacity:0;top:0;left:0';
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
      showToast('已复制到剪贴板');
    }
  }

  /* ===================== TOAST ===================== */
  function showToast(msg) {
    let toast = document.getElementById('toast');
    if (!toast) {
      toast = document.createElement('div');
      toast.id = 'toast';
      toast.className = 'toast';
      toast.setAttribute('role', 'status');
      toast.setAttribute('aria-live', 'polite');
      document.body.appendChild(toast);
    }
    toast.textContent = msg;
    toast.classList.add('show');
    clearTimeout(toast._timer);
    toast._timer = setTimeout(() => toast.classList.remove('show'), 2500);
  }

  /* ===================== MOBILE MENU ===================== */
  const mobileBtn  = document.getElementById('mobile-menu-btn');
  const mobileMenu = document.getElementById('mobile-menu');
  if (mobileBtn && mobileMenu) {
    mobileBtn.addEventListener('click', function () {
      const open = mobileMenu.style.display === 'block';
      mobileMenu.style.display = open ? 'none' : 'block';
      mobileBtn.setAttribute('aria-expanded', String(!open));
    });
    // FIX: close mobile menu when any [data-href] link is clicked (global listener handles navigation)
    mobileMenu.addEventListener('click', function (e) {
      if (e.target.closest('[data-href]')) {
        mobileMenu.style.display = 'none';
        mobileBtn.setAttribute('aria-expanded', 'false');
      }
    });
  }

  /* ===================== AUTH MODULE ===================== */
  const API_BASE = 'http://localhost:8000/api/auth';
  let currentUser = null;

  // Check for existing token on load
  function initAuth() {
    const token = localStorage.getItem('access_token');
    if (token) {
      fetchCurrentUser(token);
    }
    updateAuthUI();
    bindAuthEvents();
  }

  async function fetchCurrentUser(token) {
    try {
      const res = await fetch(API_BASE + '/me', {
        headers: { 'Authorization': 'Bearer ' + token }
      });
      if (res.ok) {
        currentUser = await res.json();
        updateAuthUI();
      } else {
        // Token invalid, clear it
        localStorage.removeItem('access_token');
        currentUser = null;
        updateAuthUI();
      }
    } catch (e) {
      console.error('Failed to fetch user:', e);
    }
  }

  function updateAuthUI() {
    const loggedOut = document.getElementById('auth-logged-out');
    const loggedIn = document.getElementById('auth-logged-in');
    const avatarText = document.getElementById('user-avatar-text');
    const displayName = document.getElementById('user-display-name');
    const userEmail = document.getElementById('user-email');

    if (currentUser) {
      loggedOut.style.display = 'none';
      loggedIn.style.display = 'flex';
      if (avatarText) avatarText.textContent = currentUser.username.charAt(0).toUpperCase();
      if (displayName) displayName.textContent = currentUser.username;
      if (userEmail) userEmail.textContent = currentUser.email;
    } else {
      loggedOut.style.display = 'flex';
      loggedIn.style.display = 'none';
    }
  }

  function bindAuthEvents() {
    // Login button
    const loginBtn = document.getElementById('login-btn');
    if (loginBtn) {
      loginBtn.addEventListener('click', () => showAuthModal('login'));
    }

    // Register button
    const registerBtn = document.getElementById('register-btn');
    if (registerBtn) {
      registerBtn.addEventListener('click', () => showAuthModal('register'));
    }

    // Modal close
    const modalClose = document.getElementById('modal-close');
    const modal = document.getElementById('auth-modal');
    const backdrop = modal ? modal.querySelector('.modal-backdrop') : null;
    if (modalClose) {
      modalClose.addEventListener('click', hideAuthModal);
    }
    if (backdrop) {
      backdrop.addEventListener('click', hideAuthModal);
    }

    // Switch between login/register
    const switchToRegister = document.getElementById('switch-to-register');
    const switchToLogin = document.getElementById('switch-to-login');
    if (switchToRegister) {
      switchToRegister.addEventListener('click', (e) => {
        e.preventDefault();
        showAuthModal('register');
      });
    }
    if (switchToLogin) {
      switchToLogin.addEventListener('click', (e) => {
        e.preventDefault();
        showAuthModal('login');
      });
    }

    // Login form
    const loginForm = document.getElementById('login-form');
    if (loginForm) {
      loginForm.addEventListener('submit', handleLogin);
    }

    // Register form
    const registerForm = document.getElementById('register-form');
    if (registerForm) {
      registerForm.addEventListener('submit', handleRegister);
    }

    // User dropdown
    const userMenuBtn = document.getElementById('user-menu-btn');
    const userDropdown = document.getElementById('user-dropdown');
    if (userMenuBtn && userDropdown) {
      userMenuBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        userDropdown.style.display = userDropdown.style.display === 'none' ? 'block' : 'none';
      });
      document.addEventListener('click', () => {
        userDropdown.style.display = 'none';
      });
    }

    // Logout
    const logoutBtn = document.getElementById('logout-btn');
    if (logoutBtn) {
      logoutBtn.addEventListener('click', (e) => {
        e.preventDefault();
        handleLogout();
      });
    }
  }

  function showAuthModal(type) {
    const modal = document.getElementById('auth-modal');
    const loginContainer = document.getElementById('login-form-container');
    const registerContainer = document.getElementById('register-form-container');
    const loginError = document.getElementById('login-error');
    const registerError = document.getElementById('register-error');

    if (modal) modal.style.display = 'flex';
    if (type === 'login') {
      if (loginContainer) loginContainer.style.display = 'block';
      if (registerContainer) registerContainer.style.display = 'none';
    } else {
      if (loginContainer) loginContainer.style.display = 'none';
      if (registerContainer) registerContainer.style.display = 'block';
    }
    if (loginError) loginError.style.display = 'none';
    if (registerError) registerError.style.display = 'none';
  }

  function hideAuthModal() {
    const modal = document.getElementById('auth-modal');
    if (modal) modal.style.display = 'none';
  }

  async function handleLogin(e) {
    e.preventDefault();
    const username = document.getElementById('login-username').value;
    const password = document.getElementById('login-password').value;
    const errorEl = document.getElementById('login-error');

    try {
      const res = await fetch(API_BASE + '/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password })
      });

      if (res.ok) {
        const data = await res.json();
        localStorage.setItem('access_token', data.access_token);
        await fetchCurrentUser(data.access_token);
        hideAuthModal();
        showToast('登录成功');
        document.getElementById('login-form').reset();
      } else {
        const err = await res.json();
        errorEl.textContent = err.detail || '登录失败，请检查用户名和密码';
        errorEl.style.display = 'block';
      }
    } catch (e) {
      errorEl.textContent = '网络错误，请稍后重试';
      errorEl.style.display = 'block';
    }
  }

  async function handleRegister(e) {
    e.preventDefault();
    const username = document.getElementById('register-username').value;
    const email = document.getElementById('register-email').value;
    const password = document.getElementById('register-password').value;
    const errorEl = document.getElementById('register-error');

    try {
      const res = await fetch(API_BASE + '/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, email, password })
      });

      if (res.ok || res.status === 201) {
        showToast('注册成功，请登录');
        showAuthModal('login');
        document.getElementById('register-form').reset();
        // Pre-fill username
        document.getElementById('login-username').value = username;
      } else {
        const err = await res.json();
        errorEl.textContent = err.detail || '注册失败';
        errorEl.style.display = 'block';
      }
    } catch (e) {
      errorEl.textContent = '网络错误，请稍后重试';
      errorEl.style.display = 'block';
    }
  }

  function handleLogout() {
    localStorage.removeItem('access_token');
    currentUser = null;
    updateAuthUI();
    showToast('已退出登录');
  }

  // Initialize auth on page load
  initAuth();
})();
