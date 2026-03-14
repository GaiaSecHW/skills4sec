# Skills4Sec — AI 技能市场

> 经过安全审计的 AI 技能目录，支持 Claude Code、Codex 等主流 AI 工具。

## 项目简介

Skills4Sec 是一个开源的 AI 技能（Skill）目录仓库，收录了适用于 [Claude Code](https://claude.ai/code) 和 [Codex](https://github.com/openai/codex) 的可复用技能包。每个技能都经过自动化安全审计，并附有风险等级标注，帮助开发者安全、快速地扩展 AI 工作流。

**在线浏览：** [https://cxm95.github.io/skills4sec](https://cxm95.github.io/skills4sec)

---

## 目录

- [特性](#特性)
- [项目设计](#项目设计)
- [仓库结构](#仓库结构)
- [快速使用](#快速使用)
- [本地开发](#本地开发)
- [添加新技能](#添加新技能)
- [安全审计机制](#安全审计机制)
- [静态站点架构](#静态站点架构)
- [License](#license)

---

## 特性

- **安全优先** — 每个技能附带 `skill-report.json` 安全报告，包含风险等级（safe / low / medium / high）
- **多平台支持** — 支持 Claude、Claude Code、Codex 三大平台
- **静态站点** — 纯静态 SPA，无需后端，可直接部署到 GitHub Pages
- **一键安装** — 技能详情页提供可复制的安装命令
- **实时搜索** — 按名称、分类、风险等级过滤，无需刷新页面

---

## 项目设计

### 总体架构

```
用户浏览器
    │
    ▼
docs/index.html          ← SPA Shell（导航、页脚、容器）
    ├── assets/style.css  ← CSS 设计系统（CSS Variables + 纯 CSS，无框架依赖）
    └── assets/app.js     ← 客户端 SPA（Hash 路由 + 渲染 + 事件）
                │
                ▼
         data/skills.json  ← 构建时生成的技能数据（由 build-site.js 读取 skill-report.json 汇总）
```

### SPA 路由

| URL Hash | 页面 | 说明 |
|---|---|---|
| `#` / 空 | 首页 | Hero 搜索、精选技能、Why 栏 |
| `#browse` | 浏览页 | 分类侧边栏 + 搜索 + 排序 |
| `#browse?q=xxx` | 浏览页（带搜索词） | 从首页搜索框跳转 |
| `#browse?cat=xxx` | 浏览页（带分类过滤） | 从首页分类 Pill 跳转 |
| `#skill/:slug` | 技能详情页 | 功能特性、使用场景、提示词模板 |

路由使用 `hashchange` 事件，所有带 `data-href` 属性的元素通过 `document` 级委托处理，**不依赖 `onclick`**，避免重复绑定与安全问题。

### 数据流

```
skills/
 └── <skill-name>/
       └── skill-report.json   (安全审计报告 + 内容元数据)
                │
                │  node scripts/build-site.js
                ▼
         docs/data/skills.json  (归一化后的技能列表)
                │
                │  fetch() in app.js (浏览器运行时)
                ▼
           页面渲染 (innerHTML 模板 + escHtml 转义)
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
│       ├── scripts/               # 可选：可执行脚本
│       ├── references/            # 可选：参考文档
│       └── assets/                # 可选：静态资源
│
├── docs/                          # 静态站点（部署到 GitHub Pages）
│   ├── index.html                 # SPA Shell
│   ├── assets/
│   │   ├── style.css              # CSS 设计系统
│   │   └── app.js                 # SPA 路由与渲染
│   ├── data/
│   │   └── skills.json            # 构建产物（由 build-site.js 生成）
│   └── .nojekyll                  # 禁用 GitHub Pages Jekyll 处理
│
├── scripts/
│   ├── build-site.js              # 构建脚本：skills/ → docs/data/skills.json
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
# 扫描 skills/ 下所有 skill-report.json，生成 docs/data/skills.json
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
1. 修改 skills/ 下的技能文件
        │
        ▼
2. npm run build:site    # 重新生成 skills.json
        │
        ▼
3. npm run serve         # 浏览器预览
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

### 提交流程

1. Fork 本仓库
2. 在 `skills/` 下创建新目录（目录名即 slug，使用小写字母、数字和连字符）
3. 添加 `SKILL.md` 和 `skill-report.json`
4. 运行 `npm run build:site` 验证数据能被正确解析
5. 提交 PR，描述技能用途和安全性

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
2. 运行 `node scripts/build-site.js` 生成 `docs/data/skills.json`
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

---

## License

本仓库目录结构及站点代码基于 [MIT License](LICENSE)。各技能可能有独立许可证，详见各技能目录下的 `license.txt` / `LICENSE.txt` 文件。
