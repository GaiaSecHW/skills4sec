#!/usr/bin/env node
/**
 * Build script for the skills4sec static site.
 *
 * What it does:
 *  1. Scans skills/ for skill-report.json files
 *  2. Generates docs/data/skills.json (normalized skill data consumed by app.js)
 *  3. Ensures docs/.nojekyll exists (required for GitHub Pages)
 *
 * The HTML/CSS/JS shell lives in docs/ and is maintained separately.
 *
 * Usage:  node scripts/build-site.js
 *         npm run build:site
 */

const fs   = require('fs');
const path = require('path');

const ROOT          = path.resolve(__dirname, '..');
const SKILLS_DIR    = path.join(ROOT, 'skills');
const HARNESSES_DIR = path.join(ROOT, 'harnesses');
const AGENTS_DIR    = path.join(ROOT, 'agents');
const DOCS_DIR      = path.join(ROOT, 'docs');
const DATA_DIR      = path.join(DOCS_DIR, 'data');

/* ── Helpers ─────────────────────────────────────────── */
function ensureDir(dir) {
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
}

function readJson(file) {
  try { return JSON.parse(fs.readFileSync(file, 'utf8')); }
  catch (e) {
    console.warn(`  ⚠ Could not parse ${path.relative(ROOT, file)}: ${e.message}`);
    return null;
  }
}

/* ── 1. Collect skills ───────────────────────────────── */
function collectSkills() {
  const skills = [];
  if (!fs.existsSync(SKILLS_DIR)) {
    console.warn('  ⚠ skills/ directory not found');
    return skills;
  }

  for (const entry of fs.readdirSync(SKILLS_DIR).sort()) {
    const dir = path.join(SKILLS_DIR, entry);
    if (!fs.statSync(dir).isDirectory()) continue;

    const reportPath = path.join(dir, 'skill-report.json');
    if (!fs.existsSync(reportPath)) {
      console.warn(`  ⚠ No skill-report.json in ${entry}, skipping`);
      continue;
    }

    const report = readJson(reportPath);
    if (!report) continue;

    const s  = report.skill          || {};
    const sa = report.security_audit || {};
    const c  = report.content        || {};
    const m  = report.meta           || {};

    // Validate required fields
    if (!s.name) {
      console.warn(`  ⚠ ${entry}/skill-report.json missing skill.name, skipping`);
      continue;
    }

    skills.push({
      _dir:              entry, // actual directory name for diff copying
      slug:              m.slug             || entry,
      name:              s.name,
      summary:           s.summary          || s.description || '',
      description:       s.description      || '',
      icon:              s.icon             || '📦',
      version:           s.version          || '1.0.0',
      author:            s.author           || 'unknown',
      license:           s.license          || '',
      category:          s.category         || '',
      tags:              s.tags             || [],
      supported_tools:   s.supported_tools  || [],
      risk_factors:      s.risk_factors     || [],
      risk_level:        sa.risk_level      || 'safe',
      is_blocked:        sa.is_blocked      || false,
      safe_to_publish:   sa.safe_to_publish !== false,
      source_url:        m.source_url       || '',
      source_type:       m.source_type      || '',
      generated_at:      m.generated_at     || '',
      // content fields (shown on detail page)
      user_title:        c.user_title       || '',
      value_statement:   c.value_statement  || '',
      actual_capabilities: c.actual_capabilities || [],
      use_cases:         c.use_cases        || [],
      prompt_templates:  c.prompt_templates || [],
      limitations:       c.limitations      || [],
      faq:               c.faq              || [],
      // diff files: scanned from skills/{slug}/.diff/*.diff, sorted by filename
      diffs: (() => {
        const diffDir = path.join(dir, '.diff');
        if (!fs.existsSync(diffDir)) return [];
        return fs.readdirSync(diffDir).filter(f => f.endsWith('.diff')).sort();
      })(),
    });
  }

  // Sort: safest first (safe → low → medium → high), then alphabetically
  const riskRank = { safe: 0, low: 1, medium: 2, high: 3 };
  skills.sort((a, b) => {
    const rd = (riskRank[a.risk_level] ?? 9) - (riskRank[b.risk_level] ?? 9);
    return rd !== 0 ? rd : a.name.localeCompare(b.name);
  });

  return skills;
}

/* ── 2. Collect harnesses ────────────────────────────── */
function collectHarnesses() {
  const harnesses = [];
  if (!fs.existsSync(HARNESSES_DIR)) {
    console.warn('  ⚠ harnesses/ directory not found');
    return harnesses;
  }

  for (const entry of fs.readdirSync(HARNESSES_DIR).sort()) {
    const dir = path.join(HARNESSES_DIR, entry);
    if (!fs.statSync(dir).isDirectory()) continue;

    const reportPath = path.join(dir, 'harness-report.json');
    if (!fs.existsSync(reportPath)) {
      console.warn(`  ⚠ No harness-report.json in ${entry}, skipping`);
      continue;
    }

    const report = readJson(reportPath);
    if (!report) continue;

    const h = report.harness || {};
    const c = report.content || {};
    const m = report.meta    || {};

    if (!h.name) {
      console.warn(`  ⚠ ${entry}/harness-report.json missing harness.name, skipping`);
      continue;
    }

    harnesses.push({
      slug:            m.slug           || entry,
      name:            h.name,
      summary:         h.description    || '',
      icon:            h.icon           || '🖥️',
      version:         h.version        || '1.0.0',
      author:          h.author         || 'unknown',
      env_type:        h.env_type       || 'image',
      base_image:      h.base_image     || '',
      ssh_host:        h.ssh_host       || '',
      ssh_user:        h.ssh_user       || '',
      supported_tools: h.supported_tools || [],
      tags:            h.tags           || [],
      source_url:      m.source_url     || '',
      value_statement: c.value_statement || '',
      capabilities:    c.capabilities   || [],
      use_cases:       c.use_cases      || [],
    });
  }

  harnesses.sort((a, b) => a.name.localeCompare(b.name));
  return harnesses;
}

/* ── 3. Collect agents ───────────────────────────────── */
function collectAgents() {
  const agents = [];
  if (!fs.existsSync(AGENTS_DIR)) {
    console.warn('  ⚠ agents/ directory not found');
    return agents;
  }

  for (const entry of fs.readdirSync(AGENTS_DIR).sort()) {
    const dir = path.join(AGENTS_DIR, entry);
    if (!fs.statSync(dir).isDirectory()) continue;

    const configPath = path.join(dir, 'config.json');
    if (!fs.existsSync(configPath)) {
      console.warn(`  ⚠ No config.json in agents/${entry}, skipping`);
      continue;
    }

    const config = readJson(configPath);
    if (!config || !config.name) {
      console.warn(`  ⚠ agents/${entry}/config.json missing name, skipping`);
      continue;
    }

    const agentMdPath = path.join(dir, 'AGENT.md');
    const agentMd = fs.existsSync(agentMdPath)
      ? fs.readFileSync(agentMdPath, 'utf8')
      : '';

    agents.push({
      slug:        config.slug        || entry,
      name:        config.name,
      icon:        config.icon        || '🤖',
      description: config.description || '',
      author:      config.author      || 'unknown',
      version:     config.version     || '1.0.0',
      tags:        config.tags        || [],
      skill:       config.skill       || null,
      mcp:         config.mcp         || [],
      agent_md:    agentMd,
    });
  }

  agents.sort((a, b) => a.name.localeCompare(b.name));
  return agents;
}

/* ── 4. Write docs/data/skills.json ─────────────────── */
function writeSkillsJson(skills) {
  ensureDir(DATA_DIR);
  const dest = path.join(DATA_DIR, 'skills.json');
  fs.writeFileSync(dest, JSON.stringify(skills, null, 2) + '\n', 'utf8');
  console.log(`✓ docs/data/skills.json — ${skills.length} skill(s)`);
  skills.forEach(s => console.log(`   · ${s.slug} [${s.risk_level}]`));
}

/* ── 4b. Copy .diff files to docs/data/diffs/{slug}/ ── */
function copyDiffs(skills) {
  for (const skill of skills) {
    if (!skill.diffs.length) continue;
    const srcDir  = path.join(SKILLS_DIR, skill._dir, '.diff');
    const destDir = path.join(DATA_DIR, 'diffs', skill.slug);
    ensureDir(destDir);
    for (const file of skill.diffs) {
      fs.copyFileSync(path.join(srcDir, file), path.join(destDir, file));
    }
    console.log(`✓ diffs copied for ${skill.slug} (${skill.diffs.length} file(s))`);
  }
}

/* ── 5. Write docs/data/harnesses.json ──────────────── */
function writeHarnessesJson(harnesses) {
  ensureDir(DATA_DIR);
  const dest = path.join(DATA_DIR, 'harnesses.json');
  fs.writeFileSync(dest, JSON.stringify(harnesses, null, 2) + '\n', 'utf8');
  console.log(`✓ docs/data/harnesses.json — ${harnesses.length} harness(es)`);
  harnesses.forEach(h => console.log(`   · ${h.slug} [${h.env_type}]`));
}

/* ── 6. Write docs/data/agents.json ─────────────────── */
function writeAgentsJson(agents) {
  ensureDir(DATA_DIR);
  const dest = path.join(DATA_DIR, 'agents.json');
  fs.writeFileSync(dest, JSON.stringify(agents, null, 2) + '\n', 'utf8');
  console.log(`✓ docs/data/agents.json — ${agents.length} agent(s)`);
  agents.forEach(a => console.log(`   · ${a.slug}`));
}

/* ── 7. Ensure .nojekyll ─────────────────────────────── */
function ensureNojekyll() {
  const dest = path.join(DOCS_DIR, '.nojekyll');
  if (!fs.existsSync(dest)) {
    fs.writeFileSync(dest, '', 'utf8');
    console.log('✓ docs/.nojekyll created');
  }
}

/* ── Main ────────────────────────────────────────────── */
(function main() {
  console.log('Building skills4sec static site…\n');
  ensureDir(DOCS_DIR);
  const skills    = collectSkills();
  const harnesses = collectHarnesses();
  const agents    = collectAgents();
  writeSkillsJson(skills);
  copyDiffs(skills);
  writeHarnessesJson(harnesses);
  writeAgentsJson(agents);
  ensureNojekyll();
  console.log('\nDone.');
})();
