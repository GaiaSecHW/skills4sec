#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Skill Report Generator - 手工生成 skill-report.json

Usage:
    python generate.py --input ../skills/0xbigboss/python-best-practices
    python generate.py --input ../skills/0xbigboss --scan
    python generate.py --input skill1 skill2 --output ./reports
"""

import argparse
import hashlib
import json
import os
import re
import sys

# 修复 Windows 控制台编码问题
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import yaml
from openai import OpenAI
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.table import Table

console = Console()

# ============================================================================
# 配置管理
# ============================================================================

DEFAULT_CONFIG = {
    "api": {
        "base_url": "https://api.openai.com/v1",
        "api_key": "${OPENAI_API_KEY}",
        "model": "gpt-4o",
        "timeout": 120
    },
    "generation": {
        "concurrent": 3,
        "retry": 2
    },
    "security_rules": {
        "scripts": {
            "extensions": [".sh", ".py", ".js", ".ts", ".mjs", ".ps1", ".bat"],
            "patterns": ["#!/bin/", "#!/usr/bin/env"]
        },
        "network": {
            "patterns": ["http://", "https://", "fetch(", "aiohttp", "requests.", "axios", "websocket", "urllib", "httpx", "curl"]
        },
        "filesystem": {
            "patterns": ["open(", ".write(", "Path(", "os.remove", "os.mkdir", "os.makedirs", "shutil.", "os.path", "fs.readFile", "fs.writeFile"]
        },
        "env_access": {
            "patterns": ["os.environ", "process.env", "dotenv", "load_dotenv", "getenv", "env["]
        },
        "external_commands": {
            "patterns": ["subprocess", "exec(", "eval(", "child_process", "os.system", "os.popen", "commands."]
        }
    },
    "dangerous_patterns": [
        {"pattern": r"eval\s*\(", "description": "Dynamic code execution"},
        {"pattern": r"exec\s*\(", "description": "Dynamic code execution"},
        {"pattern": r'subprocess.*shell=True', "description": "Shell injection risk"},
        {"pattern": r'os.system\s*\(', "description": "System command execution"},
        {"pattern": r'__import__\s*\(', "description": "Dynamic import"},
    ]
}


def load_config(config_path: Optional[str] = None) -> dict:
    """加载配置文件"""
    config = DEFAULT_CONFIG.copy()

    if config_path and Path(config_path).exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            user_config = yaml.safe_load(f)
            if user_config:
                config = deep_merge(config, user_config)

    return config


def deep_merge(base: dict, override: dict) -> dict:
    """深度合并字典"""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


# ============================================================================
# Skill 发现和解析
# ============================================================================

def discover_skills(input_paths: list[str], scan: bool) -> list[Path]:
    """发现所有 skill 目录"""
    skills = []

    for path_str in input_paths:
        path = Path(path_str)
        if not path.exists():
            console.print(f"[yellow]路径不存在: {path}")
            continue

        if path.is_file() and path.name == "SKILL.md":
            skills.append(path.parent)
        elif path.is_file() and path.suffix.lower() == ".md":
            content = path.read_text(encoding='utf-8')
            if content.strip().startswith('---'):
                skills.append(path.parent)
        elif scan and path.is_dir():
            for skill_md in path.rglob("SKILL.md"):
                if "node_modules" not in str(skill_md) and ".git" not in str(skill_md):
                    skills.append(skill_md.parent)
        elif path.is_dir() and (path / "SKILL.md").exists():
            skills.append(path)

    return list(set(skills))


def parse_skill_md(skill_dir: Path) -> dict:
    """解析 SKILL.md 文件"""
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        raise FileNotFoundError(f"SKILL.md not found in {skill_dir}")

    content = skill_md.read_text(encoding='utf-8')
    metadata = {}

    if content.strip().startswith('---'):
        parts = content.split('---', 2)
        if len(parts) >= 2:
            frontmatter = parts[1].strip()
            for line in frontmatter.split('\n'):
                if ':' in line:
                    key, value = line.split(':', 1)
                    metadata[key.strip()] = value.strip()
            content = '---'.join(parts[2:]) if len(parts) > 2 else ''

    return {
        "name": metadata.get("name", skill_dir.name),
        "description": metadata.get("description", ""),
        "icon": metadata.get("icon", "📦"),
        "version": metadata.get("version", "1.0.0"),
        "author": metadata.get("author", "unknown"),
        "license": metadata.get("license", "MIT"),
        "category": metadata.get("category", "coding"),
        "tags": metadata.get("tags", "").split(",") if metadata.get("tags") else [],
        "supported_tools": metadata.get("supported_tools", "claude, codex, claude-code").split(", ") if metadata.get("supported_tools") else ["claude", "codex", "claude-code"],
        "content": content,
    }


def scan_file_structure(skill_dir: Path) -> list[dict]:
    """扫描文件结构"""
    def scan_dir(base_path: Path, prefix: str = "") -> list[dict]:
        result = []
        try:
            items = sorted(base_path.iterdir(), key=lambda x: x.name.lower())
        except PermissionError:
            return result

        for item in items:
            if item.name.startswith('.') or item.name == '__pycache__':
                continue

            relative_path = f"{prefix}/{item.name}" if prefix else item.name

            if item.is_file():
                try:
                    lines = len(item.read_text(encoding='utf-8').splitlines())
                except:
                    lines = 0
                result.append({
                    "name": item.name,
                    "type": "file",
                    "path": relative_path,
                    "lines": lines
                })
            else:
                children = scan_dir(item, relative_path)
                if children:
                    result.append({
                        "name": item.name,
                        "type": "dir",
                        "path": relative_path,
                        "children": children
                    })
        return result

    return scan_dir(skill_dir)


# ============================================================================
# 安全审计
# ============================================================================

def analyze_security(skill_dir: Path, config: dict) -> dict:
    """安全审计 - 规则匹配"""
    risk_factors = []
    risk_factor_evidence = []
    critical_findings = []
    high_findings = []
    medium_findings = []
    low_findings = []

    rules = config.get("security_rules", {})

    for file_path in skill_dir.rglob("*"):
        if not file_path.is_file():
            continue
        if file_path.name.startswith('.') or file_path.name == 'skill-report.json':
            continue

        try:
            content = file_path.read_text(encoding='utf-8')
            lines = content.splitlines()
        except:
            continue

        relative_file = str(file_path.relative_to(skill_dir))
        file_ext = file_path.suffix.lower()

        # 检查脚本文件
        if file_ext in rules.get("scripts", {}).get("extensions", []):
            if "scripts" not in risk_factors:
                risk_factors.append("scripts")
            risk_factor_evidence.append({
                "factor": "scripts",
                "evidence": [{"file": relative_file, "line_start": 1, "line_end": len(lines)}]
            })

        # 检查各种风险模式
        for line_num, line in enumerate(lines, 1):
            # 网络模式
            for pattern in rules.get("network", {}).get("patterns", []):
                if pattern in line:
                    if "network" not in risk_factors:
                        risk_factors.append("network")
                    risk_factor_evidence.append({
                        "factor": "network",
                        "evidence": [{"file": relative_file, "line_start": line_num, "line_end": line_num}]
                    })

            # 文件系统模式
            for pattern in rules.get("filesystem", {}).get("patterns", []):
                if pattern in line:
                    if "filesystem" not in risk_factors:
                        risk_factors.append("filesystem")
                    risk_factor_evidence.append({
                        "factor": "filesystem",
                        "evidence": [{"file": relative_file, "line_start": line_num, "line_end": line_num}]
                    })

            # 环境变量访问
            for pattern in rules.get("env_access", {}).get("patterns", []):
                if pattern in line:
                    if "env_access" not in risk_factors:
                        risk_factors.append("env_access")
                    risk_factor_evidence.append({
                        "factor": "env_access",
                        "evidence": [{"file": relative_file, "line_start": line_num, "line_end": line_num}]
                    })

            # 外部命令
            for pattern in rules.get("external_commands", {}).get("patterns", []):
                if pattern in line:
                    if "external_commands" not in risk_factors:
                        risk_factors.append("external_commands")
                    risk_factor_evidence.append({
                        "factor": "external_commands",
                        "evidence": [{"file": relative_file, "line_start": line_num, "line_end": line_num}]
                    })

            # 危险模式
            for dp in config.get("dangerous_patterns", []):
                if re.search(dp["pattern"], line):
                    finding = {
                        "title": dp["description"],
                        "description": f"Found pattern: {dp['pattern']}",
                        "locations": [{"file": relative_file, "line_start": line_num, "line_end": line_num}]
                    }
                    if "exec" in line.lower() or "eval" in line.lower():
                        high_findings.append(finding)
                    else:
                        medium_findings.append(finding)

    # 计算风险等级
    risk_level = "safe"
    if len(critical_findings) > 0:
        risk_level = "critical"
    elif len(high_findings) > 0:
        risk_level = "high"
    elif len(medium_findings) > 0 or len(risk_factors) >= 3:
        risk_level = "medium"
    elif len(risk_factors) > 0:
        risk_level = "low"

    # 统计文件数和行数
    files_scanned = 0
    total_lines = 0
    for f in skill_dir.rglob("*"):
        if f.is_file() and not f.name.startswith('.'):
            files_scanned += 1
            try:
                total_lines += len(f.read_text(encoding='utf-8').splitlines())
            except:
                pass

    return {
        "risk_level": risk_level,
        "is_blocked": risk_level == "critical",
        "safe_to_publish": risk_level not in ["critical", "high"],
        "summary": generate_security_summary(risk_level, risk_factors, high_findings, medium_findings),
        "risk_factors": risk_factors,
        "risk_factor_evidence": risk_factor_evidence,
        "critical_findings": critical_findings,
        "high_findings": high_findings,
        "medium_findings": medium_findings,
        "low_findings": low_findings,
        "dangerous_patterns": [],
        "files_scanned": files_scanned,
        "total_lines": total_lines,
    }


def generate_security_summary(risk_level: str, risk_factors: list, high_findings: list, medium_findings: list) -> str:
    """生成安全审计摘要"""
    if risk_level == "safe":
        return "This skill contains only documentation and educational content. No executable code, network access, or file system operations detected."
    elif risk_level == "low":
        return f"This skill has low-risk features: {', '.join(risk_factors)}. No dangerous patterns detected."
    elif risk_level == "medium":
        findings = []
        if high_findings:
            findings.append(f"{len(high_findings)} high-severity pattern(s)")
        if medium_findings:
            findings.append(f"{len(medium_findings)} medium-severity pattern(s)")
        return f"This skill contains potentially sensitive patterns: {', '.join(findings)}. Review recommended before use."
    elif risk_level == "high":
        return "This skill contains high-risk patterns that could execute arbitrary code or commands. Careful review required before use."
    else:
        return "This skill contains critical security risks and Not recommended for use without thorough audit."


# ============================================================================
# AI 内容生成
# ============================================================================

def generate_content_with_ai(skill_data: dict, file_structure: list, config: dict, verbose: bool = False) -> dict:
    """使用 AI 生成内容"""
    api_config = config.get("api", {})
    base_url = api_config.get("base_url", "https://api.openai.com/v1")
    api_key = api_config.get("api_key", "")
    model = api_config.get("model", "gpt-4o")
    timeout = api_config.get("timeout", 120)

    # 处理环境变量
    if api_key.startswith("${") and api_key.endswith("}"):
        env_var = api_key[2:-1]
        api_key = os.environ.get(env_var, "")

    if not api_key:
        raise ValueError("API key not configured. Set OPENAI_API_KEY environment variable or configure in config.yaml")

    client = OpenAI(base_url=base_url, api_key=api_key, timeout=timeout)

    # 读取主要文件内容
    file_contents = {}
    skill_dir = Path(skill_data.get("skill_dir", "."))

    # 读取 SKILL.md
    skill_md = skill_dir / "SKILL.md"
    if skill_md.exists():
        content = skill_md.read_text(encoding='utf-8')
        file_contents["SKILL.md"] = content[:5000] + ("..." if len(content) > 5000 else "")

    # 读取其他重要文件
    for ref_dir in ["references", "assets", "scripts"]:
        ref_path = skill_dir / ref_dir
        if ref_path.exists() and ref_path.is_dir():
            for f in list(ref_path.glob("*.md"))[:3]:
                try:
                    content = f.read_text(encoding='utf-8')
                    file_contents[f"{ref_dir}/{f.name}"] = content[:2000] + ("..." if len(content) > 2000 else "")
                except:
                    pass

    # 构建 prompt
    prompt = f"""你是一个技术文档专家。请根据以下 skill 信息生成一份结构化的报告内容。

Skill 名称: {skill_data.get('name', 'Unknown')}
描述: {skill_data.get('description', 'No description')}
作者: {skill_data.get('author', 'Unknown')}
标签: {', '.join(skill_data.get('tags', []))}
文件结构: {json.dumps([f['path'] for f in file_structure], indent=2)}

文件内容摘要:
{json.dumps(file_contents, indent=2, ensure_ascii=False)}

请生成以下 JSON 格式的内容（只输出 JSON，不要包含 markdown 代码块或任何其他文字）：
{{
  "user_title": "用户友好的标题（动词开头，如 'Master Python async patterns'）",
  "value_statement": "100-200 字的价值陈述，说明这个 skill 解决什么问题",
  "seo_keywords": ["关键词1", "关键词2"],
  "actual_capabilities": ["能力1", "能力2"],
  "limitations": ["限制1", "限制2"],
  "use_cases": [
    {{"target_user": "目标用户", "title": "用例标题", "description": "详细描述"}}
  ],
  "prompt_templates": [
    {{"title": "模板标题", "scenario": "使用场景", "prompt": "示例提示"}}
  ],
  "output_examples": [
    {{"input": "输入描述", "output": ["输出行1", "输出行2"]}}
  ],
  "best_practices": ["最佳实践1"],
  "anti_patterns": ["反模式1"],
  "faq": [
    {{"question": "问题", "answer": "回答"}}
  ]
}}"""

    if verbose:
        console.print(f"[dim]Calling AI model: {model}")

    retry = config.get("generation", {}).get("retry", 2)
    last_error = None

    for attempt in range(retry + 1):
        try:
            # 使用流式输出显示模型执行过程
            console.print(f"[cyan]🔄 模型思考中...[/cyan]")

            stream = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a technical documentation expert. Generate structured JSON content for skill reports. Always respond with valid JSON only, no markdown formatting."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=3000,
                stream=True  # 启用流式输出
            )

            # 实时显示模型输出
            content_chunks = []
            with console.status("[bold green]生成中...[/bold green]", spinner="dots") as status:
                for chunk in stream:
                    if chunk.choices[0].delta.content:
                        text = chunk.choices[0].delta.content
                        content_chunks.append(text)
                        # 实时打印输出（可选）
                        if verbose:
                            console.print(text, end="", style="dim")

            console.print()  # 换行
            content_text = "".join(content_chunks).strip()

            # 清理可能的 markdown 代码块
            if content_text.startswith("```"):
                content_text = re.sub(r'^```(?:json)?\s*\n', '', content_text)
                content_text = re.sub(r'\n```\s*$', '', content_text)

            return json.loads(content_text)

        except json.JSONDecodeError as e:
            last_error = e
            if verbose:
                console.print(f"[yellow]JSON parse error (attempt {attempt + 1}): {e}")
        except Exception as e:
            last_error = e
            if verbose:
                console.print(f"[yellow]API error (attempt {attempt + 1}): {e}")

    raise Exception(f"Failed to generate content after {retry + 1} attempts: {last_error}")


# ============================================================================
# 报告生成
# ============================================================================

def compute_hashes(skill_dir: Path) -> tuple:
    """计算内容 hash 和树结构 hash"""
    content_hash = hashlib.sha256()
    tree_hash = hashlib.sha256()

    files = sorted(skill_dir.rglob("*"), key=lambda x: str(x.relative_to(skill_dir)))

    for f in files:
        if f.is_file() and not f.name.startswith('.'):
            relative = str(f.relative_to(skill_dir))
            tree_hash.update(relative.encode() + b'\n')
            try:
                content_hash.update(f.read_bytes())
            except:
                pass

    return content_hash.hexdigest(), tree_hash.hexdigest()


def generate_slug(skill_data: dict, skill_dir: Path) -> str:
    """生成 slug"""
    name = skill_data.get("name", skill_dir.name)
    author = skill_data.get("author", "")

    namespace = re.sub(r'[^a-z0-9]', '-', author.lower()).strip('-') if author else "unknown"
    slug = re.sub(r'[^a-z0-9]', '-', name.lower()).strip('-')

    return f"{namespace}-{slug}"


def generate_report(skill_dir: Path, config: dict, verbose: bool = False) -> dict:
    """生成完整的 skill-report.json"""

    if verbose:
        console.print(f"\n[cyan]Processing: {skill_dir}")

    # 1. 解析 SKILL.md
    skill_data = parse_skill_md(skill_dir)
    skill_data["skill_dir"] = str(skill_dir)

    # 2. 扫描文件结构
    file_structure = scan_file_structure(skill_dir)

    # 3. 安全审计
    security_audit = analyze_security(skill_dir, config)

    # 4. AI 生成内容
    ai_content = generate_content_with_ai(skill_data, file_structure, config, verbose)

    # 5. 计算 hash
    content_hash, tree_hash = compute_hashes(skill_dir)

    # 6. 生成 slug
    slug = generate_slug(skill_data, skill_dir)

    # 7. 获取来源信息
    source_url = f"https://github.com/{skill_data.get('author', 'unknown')}/skills/tree/main/{skill_data.get('name', skill_dir.name)}"

    # 8. 组装完整报告
    now = datetime.now(timezone.utc)

    report = {
        "schema_version": "2.0",
        "meta": {
            "generated_at": now.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "slug": slug,
            "source_url": source_url,
            "source_ref": "main",
            "model": config.get("api", {}).get("model", "gpt-4o"),
            "analysis_version": "1.0.0",
            "source_type": "community",
            "content_hash": content_hash,
            "tree_hash": tree_hash
        },
        "skill": {
            "name": skill_data.get("name", skill_dir.name),
            "description": skill_data.get("description", ""),
            "summary": skill_data.get("description", "")[:100] + ("..." if len(skill_data.get("description", "")) > 100 else ""),
            "icon": skill_data.get("icon", "📦"),
            "version": skill_data.get("version", "1.0.0"),
            "author": skill_data.get("author", "unknown"),
            "license": skill_data.get("license", "MIT"),
            "category": skill_data.get("category", "coding"),
            "tags": skill_data.get("tags", []),
            "supported_tools": skill_data.get("supported_tools", ["claude", "codex", "claude-code"]),
            "risk_factors": security_audit.get("risk_factors", [])
        },
        "security_audit": {
            "risk_level": security_audit.get("risk_level", "safe"),
            "is_blocked": security_audit.get("is_blocked", False),
            "safe_to_publish": security_audit.get("safe_to_publish", True),
            "summary": security_audit.get("summary", ""),
            "risk_factor_evidence": security_audit.get("risk_factor_evidence", []),
            "critical_findings": security_audit.get("critical_findings", []),
            "high_findings": security_audit.get("high_findings", []),
            "medium_findings": security_audit.get("medium_findings", []),
            "low_findings": security_audit.get("low_findings", []),
            "dangerous_patterns": security_audit.get("dangerous_patterns", []),
            "files_scanned": security_audit.get("files_scanned", 0),
            "total_lines": security_audit.get("total_lines", 0),
            "audit_model": config.get("api", {}).get("model", "gpt-4o"),
            "audited_at": now.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        },
        "content": {
            "user_title": ai_content.get("user_title", f"Use {skill_data.get('name', 'this skill')}"),
            "value_statement": ai_content.get("value_statement", ""),
            "seo_keywords": ai_content.get("seo_keywords", []),
            "actual_capabilities": ai_content.get("actual_capabilities", []),
            "limitations": ai_content.get("limitations", []),
            "use_cases": ai_content.get("use_cases", []),
            "prompt_templates": ai_content.get("prompt_templates", []),
            "output_examples": ai_content.get("output_examples", []),
            "best_practices": ai_content.get("best_practices", []),
            "anti_patterns": ai_content.get("anti_patterns", []),
            "faq": ai_content.get("faq", [])
        },
        "file_structure": file_structure
    }

    return report


# ============================================================================
# 主程序
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Skill Report Generator - 手工生成 skill-report.json",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--input", "-i", nargs="+", required=True, help="输入路径（skill 目录）")
    parser.add_argument("--scan", action="store_true", help="扫描目录自动发现 SKILL.md")
    parser.add_argument("--output", "-o", help="输出目录（默认原地覆盖）")
    parser.add_argument("--config", "-c", help="配置文件路径")
    parser.add_argument("--base-url", help="覆盖 API base URL")
    parser.add_argument("--model", help="覆盖模型名称")
    parser.add_argument("--concurrent", type=int, help="并发数")
    parser.add_argument("--dry-run", action="store_true", help="预览模式，不写入文件")
    parser.add_argument("--verbose", "-v", action="store_true", help="详细输出")

    args = parser.parse_args()

    # 加载配置
    config = load_config(args.config)

    # 命令行覆盖
    if args.base_url:
        config["api"]["base_url"] = args.base_url
    if args.model:
        config["api"]["model"] = args.model
    if args.concurrent:
        config["generation"]["concurrent"] = args.concurrent

    # 发现 skills
    console.print("\n[bold]Skill Report Generator[/bold]\n")
    skills = discover_skills(args.input, args.scan)

    if not skills:
        console.print("[red]No skills found![/red]")
        sys.exit(1)

    console.print(f"Found [green]{len(skills)}[/green] skill(s)\n")

    # 处理 skills
    output_dir = Path(args.output) if args.output else None
    concurrent = config.get("generation", {}).get("concurrent", 3)
    results = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]"),
        BarColumn(),
        TextColumn("[progress.percentage]"),
        console=console
    ) as progress:
        task = progress.add_task("Processing", total=len(skills))

        def process_skill(skill_dir: Path) -> tuple:
            try:
                report = generate_report(skill_dir, config, args.verbose)
                return (skill_dir, report, None)
            except Exception as e:
                return (skill_dir, None, str(e))

        with ThreadPoolExecutor(max_workers=concurrent) as executor:
            futures = [executor.submit(process_skill, s) for s in skills]
            for future in futures:
                skill_dir, report, error = future.result()
                progress.update(task, advance=1, description=f"Processed {skill_dir.name}")

                if error:
                    console.print(f"[red]Error processing {skill_dir}: {error}[/red]")
                    results.append((skill_dir, None, error))
                else:
                    results.append((skill_dir, report, None))

        progress.remove_task(task)

    # 输出结果
    success_count = 0
    error_count = 0

    for skill_dir, report, error in results:
        if error:
            error_count += 1
        else:
            success_count += 1

            if args.dry_run:
                console.print(f"\n[yellow]DRY RUN - Would write to: {skill_dir / 'skill-report.json'}[/yellow]")
                if args.verbose:
                    console.print_json(json.dumps(report, indent=2, ensure_ascii=False))
            else:
                if output_dir:
                    rel_path = skill_dir.name
                    out_path = output_dir / rel_path / "skill-report.json"
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                else:
                    out_path = skill_dir / "skill-report.json"

                with open(out_path, 'w', encoding='utf-8') as f:
                    json.dump(report, f, indent=2, ensure_ascii=False)

                console.print(f"[green]Generated: {out_path}[/green]")

    # 总结
    console.print(f"\n[bold]Summary[/bold]")
    table = Table(show_header=True)
    table.add_column("Metric", "Value")
    table.add_row("Total skills", str(len(skills)))
    table.add_row("Success", f"[green]{success_count}[/green]")
    table.add_row("Errors", f"[red]{error_count}[/red]" if error_count else f"[green]{error_count}[/green]")
    console.print(table)


if __name__ == "__main__":
    main()
