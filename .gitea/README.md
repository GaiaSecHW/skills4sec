# Gitea Actions Workflows

## Available Workflows

### 1. submission.yml - 技能提交处理

Process skill submissions from GitHub or Gitea repositories.

**Trigger:** Manual (workflow_dispatch)

**Inputs:**
- `source_url` (required): Repository URL (GitHub or Gitea)
- `skill_path` (optional): Path to skill within repository

**Output:** Creates PR with skills in `pending/` directory

**Example:**
```
Source URL: https://github.com/owner/skill-repo
Skill Path: .claude/skills/my-skill (optional)
```

---

### 2. on-pr-merge.yml - PR 合并自动批准

Automatically moves skills from `pending/` to `skills/` when PR is merged.

**Trigger:** Pull request closed (merged to main)

**Behavior:**
1. Detects merged PR
2. Finds all SKILL.md in `pending/`
3. Moves skills to `skills/{owner}/{skill-name}/`
4. Commits and pushes to main

**No manual intervention required** - triggered automatically.

---

### 3. audit-skills.yml - 技能安全审计

Security audit for skills using rule-based analysis (from skill-report-generator).

**Trigger:** Manual (workflow_dispatch)

**Inputs:**
- `target` (default: `pending`): Directory to audit (`pending` or `skills`)
- `slugs` (optional): Specific skill slugs (comma-separated)
- `dry_run` (default: `false`): Preview without creating PR

**Audit Rules:**
| Risk Factor | Patterns Detected |
|-------------|-------------------|
| scripts | .sh, .py, .js, .ts, .mjs, .ps1, .bat files |
| network | http://, fetch(, axios, requests., curl |
| filesystem | open(, .write(, Path(, os.remove, shutil. |
| env_access | os.environ, process.env, dotenv, getenv |
| external_commands | subprocess, exec(, eval(, os.system |

**Risk Levels:**
- `safe` - No executable code detected
- `low` - Low-risk features only
- `medium` - Potentially sensitive patterns
- `high` - Dangerous patterns (eval, exec, etc.)
- `critical` - Critical security risks

**Example:**
```
Target: pending
Slugs: owner-skill1, owner-skill2 (optional)
Dry Run: false
```

---

## Required Secrets

| Secret | Description | Required For |
|--------|-------------|--------------|
| `GITEATOKEN` | Token with repo permission | All workflows |
| `GITEA_SOURCE_TOKEN` | For private Gitea sources | submission.yml |
| `GITHUB_TOKEN` | For private GitHub sources | submission.yml |

**Note:** Gitea secrets cannot contain underscores. Use `GITEATOKEN` not `GITEA_TOKEN`.

---

## Runner Setup

### 1. Get Registration Token

From Gitea UI: **Site Administration → Actions → Runners → Create new Runner**

### 2. Deploy Runner

```bash
export REGISTRATION_TOKEN=your-token
docker-compose -f docker-compose.runner.yml up -d
```

### 3. With Network Access (for GitHub)

If runner needs to access GitHub, use host network mode:

```bash
docker run -d --name gitea-act-runner \
  --network host \
  -e GITEA_INSTANCE_URL=http://172.28.95.77:3000 \
  -e GITEA_RUNNER_REGISTRATION_TOKEN=${REGISTRATION_TOKEN} \
  -e GITEA_RUNNER_NAME=gitea-runner-01 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v act-runner-data:/data \
  gitea/act_runner:latest
```

### 4. Verify Registration

```bash
docker logs gitea-act-runner | grep "runner registered"
```

---

## Workflow Summary

```
┌─────────────────────────────────────────────────────────────────┐
│                     Skill Submission Flow                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. submission.yml (manual trigger)                             │
│     └─→ Clone source repo                                       │
│     └─→ Discover SKILL.md files                                 │
│     └─→ Copy to pending/{owner}/{slug}/                         │
│     └─→ Create PR                                               │
│                                                                  │
│  2. audit-skills.yml (manual trigger)                           │
│     └─→ Scan pending/ or skills/                                │
│     └─→ Apply security rules                                    │
│     └─→ Update skill-report.json                                │
│     └─→ Create PR                                               │
│                                                                  │
│  3. on-pr-merge.yml (automatic)                                 │
│     └─→ Detect merged PR                                        │
│     └─→ Move pending/* → skills/*                               │
│     └─→ Commit to main                                          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Testing

1. Go to Repository → Actions
2. Select workflow
3. Click "Run workflow"
4. Enter parameters
5. Click "Run"
