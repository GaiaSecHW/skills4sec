# 安全分析智能体技能设计技术规范 v0.1

## 1. 导言

本规范旨在定义一套标准化的架构，用于指导安全分析智能体的技能（Agent Skills）开发。通过建立统一的角色属性与安全领域映射，实现不同智能体在复杂任务中的语义化协同。

> **核心原则：** 所有的 Skill 定义应具备高精度的坐标系锚定。这将直接影响智能体群（Swarm）对该技能的调用权重与编排决策。

---

## 2. 规范设计来源与权威性说明

本规范的底层逻辑由全球公认的安全框架支撑，确保智能体在理解"安全"这一概念时与行业标准对齐。规范的核心思想是：**通过 ASVS/CWE 定义防御目标与威胁空间，通过 CAPEC 定义"攻击者的具体行为"，从而建立防攻转换的语义桥接**。

### 2.1 OWASP ASVS（应用安全验证标准）与 CWE（常见弱点列表）

**OWASP ASVS**（Application Security Verification Standard）和 **CWE**（Common Weakness Enumeration）是两个互补的安全框架，由 OWASP 基金会和 MITRE 公司分别维护，已被 NIST、ISC² 等权威机构认可。

#### 权威性与设计思路

- **ASVS - 防御者视角**：ASVS 从"应用应该具备什么能力"出发，定义了 **14 个安全功能域**与 **5 个验证等级**（从 L0 基础设施到 L4 高安全性应用），涵盖 300+ 详细验证要求。它本质上回答了：**"如果要完全阻止攻击 X，系统必须实现什么？"**

- **CWE - 攻击者视角**：CWE 列举了 **1000+ 种软件与硬件弱点**，从代码级缺陷（如 CWE-79 XSS）到架构级设计问题（如 CWE-434 文件上传验证不足），定义了导致漏洞的根本原因。

- **复合映射策略**：维度二采用**双轨制映射**，Skill 可选择：
  - **正向验证模式**：使用 ASVS 域（防御目标导向，适合验证型工具）
  - **攻击者视角模式**：使用 CWE 编号（弱点导向，适合发现型工具）

- **在本规范中的作用**：维度二告诉智能体"什么是安全的终态"（ASVS）或"什么样的代码缺陷会导致漏洞"（CWE），使智能体能够从防御或威胁的角度反向推导攻击空间。

详细要求见：https://github.com/OWASP/ASVS 和 https://cwe.mitre.org

### 2.2 MITRE CAPEC（常见攻击方式枚举与分类）

**MITRE CAPEC**（Common Attack Pattern Enumeration and Classification）是由美国国土安全部支持、MITRE 公司维护的攻击者行为百科全书，已被纳入 NIST 网络安全框架（CSF）的权威参考。

#### 权威性与设计思路

- **攻击者的"技能树"**：CAPEC 从攻击者的意图出发，定义了 **550+ 种攻击方式**，涵盖从侦察、探测、注入到利用的完整攻击链。每个攻击方式都包含：前提条件、执行步骤、必要资源、预期结果等结构化定义。

- **层次化的攻击语义**：CAPEC 采用**抽象程度递进模型**：高层攻击类定义概念级思路，中层攻击方式定义具体技术手段，低层实现定义工具层操作细节。

- **在本规范中的作用**：CAPEC 是**维度三（攻击方式）**的唯一权威来源。它定义了智能体"具体的破坏手段"。本规范严禁使用模糊的术语如"漏洞利用"、"入侵"，必须统一使用 CAPEC ID 与标准攻击方式名称（如 "CAPEC-66: SQL Injection"）。

详细分类见：https://capec.mitre.org

> 在ICSL内部使用时，将使用ICSL漏洞模式库/攻击模式库的分类来替换和扩展该维度分类。


---

## 3. 三维分类定义架构

### 维度一：功能角色（Functional Role）

定义 Skill 在智能体群协作链路中的工种属性：

- **知识提供者**（Knowledge Provider）：提供判断逻辑与漏洞机理，如攻击模式等，仅作为决策支撑。示例：Javaweb反序列化攻击模式。

- **执行者**（Executor）：负责实施具体的攻击及漏洞的端到端利用。示例：特定漏洞的挖掘工具、特定漏洞利用工具、内网渗透工具，以及通用工具如SQLMap、模糊测试引擎。

- **侦查员**（Navigator）：负责在代码或网络环境中寻找脆弱性线索，指明攻击方向。示例：codeql等静态代码扫描、漏洞扫描器、符号执行、威胁分析工具等。

- **调测器**（Debugger）：提供内存监控、协议拦截、单步调试等动态分析能力。示例：GDB、Frida、Charles 代理。

- **支撑者**（Supporter）：提供编译器、构建工具等基础设施，非安全目的的工具。示例：C++编译器、Maven、Docker。

### 维度二：防御目标与威胁空间（Verification Target & Attack Surface）

采用**复合映射模式**，指定该 Skill 的安全焦点，可选择以下两种之一：

- **ASVS 域**（防御者视角）：基于 OWASP ASVS 14 大安全功能域，指定防御目标。如：V2/V3 身份与会话、V4 访问控制、V5 输入验证、V6 输出编码、V7 错误处理、V8 数据保护、V9 通信安全、V10 代码安全、V11 业务逻辑、V12 文件上传、V13 API 安全、V14 配置安全。

- **CWE 编号**（攻击者视角）：基于 MITRE CWE 标准，指定代码级或设计级弱点。如：CWE-79 XSS、CWE-89 SQL 注入、CWE-434 文件上传验证不足、CWE-352 CSRF。

特殊情况下，某些通用工具（如 AFL、LibFuzzer）不需要指定固定的验证目标，因为它们可根据输入目标自适应地映射到不同的域或 CWE。同样，调测器与支撑者类 Skill 通常也不需要维度二的映射。




### 维度三：攻击方式（CAPEC Pattern）

基于 MITRE CAPEC 标准，指定该 Skill 实施的具体攻击方式，用 CAPEC 编号与名称标识。示例：`CAPEC-66: SQL Injection`、`CAPEC-94: MITM Attacks`。

> **灵活性说明**：并非所有 Skill 都需要完整的三维映射。知识提供者可能只有维度一二；调测器和支撑者可能只有维度一。通用工具（如 AFL）可不指定维度二三，根据输入目标动态适应。

---

## 4. 技能分类映射参考表

以下表格按功能角色排序，列举典型 Skill 与工具的标准化映射。不适用的维度标记为 n/a。
分类以工具的输入输出作为标准，例如某特定漏洞的端到端漏洞挖掘利用工具，基于fuzzing技术实现，应该分为Executor。

| 序号 | Skill/工具名称 | 维度一：功能角色 | 维度二：测试目标（ASVS/CWE） | 维度三：攻击方式（CAPEC） | 备注 |
|-----|---------------|-----------------|------------------|------------------------|------|
| **执行者 (Executor)** |  |  |  |  |  |
| 1 | LPEHunter | Executor | CWE-269 特权管理 | n/a | 漏洞利用端到端工具 |
| 2 | SqlMap | Executor | CWE-89 SQL 注入 | CAPEC-66 SQL Injection | 自动化 SQL 注入利用 |
| 3 | Burp Intruder | Executor | CWE-307 认证枚举 | CAPEC-114 Credential Enumeration | 暴力破解认证 |
| 4 | Ettercap | Executor | V9 通信安全 | CAPEC-94 MITM Attack | 中间人攻击 |
| 5 | Http DoS 开发库 | Executor | CWE-400 DoS | CAPEC-664 DoS | 服务拒绝攻击 |
| 6 | SOAPUI / ServiceFuzz | Executor | CWE-917 API 注入 | CAPEC-152 API Injection | API 注入测试 |
| 7 | AFL / LibFuzzer / Honggfuzz | Executor | n/a | CAPEC-28 Fuzzing | 通用模糊测试工具 |
| **侦查员 (Navigator)** |  |  |  |  |  |
| 8 | Findbugs / Semgrep | Navigator | CWE-20 输入验证 | n/a | 静态缺陷检测 |
| 9 | JAADAS (Android) | Navigator | CWE-94 代码注入 | n/a | Android 静态安全分析 |
| 10 | Openvas / GVM | Navigator | V14 配置安全 | CAPEC-312 Vulnerability Scanning | 网络/配置漏洞扫描 |
| 11 | Bandit (Python) | Navigator | CWE-95 代码执行 | n/a | Python 代码安全审计 |
| 12 | CheckMarx / SonarQube | Navigator | CWE-79 XSS | n/a | 静态应用安全测试（SAST） |
| 13 | Threat Analysis Tool | Navigator | V5 输入验证 | n/a | 通用威胁建模与攻击面分析 |
| **知识提供者 (Knowledge Provider)** |  |  |  |  |  |
| 14 | MyBatis 安全审计逻辑 | Knowledge Provider | CWE-89 SQL 注入 | n/a | 参数化查询验证模块 |
| 15 | Java 反序列化风险评估 | Knowledge Provider | CWE-502 反序列化 | n/a | 危险类黑名单判定 |
| 16 | TLS 证书链验证标准 | Knowledge Provider | V9 通信安全 | n/a | 证书有效性检查规则 |
| 17 | OWASP 加密算法基准 | Knowledge Provider | V8 数据保护 | n/a | 加密强度评定库 |
| **调测器 (Debugger)** |  |  |  |  |  |
| 18 | GDB / JDB | Debugger | n/a | n/a | 通用调试器 |
| 19 | IDA Pro | Debugger | n/a | n/a | 二进制反向工程 |
| 20 | Frida | Debugger | n/a | n/a | 运行时动态检测 |
| 21 | Charles Proxy | Debugger | n/a | n/a | HTTP/HTTPS 协议拦截 |
| 22 | SqliteDatabaseBrowser | Debugger | n/a | n/a | 本地数据库浏览 |
| **支撑者 (Supporter)** |  |  |  |  |  |
| 23 | GCC / Javac | Supporter | n/a | n/a | 源代码编译 |
| 24 | Maven / Gradle | Supporter | n/a | n/a | 项目构建管理 |
| 25 | Docker | Supporter | n/a | n/a | 容器化环境部署 |
| 26 | Git / SVN | Supporter | n/a | n/a | 版本控制 |

---

## 5. Skill 注册标准模板

所有开发者提交的 Skill 应该符合通用的 Skills Schema，以确保能够被智能体群调度系统解析。
请参考 https://github.com/anthropics/skills 的标准实现skill及对应的SKILL.md文件，以下是一个案例。
> 注意，尽管模板看起来复杂，经过测试，使用claude code等一键生成成功率很高，强烈建议基于大模型生成。


```markdown
# [技能名称：例如 SqlMap 自动化注入]

## 1. 技能概述 (Overview)
简要描述该技能的核心功能、解决的具体安全问题以及适用的场景。按照“原子化原则”，该技能应专注于单一维度的任务。

> **示例：** 本技能集成 SqlMap 核心引擎，专门用于对目标 URL 进行深度的 SQL 注入漏洞探测与自动化利用，支持多种数据库后端。

---

## 2. 坐标系锚定 (Skill Classification)
根据《安全分析智能体群技能设计与归类技术规范》，本技能的维度定义如下：

| 维度 | 标识值 | 说明 |
| :--- | :--- | :--- |
| **维度一：功能角色** | `Executor` / `Navigator` / `KnowledgeProvider` / `Debugger` / `Supporter` | 定义该技能在 Swarm 中的工种属性 |
| **维度二：安全对象** | `CWE-[NNN]` 或 `ASVS-V[X]` | 弱点导向（如 CWE-89）或防御验证导向（如 V5） |
| **维度三：攻击方式** | `CAPEC-[NNN]` | 基于 MITRE CAPEC 的具体攻击行为模式（如 CAPEC-66） |

*注：如为通用工具（如 AFL 模糊测试），维度二可填 `n/a`，维度三填 `CAPEC-28`。*

---

## 3. 工作原理 (How it Works)
描述技能的执行逻辑或调用链。
1. **初始化：** 检查环境（如 Python 环境、相关依赖库）。
2. **输入解析：** 接收智能体群传达的目标参数。
3. **执行过程：** 描述核心动作（如：启动扫描、生成 Payload、内存调试等）。
4. **结果收敛：** 将原始输出转换为规范化格式。

---

## 4. 输入与输出规格 (Specifications)

### 输入要求 (Inputs)
列出运行该技能所需的必要参数：
- `target_url`: (String) 目标地址
- `discovery_mode`: (Boolean) 是否仅探测不利用
- ...

### 输出结果 (Outputs)
除 `Supporter` 和 `Debugger` 外，所有涉及漏洞发现的输出必须符合 **SARIF 2.1.0** 标准。
- **格式：** `JSON (SARIF)`
- **核心字段：** `ruleId`, `level`, `locations`, `description`

---

## 5. 示例 (Examples)

### 场景示例：
> “当 Navigator 发现一个疑似含有参数化风险的链接时，Swarm 调度本技能进行验证。”

### 攻击模式对应示例：
- **Fuzzer 类：** 对应 `CAPEC-28 (Fuzzing)`。
- **逆向分析类：** 如使用 IDA Pro 逻辑，对应 `CAPEC-510 (Reverse Engineering)`。

---

## 6. 技能注册配置 (Skill JSON)
这是用于技能调度系统解析的元数据配置：

```json{
  "skill_id": "SKILL-{LANG/DOMAIN}-{TYPE}-{SEQ}",
  "name": "Human-readable Skill Name",
  "version": "1.0.0",
  "description": "简要描述该 Skill 的功能与适用场景",
  "classification": {
    "role": "Executor | Navigator | KnowledgeProvider | Debugger | Supporter",
    "target": ["ASVS-V{X} | CWE-{NNN}"],
    "pattern": ["CAPEC-{NNN}"],
    "cwe": ["CWE-{NNN}"]
  },
  "constraints": {
    "language": "java | python | c | binary | any",
    "framework": "spring-boot | mybatis | django | fastapi | any",
    "platform": "linux | windows | android | macos | any",
    "input_required": ["source_code_path | target_url | binary_path | ..."]
  },
  "dependencies": [
    {
      "skill_id": "SKILL-UTIL-JAVAC-001",
      "role": "Supporter",
      "required": true
    },
    {
      "skill_id": "SKILL-DBG-JDB-001",
      "role": "Debugger",
      "required": false
    }
  ],
  "procedure": {
    "step1": "描述第一步操作逻辑",
    "step2": "描述第二步操作逻辑",
    "step3": "描述第三步操作逻辑"
  },
  "output": {
    "format": "SARIF | JSON | Markdown | PlainText",
    "sarif_compatible": true
  },
  "metadata": {
    "author": "开发者姓名或团队",
    "created_date": "2026-03-01",
    "last_updated": "2026-03-03",
    "tags": ["java", "sql-injection", "mybatis", "static-analysis"],
    "references": ["https://capec.mitre.org/data/definitions/66.html", "https://cwe.mitre.org/data/definitions/89.html"]
  }
}
```


**字段说明**：

- `skill_id`：全局唯一标识，格式 `SKILL-{语言/领域}-{类型缩写}-{序号}`。示例：`SKILL-JAVA-EXEC-001`（Java 执行者型 Skill）、`SKILL-PY-NAV-003`（Python 导航员型 Skill）

- `classification.target`：使用 ASVS 域（如 `ASVS-V5`）或 CWE 编号（如 `CWE-89`），取决于 Skill 的设计视角。若为 Debugger/Supporter 或通用工具，可留空。

- `classification.pattern`：仅在有明确攻击方式时填写；通用工具（如 AFL）可填 `["CAPEC-28"]`

- `output.sarif_compatible`：除"支撑者"与"调测器"外，所有涉及安全发现的 Skill 输出必须标记为 `true`

---

## 6. 执行与互操作性要求

### 6.1 漏洞信息与 SARIF

除"支撑者"与"调测器"外，所有涉及漏洞发现的 Skill 输出的**漏洞信息**，须符合 **SARIF 2.1.0** 标准，确保结果的规范化与跨工具链兼容性；非漏洞信息以markdown格式，或者自定义的格式输出均可。

### 6.2 原子化原则

每一个 Skill 应**只解决一个特定维度的任务**。复杂的任务应通过多个 Skill 的协作实现。例：代码编译应由"支撑者"（GCC）独立执行，静态分析应由"导航员"（Semgrep）独立执行，两者通过依赖链编排。

### 6.3 动态权重与编排优先级

本规范定义的三个维度将直接影响智能体群（Swarm）对该技能的调用权重：维度二（验证目标）映射越精准，优先级越高；维度三（攻击方式）精度越高，优先级越高；Executor + Navigator 组合的协作分值高于单独的 Navigator 或纯分析。

---

## 7. 规范版本与维护

- **版本**：1.0.0 (2026-03-03)
- **维护方**：AI4SEC TMG & AI Infra工作组

---
