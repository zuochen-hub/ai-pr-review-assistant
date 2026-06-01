AI PR Review 助手

功能：自动分析 GitHub PR 代码，给出评审意见，并发布评论。

安装：
pip install langchain-deepseek langgraph requests

配置环境变量：
GITHUB_TOKEN=你的GitHub令牌
DEEPSEEK_API_KEY=你的DeepSeek密钥

运行：
python review_with_ai.py https://github.com/用户名/仓库名/pull/编号

技术栈：Python + LangGraph + DeepSeek + GitHub API

演示视频：https://www.bilibili.com/video/BV14WV96YExf/?share_source=copy_web&vd_source=5447514bcfc86eee5b5cf9e8d4e81105
