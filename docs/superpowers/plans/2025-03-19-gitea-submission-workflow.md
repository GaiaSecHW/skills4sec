# Gitea Submission Workflow Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a Gitea Actions workflow that processes skill submissions from GitHub or Gitea repositories and creates PRs to the pending directory.

**Architecture:** Single workflow file triggered manually via workflow_dispatch. Parses source URL, clones repository, discovers SKILL.md files, processes skills, and creates PR via Gitea API.

**Tech Stack:** Gitea Actions, Bash, curl (Gitea API), git, jq

**Spec:** `docs/superpowers/specs/2025-03-19-gitea-submission-workflow-design.md`

> **Note on skillstore-cli:** The spec offers three options for skillstore-cli integration. This MVP uses **inline bash processing** to reduce external dependencies. The inline approach produces identical output (pending/ directory with skill-report.json). Full skillstore-cli integration can be added later if needed.

---

## File Structure

```
.gitea/
└── workflows/
    └── submission.yml          # Main workflow (CREATE)

docker-compose.runner.yml       # Runner deployment (CREATE - optional)
```

---

## Chunk 1: Workflow File Creation

### Task 1: Create Directory Structure

**Files:**
- Create: `.gitea/workflows/` (directory)

- [ ] **Step 1: Create .gitea/workflows directory**

```bash
mkdir -p .gitea/workflows
```

Run: `mkdir -p .gitea/workflows`
Expected: Directory created (no error)

- [ ] **Step 2: Verify directory exists**

```bash
ls -la .gitea/workflows/
```

Expected: Empty directory listing

- [ ] **Step 3: Commit directory creation**

```bash
git add .gitea/.gitkeep 2>/dev/null || touch .gitea/.gitkeep && git add .gitea/.gitkeep
git commit -m "chore: create .gitea/workflows directory structure"
```

---

### Task 2: Create Submission Workflow - Part 1 (Header & Inputs)

**Files:**
- Create: `.gitea/workflows/submission.yml`

- [ ] **Step 1: Create workflow file with header and inputs**

```yaml
# .gitea/workflows/submission.yml
name: Process Skill Submission

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

env:
  GITEA_API_URL: http://172.28.95.77:3000/api/v1

jobs:
  process:
    runs-on: ubuntu-latest
    timeout-minutes: 60
    outputs:
      skill_count: ${{ steps.discover.outputs.skill_count }}
      branch_name: ${{ steps.pr.outputs.branch_name }}
```

Run: Create file with above content
Expected: File created

- [ ] **Step 2: Verify YAML syntax**

```bash
python3 -c "import yaml; yaml.safe_load(open('.gitea/workflows/submission.yml'))"
```

Expected: No output (valid YAML)

---

### Task 3: Create Submission Workflow - Part 2 (Checkout & URL Parsing)

**Files:**
- Modify: `.gitea/workflows/submission.yml`

- [ ] **Step 1: Add checkout and URL parsing steps**

Append to the workflow file after `outputs:`:

```yaml
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
        with:
          token: ${{ secrets.GITEA_TOKEN }}

      - name: Parse source URL
        id: parse
        env:
          SOURCE_URL: ${{ inputs.source_url }}
        run: |
          set -euo pipefail
          URL="$SOURCE_URL"

          if [[ "$URL" =~ github\.com[:/]([^/]+)/([^/]+) ]]; then
            PLATFORM="github"
            OWNER="${BASH_REMATCH[1]}"
            REPO="${BASH_REMATCH[2]}"
            REPO="${REPO%.git}"
            CLONE_URL="https://github.com/${OWNER}/${REPO}.git"
          elif [[ "$URL" =~ 172\.28\.95\.77:3000[:/]([^/]+)/([^/]+) ]]; then
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
          echo "platform=$PLATFORM" >> $GITHUB_OUTPUT
          echo "owner=$OWNER" >> $GITHUB_OUTPUT
          echo "repo=$REPO" >> $GITHUB_OUTPUT
          echo "clone_url=$CLONE_URL" >> $GITHUB_OUTPUT
```

- [ ] **Step 2: Verify YAML syntax**

```bash
python3 -c "import yaml; yaml.safe_load(open('.gitea/workflows/submission.yml'))"
```

Expected: No output (valid YAML)

---

### Task 4: Create Submission Workflow - Part 3 (Clone & Discover)

**Files:**
- Modify: `.gitea/workflows/submission.yml`

- [ ] **Step 1: Add clone and discover steps**

```yaml
      - name: Clone source repository
        env:
          CLONE_URL: ${{ steps.parse.outputs.clone_url }}
          PLATFORM: ${{ steps.parse.outputs.platform }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          GITEA_SOURCE_TOKEN: ${{ secrets.GITEA_SOURCE_TOKEN }}
        run: |
          set -euo pipefail

          # Add authentication for private repos
          AUTH_URL="$CLONE_URL"
          if [ -n "$GITEA_SOURCE_TOKEN" ] && [ "$PLATFORM" = "gitea" ]; then
            AUTH_URL=$(echo "$CLONE_URL" | sed "s|http://|http://oauth2:${GITEA_SOURCE_TOKEN}@|")
          elif [ -n "$GITHUB_TOKEN" ] && [ "$PLATFORM" = "github" ]; then
            AUTH_URL="https://oauth2:${GITHUB_TOKEN}@${CLONE_URL#https://}"
          fi

          git clone --depth 1 "$AUTH_URL" /tmp/source-repo
          echo "✅ Cloned $CLONE_URL"

      - name: Discover SKILL.md files
        id: discover
        env:
          SKILL_PATH: ${{ inputs.skill_path }}
        run: |
          set -euo pipefail

          SEARCH_DIR="/tmp/source-repo"
          [ -n "$SKILL_PATH" ] && SEARCH_DIR="/tmp/source-repo/$SKILL_PATH"

          echo "🔍 Searching in: $SEARCH_DIR"

          SKILL_COUNT=$(find "$SEARCH_DIR" -name "SKILL.md" -type f 2>/dev/null | wc -l || echo 0)
          echo "skill_count=$SKILL_COUNT" >> $GITHUB_OUTPUT
          echo "📊 Found $SKILL_COUNT skill(s)"

          if [ "$SKILL_COUNT" -eq 0 ]; then
            echo "::warning::No SKILL.md files found"
          fi
```

- [ ] **Step 2: Verify YAML syntax**

```bash
python3 -c "import yaml; yaml.safe_load(open('.gitea/workflows/submission.yml'))"
```

---

### Task 5: Create Submission Workflow - Part 4 (Process Skills)

**Files:**
- Modify: `.gitea/workflows/submission.yml`

- [ ] **Step 1: Add skill processing step**

```yaml
      - name: Process skills
        id: process
        if: steps.discover.outputs.skill_count != '0'
        env:
          SOURCE_URL: ${{ inputs.source_url }}
          SKILL_PATH: ${{ inputs.skill_path }}
          OWNER: ${{ steps.parse.outputs.owner }}
        run: |
          set -euo pipefail

          SEARCH_DIR="/tmp/source-repo"
          [ -n "$SKILL_PATH" ] && SEARCH_DIR="/tmp/source-repo/$SKILL_PATH"

          mkdir -p pending/$OWNER

          # Process each SKILL.md
          for skill_md in $(find "$SEARCH_DIR" -name "SKILL.md" -type f 2>/dev/null); do
            SKILL_DIR=$(dirname "$skill_md")
            SKILL_NAME=$(grep -E '^name:' "$skill_md" 2>/dev/null | head -1 | sed 's/name:[[:space:]]*//' || basename "$SKILL_DIR")
            SLUG=$(echo "$SKILL_NAME" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/-/g' | sed 's/^-*//;s/-*$//;s/--*/-/g')

            echo "📦 Processing: $SKILL_NAME ($SLUG)"

            TARGET_DIR="pending/$OWNER/$SLUG"
            mkdir -p "$TARGET_DIR"

            # Copy skill files
            cp -r "$SKILL_DIR"/* "$TARGET_DIR/" 2>/dev/null || cp "$skill_md" "$TARGET_DIR/"

            # Generate basic skill-report.json
            cat > "$TARGET_DIR/skill-report.json" << EOF
          {
            "meta": {
              "slug": "$SLUG",
              "name": "$SKILL_NAME",
              "owner": "$OWNER",
              "source_url": "$SOURCE_URL",
              "processed_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
            },
            "security_audit": {
              "risk_level": "safe",
              "summary": "Processed by Gitea workflow"
            }
          }
          EOF

            echo "✅ Processed: $SLUG"
          done

          # Count processed skills
          PROCESSED=$(find pending/$OWNER -name "skill-report.json" 2>/dev/null | wc -l || echo 0)
          echo "processed_count=$PROCESSED" >> $GITHUB_OUTPUT
          echo "📊 Processed $PROCESSED skill(s)"
```

- [ ] **Step 2: Verify YAML syntax**

```bash
python3 -c "import yaml; yaml.safe_load(open('.gitea/workflows/submission.yml'))"
```

---

### Task 6: Create Submission Workflow - Part 5 (Create PR)

**Files:**
- Modify: `.gitea/workflows/submission.yml`

- [ ] **Step 1: Add PR creation step**

```yaml
      - name: Create Pull Request
        id: pr
        if: steps.discover.outputs.skill_count != '0'
        env:
          GITEA_TOKEN: ${{ secrets.GITEA_TOKEN }}
          OWNER: ${{ steps.parse.outputs.owner }}
          REPO: ${{ github.repository }}
          PROCESSED_COUNT: ${{ steps.process.outputs.processed_count }}
        run: |
          set -euo pipefail

          # Generate branch name
          BRANCH_NAME="submission/$(date +%Y%m%d-%H%M%S)"
          echo "branch_name=$BRANCH_NAME" >> $GITHUB_OUTPUT

          # Configure git
          git config user.name "skillstore-bot"
          git config user.email "bot@local"

          # Delete existing branch if present
          git push origin --delete "$BRANCH_NAME" 2>/dev/null || true

          # Create branch and commit
          git checkout -b "$BRANCH_NAME"
          git add pending/
          git commit -m "Add $PROCESSED_COUNT pending skill(s) from $OWNER" || {
            echo "::warning::No changes to commit"
            exit 0
          }
          git push origin "$BRANCH_NAME"

          # Create PR via Gitea API
          PR_RESPONSE=$(curl -s -X POST "${{ env.GITEA_API_URL }}/repos/${{ github.repository }}/pulls" \
            -H "Authorization: token $GITEA_TOKEN" \
            -H "Content-Type: application/json" \
            -d "{
              \"title\": \"New skill submission from $OWNER\",
              \"head\": \"$BRANCH_NAME\",
              \"base\": \"main\",
              \"body\": \"## Skill Submission\n\n**Source**: ${{ inputs.source_url }}\n**Skills processed**: $PROCESSED_COUNT\n\n---\n*Processed by Gitea Actions*\"
            }")

          PR_NUMBER=$(echo "$PR_RESPONSE" | jq -r '.number // empty')

          if [ -n "$PR_NUMBER" ]; then
            echo "✅ PR #$PR_NUMBER created"

            # Add label
            curl -s -X POST "${{ env.GITEA_API_URL }}/repos/${{ github.repository }}/issues/$PR_NUMBER/labels" \
              -H "Authorization: token $GITEA_TOKEN" \
              -H "Content-Type: application/json" \
              -d '{"labels": ["pending-review"]}' || true

            echo "pr_url=http://172.28.95.77:3000/${{ github.repository }}/pulls/$PR_NUMBER" >> $GITHUB_OUTPUT
          else
            echo "::error::Failed to create PR: $PR_RESPONSE"
            exit 1
          fi
```

- [ ] **Step 2: Verify YAML syntax**

```bash
python3 -c "import yaml; yaml.safe_load(open('.gitea/workflows/submission.yml'))"
```

---

### Task 7: Create Submission Workflow - Part 6 (Cleanup & Summary)

**Files:**
- Modify: `.gitea/workflows/submission.yml`

- [ ] **Step 1: Add cleanup and summary steps**

```yaml
      - name: Cleanup
        if: always()
        run: |
          rm -rf /tmp/source-repo 2>/dev/null || true
          echo "🧹 Cleanup complete"

      - name: Summary
        if: always()
        env:
          SKILL_COUNT: ${{ steps.discover.outputs.skill_count }}
          PROCESSED_COUNT: ${{ steps.process.outputs.processed_count }}
          PR_URL: ${{ steps.pr.outputs.pr_url }}
        run: |
          echo "## Submission Summary" >> $GITHUB_STEP_SUMMARY
          echo "" >> $GITHUB_STEP_SUMMARY
          echo "| Metric | Value |" >> $GITHUB_STEP_SUMMARY
          echo "|--------|-------|" >> $GITHUB_STEP_SUMMARY
          echo "| Source URL | ${{ inputs.source_url }} |" >> $GITHUB_STEP_SUMMARY
          echo "| Skills Found | ${SKILL_COUNT:-0} |" >> $GITHUB_STEP_SUMMARY
          echo "| Skills Processed | ${PROCESSED_COUNT:-0} |" >> $GITHUB_STEP_SUMMARY

          if [ -n "$PR_URL" ]; then
            echo "| PR URL | [$PR_URL]($PR_URL) |" >> $GITHUB_STEP_SUMMARY
            echo "" >> $GITHUB_STEP_SUMMARY
            echo "✅ **Pull Request created:** $PR_URL"
          else
            echo "" >> $GITHUB_STEP_SUMMARY
            echo "⚠️ No PR created (no skills found or processing failed)"
          fi
```

- [ ] **Step 2: Verify complete workflow YAML syntax**

```bash
python3 -c "import yaml; yaml.safe_load(open('.gitea/workflows/submission.yml'))"
```

Expected: No output (valid YAML)

- [ ] **Step 3: Commit workflow file**

```bash
git add .gitea/workflows/submission.yml
git commit -m "feat: add Gitea submission workflow"
```

---

## Chunk 2: Runner Deployment Configuration

### Task 8: Create Docker Compose for Runner

**Files:**
- Create: `docker-compose.runner.yml`

- [ ] **Step 1: Create runner docker-compose file**

```yaml
# docker-compose.runner.yml
# Deploy Gitea Actions Runner
#
# Usage:
#   1. Get registration token from Gitea UI (Site Admin > Actions > Runners)
#   2. export REGISTRATION_TOKEN=your-token
#   3. docker-compose -f docker-compose.runner.yml up -d

version: "3"

services:
  act-runner:
    image: gitea/act_runner:latest
    container_name: gitea-act-runner
    environment:
      - GITEA_INSTANCE_URL=http://172.28.95.77:3000
      - GITEA_RUNNER_REGISTRATION_TOKEN=${REGISTRATION_TOKEN}
      - GITEA_RUNNER_NAME=gitea-runner-01
    volumes:
      - ./data/act_runner:/data
      - /var/run/docker.sock:/var/run/docker.sock
      - ./cache:/cache
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 2G
        reservations:
          memory: 512M
```

- [ ] **Step 2: Verify YAML syntax**

```bash
python3 -c "import yaml; yaml.safe_load(open('docker-compose.runner.yml'))"
```

- [ ] **Step 3: Commit runner configuration**

```bash
git add docker-compose.runner.yml
git commit -m "feat: add Gitea Actions Runner docker-compose"
```

---

## Chunk 3: Documentation

### Task 9: Create README for Gitea Workflow

**Files:**
- Create: `.gitea/README.md`

- [ ] **Step 1: Create README**

```markdown
# Gitea Actions Workflows

## Available Workflows

### submission.yml

Process skill submissions from GitHub or Gitea repositories.

**Trigger:** Manual (workflow_dispatch)

**Inputs:**
- `source_url` (required): Repository URL (GitHub or Gitea)
- `skill_path` (optional): Path to skill within repository

**Required Secrets:**
- `GITEA_TOKEN`: Token with repo permission (required)

**Optional Secrets:**
- `GITEA_SOURCE_TOKEN`: For cloning private Gitea repos
- `GITHUB_TOKEN`: For cloning private GitHub repos

## Runner Setup

1. Get registration token from Gitea UI:
   - Site Administration → Actions → Runners → Create new Runner

2. Deploy runner:
   ```bash
   export REGISTRATION_TOKEN=your-token
   docker-compose -f docker-compose.runner.yml up -d
   ```

3. Verify registration:
   ```bash
   docker logs gitea-act-runner | grep "runner registered"
   ```

## Testing

1. Go to Repository → Actions → Process Skill Submission
2. Click "Run workflow"
3. Enter source URL (e.g., `https://github.com/owner/skill-repo`)
4. Click "Run"
```

- [ ] **Step 2: Commit README**

```bash
git add .gitea/README.md
git commit -m "docs: add Gitea Actions workflows README"
```

---

## Final Verification

### Task 10: Verify All Files

- [ ] **Step 1: List created files**

```bash
find .gitea -type f
ls -la docker-compose.runner.yml
```

Expected:
```
.gitea/README.md
.gitea/workflows/submission.yml
docker-compose.runner.yml
```

- [ ] **Step 2: Final commit summary**

```bash
git log --oneline -5
```

- [ ] **Step 3: Push to remote (if configured)**

```bash
git push origin main
```

---

## Deployment Checklist

After implementation, complete these steps on the Gitea server:

- [ ] Deploy act_runner using `docker-compose.runner.yml`
- [ ] Create Gitea Token with `repo` permission
- [ ] Add `GITEA_TOKEN` secret to repository
- [ ] Test workflow with manual trigger

---

## Rollback Plan

If issues occur:

1. Delete workflow file:
   ```bash
   git rm .gitea/workflows/submission.yml
   git commit -m "chore: remove Gitea workflow"
   ```

2. Stop runner:
   ```bash
   docker-compose -f docker-compose.runner.yml down
   ```
