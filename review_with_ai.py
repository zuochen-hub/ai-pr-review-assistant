# review_with_ai.py
import warnings
warnings.filterwarnings('ignore')
import requests
from langchain_deepseek import ChatDeepSeek
from langchain.tools import tool
from langgraph.prebuilt import create_react_agent

# ========== 配置区域（请替换为真实值）==========
GITHUB_TOKEN = "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"  # 替换成你自己的
DEEPSEEK_API_KEY = "sk-7dfab548c37941b98a67fc15714d7eed"  # 替换成你自己的

owner = "zuochen-hub"
repo = "test"
pr_number = 2


# ============================================

# 1. 工具1：获取 PR 的 diff
@tool
def get_pr_diff(pr_url: str) -> str:
    """
    获取 GitHub PR 的代码修改内容（diff 格式）。
    输入格式：https://github.com/owner/repo/pull/123
    """
    # 从 URL 解析 owner, repo, pr_number
    parts = pr_url.replace("https://github.com/", "").split("/")
    owner, repo, pr_number = parts[0], parts[1], int(parts[3])

    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3.diff"
    }
    response = requests.get(url, headers=headers, verify=False)

    if response.status_code == 200:
        return response.text
    else:
        return f"获取失败，错误码：{response.status_code}"


# 2. 工具2：在 PR 下发布评论
@tool
def post_github_comment(pr_url: str, comment: str) -> str:
    """
    在 GitHub PR 下发布评论。
    输入 PR 地址和要发布的评论内容。
    """
    # 解析 URL
    parts = pr_url.replace("https://github.com/", "").split("/")
    owner, repo, pr_number = parts[0], parts[1], int(parts[3])

    # GitHub API 端点（PR 评论复用 issues 端点）
    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{pr_number}/comments"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    data = {"body": comment}

    response = requests.post(url, headers=headers, json=data, verify=False)
    if response.status_code == 201:
        return f"✅ 评论已成功发布到 {pr_url}"
    else:
        return f"❌ 发布失败，错误码：{response.status_code}"


# 3. 初始化 DeepSeek 模型
llm = ChatDeepSeek(
    model="deepseek-v4-flash",
    temperature=0.3,
    api_key=DEEPSEEK_API_KEY,
    extra_body={"thinking": {"type": "disabled"}}
)

# 4. 创建 Agent（注册两个工具）
agent = create_react_agent(
    model=llm,
    tools=[get_pr_diff, post_github_comment],
)

# 5. 运行 Agent，让它自主完成整个任务
if __name__ == "__main__":
    pr_url = f"https://github.com/{owner}/{repo}/pull/{pr_number}"

    # 给 Agent 的指令：明确要求先看代码，再分析，最后发评论
    user_instruction = f"""
请按以下步骤完成任务：

1. 调用 get_pr_diff 工具获取这个 PR 的代码修改：{pr_url}
2. 仔细分析代码修改，指出其中的风险、问题和改进建议
3. 调用 post_github_comment 工具，将你的分析结果作为评论发布到同一个 PR 下

注意：三个步骤必须全部完成，不要省略任何一个。
"""

    result = agent.invoke({
        "messages": [{"role": "user", "content": user_instruction}]
    })

    # 打印 Agent 的最终回答（通常是对任务完成的确认）
    print("\n" + "=" * 50)
    print("Agent 执行结果：")
    print("=" * 50)
    print(result["messages"][-1].content)