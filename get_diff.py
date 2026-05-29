import requests

# 请在 GitHub Settings → Developer settings → Personal access tokens → Tokens (classic)
# 生成一个 token，勾选 repo 权限，然后把 token 粘贴在两个引号之间
GITHUB_TOKEN = "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"

def get_pr_diff(owner, repo, pr_number):
    """获取 GitHub PR 的代码修改内容（diff）"""
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3.diff"
    }
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        return response.text
    else:
        return f"获取失败，错误码：{response.status_code}"

if __name__ == "__main__":
    # 用一个小 PR 来测试（这个 PR 是真实的、内容简单的）
    owner = "facebook"
    repo = "react"
    pr_number = 30000
    
    diff_result = get_pr_diff(owner, repo, pr_number)
    print(diff_result)
