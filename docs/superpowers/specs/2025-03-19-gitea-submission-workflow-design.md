# Gitea Submission Workflow Design

## Overview

Adapt the GitHub-based skill submission workflow to work with a self-hosted Gitea instance (172.28.95.77:3000, version 1.25.5).

## Goals

- Replace GitHub Actions with Gitea Actions
- Support manual trigger via workflow_dispatch
- Support both GitHub and Gitea source repositories
- Remove external service dependencies (Supabase, Skillstore API)
- Single repository mode (skills stored in `pending/` directory)

## Non-Goals

- Issue comment monitoring (`/approve`, `/reject` commands)
- Parallel sharding for large repositories
- External API callbacks

## Architecture

```
User submits Issue
       ↓
Admin triggers workflow manually (Gitea UI / API)
       ↓
┌─────────────────────────────────────────────────────────────┐
│                    .gitea/workflows/submission.yml          │
│                                                             │
│  Job: process                                               │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 1. Parse source URL (GitHub/Gitea)                   │   │
│  │ 2. Clone source repository                           │   │
│  │ 3. Discover SKILL.md files                           │   │
│  │ 4. Process skills with skillstore-cli                │   │
│  │ 5. Create branch + commit to pending/                │   │
│  │ 6. Create PR via Gitea API                           │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
       ↓
PR awaits review → Merge activates skill
```

## Workflow Inputs

> **Note**: Gitea 1.25.5 Actions supports `workflow_dispatch` with inputs. The `type` field may not be fully supported - use string as default.

```yaml
on:
  workflow_dispatch:
    inputs:
      source_url:
        description: 'Repository URL (GitHub or Gitea)'
        required: true
      skill_path:
        description: 'Skill path (optional, e.g., .claude/skills/my-skill)'
        required: false
        default: ''
```

## URL Parsing Logic

Handle both GitHub and Gitea URL formats:

```bash
# URL format detection and parsing
parse_source_url() {
  local URL="$1"

  if [[ "$URL" =~ github\.com[:/]([^/]+)/([^/]+) ]]; then
    # GitHub URL
    PLATFORM="github"
    OWNER="${BASH_REMATCH[1]}"
    REPO="${BASH_REMATCH[2]}"
    REPO="${REPO%.git}"  # Remove .git suffix
    CLONE_URL="https://github.com/${OWNER}/${REPO}.git"

  elif [[ "$URL" =~ 172\.28\.95\.77:3000[:/]([^/]+)/([^/]+) ]] || \
       [[ "$URL" =~ gitea\.local[:/]([^/]+)/([^/]+) ]]; then
    # Gitea URL (IP or domain)
    PLATFORM="gitea"
    OWNER="${BASH_REMATCH[1]}"
    REPO="${BASH_REMATCH[2]}"
    REPO="${REPO%.git}"
    CLONE_URL="http://172.28.95.77:3000/${OWNER}/${REPO}.git"

  else
    echo "::error::Unsupported URL format: $URL"
    exit 1
  fi

  echo "platform=$PLATFORM"
  echo "owner=$OWNER"
  echo "repo=$REPO"
  echo "clone_url=$CLONE_URL"
}
```

## Authentication Strategy

| Source Type | Public Repo | Private Repo |
|-------------|-------------|--------------|
| GitHub | No auth needed | `GITHUB_TOKEN` secret (PAT) |
| Gitea | No auth needed | `GITEA_SOURCE_TOKEN` secret |

## Secrets Required

| Secret | Description | Required |
|--------|-------------|----------|
| `GITEA_TOKEN` | Target repo token (create PR, push) | Yes |
| `GITEA_SOURCE_TOKEN` | Source repo token (clone private Gitea repos) | Optional |
| `GITHUB_TOKEN` | Source repo token (clone private GitHub repos) | Optional |

## Output Structure

```
pending/
└── {owner}/
    └── {skill-slug}/
        ├── SKILL.md
        ├── skill-report.json
        └── (other files)
```

## Gitea API Reference

### Base URL

```
GITEA_API_URL=http://172.28.95.77:3000/api/v1
```

### Authentication Header

```bash
-H "Authorization: token ${GITEA_TOKEN}"
```

### Create Pull Request

```bash
curl -X POST "${GITEA_API_URL}/repos/${OWNER}/${REPO}/pulls" \
  -H "Authorization: token ${GITEA_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "New skill: my-skill",
    "head": "submission/20240319-120000",
    "base": "main",
    "body": "Skill submission from workflow"
  }'
```

### Add Labels to PR

```bash
# Note: In Gitea, PRs are also issues, use issue ID
curl -X POST "${GITEA_API_URL}/repos/${OWNER}/${REPO}/issues/${PR_NUMBER}/labels" \
  -H "Authorization: token ${GITEA_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"labels": ["pending-review"]}'
```

### Add Comment

```bash
curl -X POST "${GITEA_API_URL}/repos/${OWNER}/${REPO}/issues/${PR_NUMBER}/comments" \
  -H "Authorization: token ${GITEA_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"body": "Processing complete. Ready for review."}'
```

## skillstore-cli Integration

### Option A: Download from GitHub Releases (Recommended)

```bash
# Download latest CLI from GitHub
CLI_VERSION="latest"
DOWNLOAD_URL=$(curl -s "https://api.github.com/repos/ai-skill-store/skillstore-cli/releases/latest" | jq -r '.assets[] | select(.name | contains("linux-amd64")) | .browser_download_url')

curl -L -o skillstore-cli "$DOWNLOAD_URL"
chmod +x skillstore-cli
```

### Option B: Bundle in Repository

```bash
# CLI bundled at tools/skillstore-cli
chmod +x tools/skillstore-cli
./tools/skillstore-cli skill process "$SOURCE_URL" --output ./pending
```

### Option C: Docker Image

```yaml
- name: Process with skillstore-cli
  run: |
    docker run --rm \
      -v ${{ github.workspace }}:/workspace \
      -w /workspace \
      skillstore/cli:latest \
      skill process "${{ inputs.source_url }}" --output ./pending
```

## Error Handling

```bash
set -euo pipefail

# Cleanup function
cleanup() {
  echo "🧹 Cleaning up..."
  rm -rf /tmp/source-repo 2>/dev/null || true
  # Delete branch if workflow failed mid-process
  if [ -n "${BRANCH_NAME:-}" ]; then
    git push origin --delete "$BRANCH_NAME" 2>/dev/null || true
  fi
}
trap cleanup EXIT

# Retry logic
retry() {
  local max_attempts=3
  local delay=10
  local attempt=1

  while [ $attempt -le $max_attempts ]; do
    if "$@"; then
      return 0
    fi
    echo "::warning::Attempt $attempt failed, retrying in ${delay}s..."
    sleep $delay
    attempt=$((attempt + 1))
  done

  echo "::error::Command failed after $max_attempts attempts: $*"
  return 1
}

# Usage
retry git clone --depth 1 "$CLONE_URL" /tmp/source-repo
```

## Branch Naming Convention

```
submission/{timestamp}
submission/20240319-120000
```

### Branch Cleanup Before Creating

```bash
# Delete existing branch if present (from previous failed run)
git push origin --delete "$BRANCH_NAME" 2>/dev/null || true
```

## Runner Deployment

### Step 1: Get Registration Token

From Gitea UI: **Site Administration → Actions → Runners → Create new Runner**

Or via API:
```bash
curl -X POST "http://172.28.95.77:3000/api/v1/admin/runners/registration-token" \
  -H "Authorization: token ${ADMIN_TOKEN}"
```

### Step 2: Deploy Runner

```yaml
# docker-compose.runner.yml
version: "3"

services:
  act-runner:
    image: gitea/act_runner:latest
    container_name: gitea-act-runner
    environment:
      - GITEA_INSTANCE_URL=http://172.28.95.77:3000
      - GITEA_RUNNER_REGISTRATION_TOKEN=${REGISTRATION_TOKEN}
    volumes:
      - ./data/act_runner:/data
      - /var/run/docker.sock:/var/run/docker.sock
      - ./cache:/cache  # Optional: cache directory
    restart: unless-stopped
    # Optional: resource limits
    deploy:
      resources:
        limits:
          memory: 2G
```

### Step 3: Register Runner

```bash
# Runner auto-registers on first start
# Verify registration:
docker logs gitea-act-runner | grep "runner registered"
```

## File Structure

```
.gitea/
└── workflows/
    └── submission.yml          # Submission workflow

pending/                         # Processed skills (auto-generated)
└── (owner)/(skill-slug)/

skills/                          # Active skills directory
└── ...

tools/                           # Optional: bundled CLI
└── skillstore-cli
```

## Logging & Observability

- **View Logs**: Gitea UI → Repository → Actions → Click workflow run
- **Download Logs**: Available in Actions UI after run completes
- **Debug Mode**: Add `ACTIONS_STEP_DEBUG=true` to secrets for verbose output

## Migration Steps

1. **Deploy Runner** on Gitea server (172.28.95.77)
2. **Create Token** with `repo` permission
3. **Add Secrets** to repository:
   - `GITEA_TOKEN` (required)
   - `GITEA_SOURCE_TOKEN` (optional, for private sources)
   - `GITHUB_TOKEN` (optional, for private GitHub sources)
4. **Create Workflow** at `.gitea/workflows/submission.yml`
5. **Test** with manual trigger via Gitea UI

## Removed Features

- Issue comment monitoring (`issue_comment` event not supported)
- Supabase sync
- Skillstore API callbacks
- Parallel sharding (simplified for single-workflow approach)
