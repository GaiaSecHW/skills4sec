# Skills4Sec — AI 技能市场

> 经过安全审计的 AI 技能、运行环境与智能体目录，支持 Claude Code、Codex 等主流 AI 工具。

## 项目简介

Skills4Sec 是一个开源目录仓库，收录三类核心实体：

- **技能（Skill）** — 适用于 [Claude Code](https://claude.ai/code) 和 [Codex](https://github.com/openai/codex) 的可复用技能包，每个技能都经过自动化安全审计
- **运行环境（Harness）** — Agent 执行技能时所依赖的目标环境（Docker 镜像或 SSH 环境），描述 Agent 可以操作的系统上下文
- **智能体（Agent）** — 开箱即用的 AI 智能体，内置系统提示词（AGENT.md）与工具配置（MCP），可直接用于特定领域的自动化任务

三者关系：Skill 定义 Agent 能做什么，Harness 定义 Agent 在哪里做，Agent 则将二者整合为可直接运行的完整工作流。

**在线浏览：** [https://cxm95.github.io/skills4sec](https://cxm95.github.io/skills4sec)

---

## 目录

- [特性](#特性)
- [项目设计](#项目设计)
- [仓库结构](#仓库结构)
- [快速使用](#快速使用)
- [本地开发](#本地开发)
- [添加新技能](#添加新技能)
- [添加新环境](#添加新环境)
- [添加新智能体](#添加新智能体)
- [安全审计机制](#安全审计机制)
- [静态站点架构](#静态站点架构)
- [License](#license)

---

## 特性

- **安全优先** — 每个技能附带 `skill-report.json` 安全报告，包含风险等级（safe / low / medium / high）
- **Harness 支持** — 维护 Agent 运行环境目录，支持 Docker 镜像（image）和 SSH 两类环境
- **智能体目录** — 收录开箱即用的 AI 智能体，内置 AGENT.md 系统提示词与 MCP 工具配置
- **多平台支持** — 支持 Claude、Claude Code、Codex 三大平台
- **静态站点** — 纯静态 SPA，无需后端，可直接部署到 GitHub Pages
- **一键安装** — 技能详情页提供可复制的安装命令
- **实时搜索** — 按名称、分类、风险等级过滤，无需刷新页面
- **技能提交** — 内置提交引导页（`#submit`），一键生成 GitHub Issue
- **版本变更对比** — 技能详情页展示版本间 diff，双栏 side-by-side 对比，支持多版本切换
- **技能自进化** — 展示 Memento-S 技能自进化系统的工作原理（SVG 流程图）、运行状态统计和实时滚动日志

---

## 项目设计

### 总体架构

```
用户浏览器
    │
    ▼
docs/index.html           ← SPA Shell（导航、页脚、容器）
    ├── assets/style.css   ← CSS 设计系统（CSS Variables + 纯 CSS，无框架依赖）
    └── assets/app.js      ← 客户端 SPA（Hash 路由 + 渲染 + 事件）
                │
                ├── data/skills.json    ← 构建时生成（skill-report.json 汇总）
                └── data/harnesses.json ← 构建时生成（harness-report.json 汇总）
```

### SPA 路由

| URL Hash | 页面 | 说明 |
|---|---|---|
| `#` / 空 | 首页 | Hero 搜索、精选技能、精选环境、精选智能体、Why 栏 |
| `#browse` | 技能浏览页 | 分类侧边栏 + 搜索 + 排序 |
| `#browse?q=xxx` | 技能浏览页（带搜索词） | 从首页搜索框跳转 |
| `#browse?cat=xxx` | 技能浏览页（带分类过滤） | 从首页分类 Pill 跳转 |
| `#skill/:slug` | 技能详情页 | 功能特性、使用场景、提示词模板、版本变更对比 |
| `#harnesses` | 环境浏览页 | 按环境类型过滤（image / ssh） |
| `#harness/:slug` | 环境详情页 | 能力列表、使用场景、连接信息 |
| `#agents` | 智能体浏览页 | 按技能类型过滤（github / npx）+ 搜索 |
| `#agent/:slug` | 智能体详情页 | 系统提示词（AGENT.md）、MCP 配置、安装命令 |
| `#submit` | 技能提交页 | 三步引导 + 表单生成 GitHub Issue |
| `#evolution` | 技能自进化页 | Memento-S 原理图、统计面板、实时日志 |

路由使用 `hashchange` 事件，所有带 `data-href` 属性的元素通过 `document` 级委托处理，**不依赖 `onclick`**，避免重复绑定与安全问题。

### 数据流

```
skills/            harnesses/             agents/
 └── <name>/        └── <name>/            └── <name>/
       ├── skill-report.json  └── harness-report.json  ├── AGENT.md
       └── .diff/*.diff             │                └── config.json
                │                     │
                └─────────────────────┴──────────────────────┘
                                      │  node scripts/build-site.js
                                      ▼
                         docs/data/skills.json
                         docs/data/harnesses.json
                         docs/data/agents.json
                         docs/data/diffs/<slug>/*.diff   ← diff 文件复制到此
                         docs/data/evol/summary.json     ← 自进化统计（手动维护）
                         docs/data/evol/logs.json        ← 自进化日志（手动维护）
                                      │
                                      │  fetch() in app.js (浏览器运行时)
                                      ▼
                           页面渲染 (innerHTML 模板 + escHtml 转义)
                           技能详情页：diff2html 渲染版本变更对比
```

### CSS 设计系统

- 使用 CSS Custom Properties（变量）统一管理色彩、圆角、阴影等 Token
- 无任何第三方 CSS 框架依赖（无 Tailwind、无 Bootstrap）
- 响应式断点：640 px（移动/桌面分界）、1024 px（侧边栏显示）

---

## 仓库结构

```
skills4sec/
├── skills/                        # 技能目录（每个子目录为一个技能）
│   └── <skill-name>/
│       ├── SKILL.md               # 技能定义文件（AI 工具加载）
│       ├── skill-report.json      # 安全审计报告 + 内容元数据
│       ├── .diff/                 # 可选：版本变更 diff 文件
│       │   └── 001-v1.0-v1.1.diff # 命名规范：{序号}-{from}-{to}.diff
│       ├── scripts/               # 可选：可执行脚本
│       ├── references/            # 可选：参考文档
│       └── assets/                # 可选：静态资源
│
├── harnesses/                     # 运行环境目录（每个子目录为一个 Harness）
│   └── <harness-name>/
│       └── harness-report.json    # 环境元数据（无安全审计）
│
├── agents/                        # 智能体目录（每个子目录为一个 Agent）
│   └── <agent-name>/
│       ├── AGENT.md               # 系统提示词（AI 工具直接加载）
│       └── config.json            # 元数据 + skill 配置 + MCP 配置
│
├── docs/                          # 静态站点（部署到 GitHub Pages）
│   ├── index.html                 # SPA Shell
│   ├── assets/
│   │   ├── style.css              # CSS 设计系统
│   │   └── app.js                 # SPA 路由与渲染
│   ├── data/
│   │   ├── skills.json            # 构建产物（由 build-site.js 生成）
│   │   ├── harnesses.json         # 构建产物（由 build-site.js 生成）
│   │   ├── agents.json            # 构建产物（由 build-site.js 生成）
│   │   ├── diffs/                 # 构建产物：diff 文件（由 build-site.js 复制）
│   │   │   └── <skill-slug>/      # 按 slug 分目录存放
│   │   └── evol/                  # 技能自进化数据（手动维护）
│   │       ├── summary.json       # 统计摘要（进化轮数、成功率等）
│   │       └── logs.json          # 调用/优化日志（按时间倒序）
│   └── .nojekyll                  # 禁用 GitHub Pages Jekyll 处理
│
├── scripts/
│   ├── build-site.js              # 构建脚本：skills/ + harnesses/ + agents/ → docs/data/
│   └── serve.py                   # 本地预览服务器
│
├── schemas/                       # JSON Schema 校验规则
├── pending/                       # 待审核技能
├── .github/workflows/
│   └── deploy-site.yml            # GitHub Actions：构建 + 部署到 Pages
└── package.json
```

---

## 快速使用

### 安装技能到 Claude Code

**方式一：快速安装（推荐）**

在 Claude Code 中输入以下提示词：

```
Download all files from https://github.com/cxm95/skills4sec/tree/main/skills/<skill-name>
and save to ~/.claude/skills/
```

**方式二：手动安装**

```bash
# 克隆仓库
git clone https://github.com/cxm95/skills4sec.git

# 复制技能到 Claude Code 用户目录
cp -r skills4sec/skills/<skill-name> ~/.claude/skills/
```

技能作用域：

| 作用域 | 路径 | 说明 |
|---|---|---|
| 项目级 | `.claude/skills/<skill-name>/` | 仅当前项目生效 |
| 用户级 | `~/.claude/skills/<skill-name>/` | 所有项目生效 |

### 安装技能到 Codex

```bash
# 使用 skill-installer 技能（推荐）
# 在 Codex 中运行：
Install the skill-installer skill from github.com/cxm95/skills4sec

# 之后即可通过 skill-installer 安装其他技能：
Install the <skill-name> skill from github.com/cxm95/skills4sec
```

**手动安装：**

```bash
cp -r skills4sec/skills/<skill-name> ~/.codex/skills/
# 重启 Codex 以加载新技能
```

---

## 本地开发

### 前置条件

- Node.js 18+
- Python 3（用于本地预览服务器）

### 安装依赖

```bash
npm install
```

### 构建站点数据

```bash
# 扫描 skills/、harnesses/ 和 agents/，生成 docs/data/ 下的三个 JSON 文件
npm run build:site
```

### 本地预览

```bash
# 启动本地服务器（默认端口 8080）
npm run serve

# 指定端口
python3 scripts/serve.py 3000
```

打开 [http://localhost:8080](http://localhost:8080) 即可预览。

### 开发流程

```
1. 修改 skills/、harnesses/ 或 agents/ 下的文件
        │
        ▼
2. npm run build:site    # 重新生成 skills.json、harnesses.json 和 agents.json
        │
        ▼
3. npm run serve         # 浏览器预览（http://localhost:8080）
        │
        ▼
4. git add & commit & push
        │
        ▼
5. GitHub Actions 自动部署到 Pages
```

---

## 添加新技能

### 技能目录规范

每个技能必须包含：

```
skills/<skill-name>/
├── SKILL.md             # 技能定义（必须）
└── skill-report.json    # 安全审计报告（必须）
```

`skill-report.json` 遵循 `schema_version: "2.0"` 格式，核心字段：

```json
{
  "schema_version": "2.0",
  "meta": {
    "slug": "my-skill",
    "source_url": "https://github.com/...",
    "source_type": "official"
  },
  "skill": {
    "name": "my-skill",
    "description": "触发描述（AI 工具据此判断何时激活技能）",
    "icon": "🛠️",
    "version": "1.0.0",
    "author": "your-name",
    "category": "productivity",
    "tags": ["tag1", "tag2"],
    "supported_tools": ["claude", "codex", "claude-code"]
  },
  "security_audit": {
    "risk_level": "safe",
    "is_blocked": false,
    "safe_to_publish": true,
    "summary": "安全审计摘要"
  },
  "content": {
    "value_statement": "这个技能解决什么问题",
    "actual_capabilities": ["能力1", "能力2"],
    "use_cases": [
      {
        "target_user": "目标用户",
        "title": "使用场景标题",
        "description": "描述"
      }
    ],
    "prompt_templates": [
      {
        "title": "模板标题",
        "scenario": "适用场景",
        "prompt": "提示词内容"
      }
    ]
  }
}
```

### 添加版本变更对比（可选）

在技能目录下创建 `.diff/` 子文件夹，放入 unified diff 文件，构建后自动在详情页展示双栏对比：

```
skills/<skill-name>/.diff/
├── 001-v1.0-v1.1.diff
├── 002-v1.1-v1.2.diff
└── 003-v1.2-v1.3.diff    ← 序号最大的默认展示
```

**命名规范：** `{三位序号}-{from版本}-{to版本}.diff`，例如 `001-v1.0-v1.1.diff`。构建时按文件名字典序排序，序号最大的为最新版本，默认展示。

生成 diff 文件的方法：
```bash
git diff v1.0 v1.1 -- skills/<skill-name>/ > skills/<skill-name>/.diff/001-v1.0-v1.1.diff
```

### 提交流程

也可通过网站内置的[技能提交页面](https://cxm95.github.io/skills4sec/#submit)，填写表单后一键生成 GitHub Issue。

或手动提交：

1. Fork 本仓库
2. 在 `skills/` 下创建新目录（目录名即 slug，使用小写字母、数字和连字符）
3. 添加 `SKILL.md` 和 `skill-report.json`
4. （可选）在 `.diff/` 下添加版本变更 diff 文件
5. 运行 `npm run build:site` 验证数据能被正确解析
6. 提交 PR，描述技能用途和安全性

---

## 添加新环境

### 环境目录规范

每个 Harness 只需一个文件：

```
harnesses/<harness-name>/
└── harness-report.json    # 环境元数据（必须）
```

目录名即 slug，使用小写字母、数字和连字符。

### harness-report.json 格式

当前支持两种环境类型：

**镜像类型（image）：**

```json
{
  "schema_version": "1.0",
  "meta": {
    "slug": "my-ubuntu-env",
    "source_url": "https://github.com/..."
  },
  "harness": {
    "name": "My Ubuntu 环境",
    "description": "基于 Ubuntu 22.04 的分析环境",
    "icon": "🐧",
    "version": "1.0.0",
    "author": "your-name",
    "env_type": "image",
    "base_image": "ubuntu:22.04",
    "supported_tools": ["claude-code", "codex"],
    "tags": ["ubuntu", "linux"]
  },
  "content": {
    "value_statement": "为 Agent 提供标准化的 Linux 运行上下文",
    "capabilities": ["执行 shell 命令", "访问文件系统"],
    "use_cases": [
      {
        "title": "自动化分析",
        "description": "在受控环境中运行分析脚本"
      }
    ]
  }
}
```

**SSH 类型（ssh）：**

```json
{
  "schema_version": "1.0",
  "meta": {
    "slug": "my-ssh-env",
    "source_url": "https://github.com/..."
  },
  "harness": {
    "name": "My SSH 实验环境",
    "description": "可远程 SSH 连接的实验环境",
    "icon": "🔐",
    "version": "1.0.0",
    "author": "your-name",
    "env_type": "ssh",
    "ssh_host": "lab.example.com",
    "ssh_user": "agent",
    "supported_tools": ["claude-code"],
    "tags": ["ssh", "remote"]
  },
  "content": {
    "value_statement": "通过 SSH 让 Agent 操作远程环境",
    "capabilities": ["执行远程命令", "访问内网资源"],
    "use_cases": []
  }
}
```

> **注意：** Harness 不包含 `security_audit` 块，由提交者和维护者共同评估环境安全性。

### 提交流程

1. Fork 本仓库
2. 在 `harnesses/` 下创建新目录
3. 添加 `harness-report.json`
4. 运行 `npm run build:site` 验证解析
5. 提交 PR

---

## 添加新智能体

### 智能体目录规范

每个 Agent 包含两个文件：

```
agents/<agent-name>/
├── AGENT.md        # 系统提示词，AI 工具直接加载（必须）
└── config.json     # 元数据 + skill 配置 + MCP 配置（必须）
```

目录名即 slug，使用小写字母、数字和连字符。

### config.json 格式

```json
{
  "name": "我的安全智能体",
  "slug": "my-security-agent",
  "icon": "🤖",
  "description": "一句话描述智能体的用途",
  "author": "your-name",
  "version": "1.0.0",
  "tags": ["security", "recon"],
  "skill": {
    "type": "github",
    "source": "cxm95/skills4sec"
  },
  "mcp": [
    {
      "name": "filesystem",
      "type": "npx",
      "package": "@modelcontextprotocol/server-filesystem",
      "args": ["/tmp/workspace"]
    }
  ]
}
```

`skill.type` 支持两种值：
- `"github"` — 通过 `gh skill install <source>` 安装
- `"npx"` — 通过 `npx <package>` 运行

### AGENT.md 格式

AGENT.md 是该智能体的系统提示词，建议包含：

- 角色定位（这个 Agent 是谁、做什么）
- 行为准则（安全红线、授权要求）
- 工作流程（标准操作步骤）
- 输出格式（报告模板、结构要求）

### 提交流程

1. Fork 本仓库
2. 在 `agents/` 下创建新目录（目录名即 slug）
3. 添加 `AGENT.md` 和 `config.json`
4. 运行 `npm run build:site` 验证 Agent 被正确解析
5. 提交 PR，说明智能体的用途和使用场景

---

## 安全审计机制

每个技能的 `skill-report.json` 包含 `security_audit` 块，记录：

| 字段 | 说明 |
|---|---|
| `risk_level` | 风险等级：`safe` / `low` / `medium` / `high` |
| `is_blocked` | 是否因安全问题被屏蔽 |
| `safe_to_publish` | 是否可以公开发布 |
| `critical_findings` | 严重发现列表 |
| `dangerous_patterns` | 危险代码模式 |
| `risk_factor_evidence` | 风险因子证据（文件 + 行号） |

风险等级说明：

- **safe** — 纯文档或无副作用代码，零攻击面
- **low** — 有网络/文件/外部命令操作，但均受控且合理
- **medium** — 有潜在风险操作，建议仔细审阅
- **high** — 存在明显风险，不建议直接使用

---

## 静态站点架构

### GitHub Pages 部署

推送到 `main`/`master` 分支后，`.github/workflows/deploy-site.yml` 自动：

1. 安装 Node.js 依赖
2. 运行 `node scripts/build-site.js` 生成 `docs/data/skills.json`、`docs/data/harnesses.json` 和 `docs/data/agents.json`
3. 将 `docs/` 目录发布到 GitHub Pages

**启用 GitHub Pages：**
仓库 Settings → Pages → Source 选择 `Deploy from a branch` → 分支 `main` → 目录 `/docs`

### 关键设计决策

| 决策 | 原因 |
|---|---|
| 纯静态 SPA（无构建框架） | 零运行时依赖，加载快，维护简单 |
| Hash 路由（`#`） | 无需服务器端路由配置，兼容 GitHub Pages 静态托管 |
| `document` 级委托点击 | 避免动态 innerHTML 后重复注册监听器；统一处理导航、卡片、面包屑 |
| `data-href` 而非 `onclick` | 内容与行为分离，避免 XSS 风险，支持键盘导航 |
| `escHtml()` 包含单引号转义 | 防止 HTML 注入，即使技能名包含特殊字符也安全 |
| `docs/index.html` 静态维护 | 构建脚本只生成数据文件，避免每次构建覆盖已修复的 Shell |
| diff 文件复制到 `docs/data/diffs/` | 静态站点只能 fetch 同源文件，skills/ 不在 docs/ 下，构建时统一复制 |
| diff2html CDN 引入 | 专为 git diff 设计，双栏渲染开箱即用，无需打包工具 |

---

## 技能自进化（Memento-S）

`#evolution` 页面展示基于 Memento-S 框架的技能自进化系统，包含三个核心模块：

### 原理图

SVG 流程图呈现 Memento-S 闭环的三个阶段：

1. **Execution Phase** — Task Executor 执行任务，Answer Judge 判定结果；正确则记录成功，失败则进入归因
2. **Attribution Phase** — Failure Attribution 分析失败根因，Utility Tracker 评估技能效用，决定 OPTIMIZE（优化已有技能）或 DISCOVER（发现新技能）
3. **Evolution Phase** — LLM Skill Rewriter 重写技能代码，Unit Test Gate 运行回归+生成测试；通过则重试任务，失败则回滚

### 统计面板

4 个指标卡片，数据来自 `docs/data/evol/summary.json`：

| 字段 | 说明 |
|---|---|
| `total_rounds` | 进化轮数 |
| `evolved_skills` | 发生进化的技能数 |
| `original_accuracy` / `improved_accuracy` | 成功率提升（原始 → 改进） |
| `running_instances` | 当前运行中的优化实例数 |

### 实时日志

自动滚动的日志列表，数据来自 `docs/data/evol/logs.json`，每条记录包含：

| 字段 | 说明 |
|---|---|
| `ts` | ISO 8601 时间戳 |
| `type` | `optimize`（优化）或 `invoke`（调用） |
| `skill` | 技能名称 |
| `agent` | 智能体名称 |
| `harness` | 运行环境名称 |
| `detail` | 操作描述 |
| `result` | `pass` / `success` / `fail` |

日志使用 CSS animation 实现无缝自滚动，鼠标悬停时暂停。

---

## License

本仓库目录结构及站点代码基于 [MIT License](LICENSE)。各技能可能有独立许可证，详见各技能目录下的 `license.txt` / `LICENSE.txt` 文件。
