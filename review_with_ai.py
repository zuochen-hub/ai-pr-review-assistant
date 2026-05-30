# review_with_ai.py
import warnings
warnings.filterwarnings('ignore')
import sys
import json
import hashlib
import os
import time
import requests
from typing import Optional, Dict, Any
from langchain_deepseek import ChatDeepSeek
from langchain.tools import tool
from langgraph.prebuilt import create_react_agent

# ========== 配置区域 ==========
GITHUB_TOKEN = "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"
DEEPSEEK_API_KEY = "sk-7dfab548c37941b98a67fc15714d7eed"

# 缓存目录（用于避免重复分析同一PR）
CACHE_DIR = ".cache"
os.makedirs(CACHE_DIR, exist_ok=True)


# ============================

def get_cache_key(pr_url: str) -> str:
    """生成缓存key"""
    return hashlib.md5(pr_url.encode()).hexdigest()


def get_cached_result(pr_url: str) -> Optional[Dict]:
    """读取缓存"""
    cache_file = os.path.join(CACHE_DIR, get_cache_key(pr_url))
    if os.path.exists(cache_file):
        with open(cache_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None


def save_cache(pr_url: str, result: Dict):
    """保存缓存"""
    cache_file = os.path.join(CACHE_DIR, get_cache_key(pr_url))
    with open(cache_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)


@tool
def get_pr_diff(pr_url: str) -> str:
    """获取 GitHub PR 的代码修改内容（diff 格式）"""
    parts = pr_url.replace("https://github.com/", "").split("/")
    if len(parts) < 4:
        return "错误：PR URL 格式不正确"
    owner, repo, pr_number = parts[0], parts[1], int(parts[3])

    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3.diff"
    }
    response = requests.get(url, headers=headers, verify=False)

    if response.status_code == 200:
        diff = response.text
        # 截断过长的 diff（保留前 5000 行）
        lines = diff.split('\n')
        if len(lines) > 5000:
            diff = '\n'.join(lines[:5000]) + f"\n... (diff 过长，仅显示前5000行，共{len(lines)}行)"
        return diff
    else:
        return f"获取失败，错误码：{response.status_code}"


@tool
def get_pr_metadata(pr_url: str) -> str:
    """获取 PR 的标题、描述等元数据"""
    parts = pr_url.replace("https://github.com/", "").split("/")
    if len(parts) < 4:
        return "错误：PR URL 格式不正确"
    owner, repo, pr_number = parts[0], parts[1], int(parts[3])

    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    response = requests.get(url, headers=headers, verify=False)

    if response.status_code == 200:
        data = response.json()
        return f"PR标题：{data.get('title', '无')}\nPR描述：{data.get('body', '无')}\n作者：{data.get('user', {}).get('login', '未知')}"
    else:
        return "获取 PR 元数据失败"


@tool
def post_github_comment(pr_url: str, comment: str) -> str:
    """在 GitHub PR 下发布评论"""
    parts = pr_url.replace("https://github.com/", "").split("/")
    if len(parts) < 4:
        return "错误：PR URL 格式不正确"
    owner, repo, pr_number = parts[0], parts[1], int(parts[3])

    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{pr_number}/comments"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    data = {"body": comment}
    response = requests.post(url, headers=headers, json=data, verify=False)

    if response.status_code == 201:
        return f"✅ 评论已发布到 {pr_url}"
    else:
        return f"❌ 发布失败，错误码：{response.status_code}"


def filter_false_positives(analysis: Dict) -> Dict:
    """简单的误报过滤规则"""
    if 'risks' not in analysis:
        return analysis

    filtered_risks = []
    for risk in analysis['risks']:
        description = risk.get('description', '').lower()
        # 过滤明显不合理的警告
        false_positive_patterns = [
            ('缺少注释', len(description) < 50),  # 小文件缺少注释不算风险
            ('命名不规范', 'i' in description or 'j' in description or 'k' in description),  # 循环变量
            ('没有错误处理', 'example' in description or 'demo' in description),  # 示例代码
        ]
        is_false_positive = any(pattern in description and condition for pattern, condition in false_positive_patterns)
        if not is_false_positive:
            filtered_risks.append(risk)

    analysis['risks'] = filtered_risks
    analysis['false_positive_filtered'] = len(analysis.get('risks', [])) - len(filtered_risks)
    return analysis


def create_analysis_prompt(diff: str, metadata: str) -> str:
    """构建分析提示词"""
    return f"""
你是一个专业的代码评审专家。请分析以下 PR，并严格按照 JSON 格式输出。

PR 元数据：
{metadata}

代码修改内容（diff）：
{diff}

请按以下 JSON 格式输出（不要输出其他内容）：
{{
  "summary": "一句话总结这个 PR 的主要变更",
  "risks": [
    {{"severity": "high|medium|low", "description": "风险描述", "suggestion": "修复建议", "file": "文件名（如果知道）"}}
  ],
  "suggestions": ["改进建议1", "改进建议2"],
  "overall_assessment": "pass|warn|fail",
  "key_changes": ["关键变更点1", "关键变更点2"]
}}

注意：
- severity 只使用 high/medium/low
- overall_assessment 只使用 pass/warn/fail
- 如果没有发现风险，risks 可以为空数组
- 不要输出 JSON 之外的任何内容
"""


def run_agent(pr_url: str, use_cache: bool = True) -> Dict[str, Any]:
    """运行 Agent，返回结构化的分析结果"""
    start_time = time.time()

    # 检查缓存
    if use_cache:
        cached = get_cached_result(pr_url)
        if cached:
            cached['from_cache'] = True
            cached['response_time'] = 0
            return cached

    # 初始化模型
    llm = ChatDeepSeek(
        model="deepseek-chat",
        temperature=0.3,  # 降低随机性，提高准确性
        api_key=DEEPSEEK_API_KEY,
    )

    # 创建 Agent
    agent = create_react_agent(
        model=llm,
        tools=[get_pr_diff, get_pr_metadata],
    )

    # 第一步：获取 diff 和 metadata
    diff = get_pr_diff.invoke({"pr_url": pr_url})
    if diff.startswith("错误") or diff.startswith("获取失败"):
        return {"error": diff, "success": False}

    metadata = get_pr_metadata.invoke({"pr_url": pr_url})

    # 第二步：让 AI 分析
    prompt = create_analysis_prompt(diff, metadata)
    response = agent.invoke({
        "messages": [{"role": "user", "content": prompt}]
    })

    # 解析 AI 输出
    ai_content = response["messages"][-1].content
    try:
        # 尝试提取 JSON
        if "```json" in ai_content:
            ai_content = ai_content.split("```json")[1].split("```")[0]
        elif "```" in ai_content:
            ai_content = ai_content.split("```")[1].split("```")[0]
        analysis = json.loads(ai_content)
    except json.JSONDecodeError:
        # 如果解析失败，返回原始内容
        analysis = {
            "summary": "AI 输出格式异常，请查看原始内容",
            "risks": [],
            "suggestions": [],
            "overall_assessment": "warn",
            "raw_output": ai_content
        }

    # 应用误报过滤
    analysis = filter_false_positives(analysis)
    analysis['success'] = True
    analysis['response_time'] = round(time.time() - start_time, 2)
    analysis['from_cache'] = False

    # 保存缓存
    save_cache(pr_url, analysis)

    return analysis


def format_output(analysis: Dict) -> str:
    """将分析结果格式化为可读文本"""
    if not analysis.get('success'):
        return f"❌ 分析失败：{analysis.get('error', '未知错误')}"

    if analysis.get('from_cache'):
        cache_note = "📦 (来自缓存，本次未重新分析)\n"
    else:
        cache_note = f"⏱️ 响应时间：{analysis.get('response_time', 'N/A')} 秒\n"

    output = f"""
{'=' * 60}
🤖 AI PR Review 报告
{'=' * 60}

📋 变更总结：
{analysis.get('summary', '无')}

🔴 风险识别：
"""
    for risk in analysis.get('risks', []):
        severity_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(risk.get('severity'), "⚪")
        output += f"\n  {severity_icon} [{risk.get('severity', 'unknown').upper()}] {risk.get('description', '')}"
        if risk.get('file'):
            output += f"\n      📁 {risk.get('file')}"
        if risk.get('suggestion'):
            output += f"\n      💡 {risk.get('suggestion')}"

    output += "\n\n💡 改进建议：\n"
    for i, sug in enumerate(analysis.get('suggestions', []), 1):
        output += f"  {i}. {sug}\n"

    overall_icon = {"pass": "✅", "warn": "⚠️", "fail": "❌"}.get(analysis.get('overall_assessment'), "❓")
    output += f"\n📊 总体评估：{overall_icon} {analysis.get('overall_assessment', 'unknown').upper()}\n"
    output += f"\n{cache_note}"
    output += f"{'=' * 60}"

    return output


def post_comment_to_pr(pr_url: str, analysis: Dict) -> str:
    """将分析结果发布到 PR 评论区"""
    comment_body = format_output(analysis)
    return post_github_comment.invoke({"pr_url": pr_url, "comment": comment_body})


if __name__ == "__main__":
    # 支持命令行参数
    if len(sys.argv) > 1:
        pr_url = sys.argv[1]
    else:
        pr_url = input("请输入 PR 地址: ").strip()

    if not pr_url:
        print("❌ 未提供 PR 地址")
        sys.exit(1)

    print(f"🔍 正在分析 PR: {pr_url}")
    print("⏳ 这可能需要 10-15 秒...\n")

    # 运行分析
    analysis = run_agent(pr_url)

    # 打印结果
    print(format_output(analysis))

    # 询问是否发布评论
    if analysis.get('success') and not analysis.get('from_cache'):
        post = input("\n是否将分析结果发布到 PR 评论区？(y/n): ").strip().lower()
        if post == 'y':
            result = post_comment_to_pr(pr_url, analysis)
            print(f"\n{result}")