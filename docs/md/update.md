## 🚀 最新技能：secskill-evo

**secskill-evo** 是一个基于 [Memento-S](https://github.com/cxm95/secskill-evo) 思路衍生的 Claude Code skill **演化框架**。

> 核心理念：skill 不是写完就结束的静态产物，而是可以基于执行反馈**自主反思、自动改进、版本化迭代**的活体。

### 双模式架构

| 模式 | 描述 |
|------|------|
| **创建模式** | 从零起草 skill → 编写测试用例 → 运行评估 → 迭代改进 → 打包交付 |
| **演化模式** | 执行失败时触发自动演化循环：LLM-as-Judge 评估 → 失败归因 → 改进 → 验证门控 → Git 版本化 |

### 核心能力

- **LLM-as-Judge** 双重评分：二元判定（对/错）+ 0-10 软评分 + 改进建议
- **Git 版本管理**：每次演化前后自动快照，退步时安全回滚
- **经验累积**：将失败模式和设计决策写入 TIP.md，持续积累 skill 知识

### 快速开始

```bash
gh skill install secskill-evo
```

---

👉 查看 [完整介绍文章](/blog/secskill-evo-intro) 了解详细设计原则与使用方式。
