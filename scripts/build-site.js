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

const ROOT       = path.resolve(__dirname, '..');
const SKILLS_DIR = path.join(ROOT, 'skills');
const DOCS_DIR   = path.join(ROOT, 'docs');
const DATA_DIR   = path.join(DOCS_DIR, 'data');

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

/* ── 2. Write docs/data/skills.json ─────────────────── */
function writeSkillsJson(skills) {
  ensureDir(DATA_DIR);
  const dest = path.join(DATA_DIR, 'skills.json');
  fs.writeFileSync(dest, JSON.stringify(skills, null, 2), 'utf8');
  console.log(`✓ docs/data/skills.json — ${skills.length} skill(s)`);
  skills.forEach(s => console.log(`   · ${s.slug} [${s.risk_level}]`));
}

/* ── 3. Ensure .nojekyll ─────────────────────────────── */
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
  const skills = collectSkills();
  writeSkillsJson(skills);
  ensureNojekyll();
  console.log('\nDone.');
})();
