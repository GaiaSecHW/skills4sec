# Skill Report Generator

手工生成 `skill-report.json` 的 Python 工具。

## 安装

```bash
pip install -r requirements.txt
```

## 配置

1. 复制配置文件模板：
```bash
cp config.yaml config.local.yaml
```

2. 编辑 `config.local.yaml`，设置 API 密钥：
```yaml
api:
  base_url: "https://api.openai.com/v1"  # 或其他兼容端点
  api_key: "sk-xxx"                       # 或使用环境变量 ${OPENAI_API_KEY}
  model: "gpt-4o"
```

也可以通过环境变量设置：
```bash
export OPENAI_API_KEY="sk-xxx"
```

## 使用

### 基本用法

```bash
# 处理单个 skill
python generate.py --input ../skills/0xbigboss/python-best-practices

# 处理多个 skills
python generate.py --input skill1 skill2 skill3

# 扫描目录（自动发现所有 SKILL.md）
python generate.py --input ../skills/0xbigboss --scan

# 指定输出目录
python generate.py --input skill1 --output ./reports

# 使用自定义配置
python generate.py --input skill1 --config ./config.local.yaml

# 覆盖 API 端点
python generate.py --input skill1 --base-url https://api.deepseek.com/v1

# 设置并发数
python generate.py --input ../skills/ --scan --concurrent 5

# 预览模式（不写入文件）
python generate.py --input skill1 --dry-run
```

### 命令行选项

| 选项 | 说明 |
|------|------|
| `--input, -i` | 输入路径（skill 目录或包含 skills 的目录）|
| `--scan` | 扫描目录自动发现 SKILL.md |
| `--output, -o` | 输出目录（默认原地覆盖）|
| `--config, -c` | 配置文件路径 |
| `--base-url` | 覆盖 API base URL |
| `--model` | 覆盖模型名称 |
| `--concurrent` | 并发数（默认 3）|
| `--dry-run` | 预览模式，不写入文件 |
| `--verbose, -v` | 详细输出 |
| `--help, -h` | 显示帮助 |

## 输出

生成的 `skill-report.json` 包含：

- `meta` - 元数据（时间戳、来源、hash 等）
- `skill` - 基本信息（名称、描述、标签等）
- `security_audit` - 安全审计结果
- `content` - AI 生成的内容（能力描述、使用场景、FAQ 等）
- `file_structure` - 文件结构

## 支持的 API

任何兼容 OpenAI 协议的 API：
- OpenAI (api.openai.com)
- DeepSeek (api.deepseek.com)
- 通义千问 (dashscope.aliyuncs.com/compatible-mode/v1)
- 本地 Ollama (localhost:11434/v1)
- 其他兼容服务
