import os
from pathlib import Path
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langchain_core.tools import tool

load_dotenv()

# ----------------------------------------------------
# 全局单例 LLM (所有 Node 共享)
# ----------------------------------------------------
llm = ChatOpenAI(
    model=os.getenv("MODEL"),
    openai_api_key=os.getenv("ZAI_API_KEY"),
    openai_api_base=os.getenv("BASE_URL"),
    temperature=0.6,
)


# ----------------------------------------------------
# 1. 真实 arXiv 学术论文检索工具 (Real arXiv API)
# ----------------------------------------------------
@tool
def arxiv_paper_search(query: str) -> str:
    """
    通过官方 arXiv API 实时检索最新的学术论文、架构设计与算法基准。
    返回真实的论文标题、作者、发布日期、arXiv URL 链接以及论文摘要。
    """
    print(f"  [Real Tool: arXiv] 正在真实检索学术论文库 -> '{query}'")
    try:
        import arxiv
        client = arxiv.Client()
        search = arxiv.Search(
            query=query,
            max_results=2,
            sort_by=arxiv.SortCriterion.Relevance
        )
        results = list(client.results(search))
        if results:
            snippets = []
            for paper in results:
                authors = ", ".join([a.name for a in paper.authors[:3]])
                published = paper.published.strftime("%Y-%m-%d")
                snippets.append(
                    f"【论文标题】: {paper.title}\n"
                    f"【作者】: {authors}\n"
                    f"【发布日期】: {published}\n"
                    f"【原文链接】: {paper.entry_id}\n"
                    f"【论文摘要】:\n{paper.summary.strip()}"
                )
            return "\n\n" + "="*40 + "\n\n".join(snippets)
    except Exception as e:
        print(f"  [Real Tool: arXiv] 检索遇到网络波动: {e}")

    return f"【arXiv 检索】未找到与 '{query}' 直接匹配的公开预印本论文。"


# ----------------------------------------------------
# 2. 真实 Wikipedia 维基百科权威检索工具 (Real Wikipedia API)
# ----------------------------------------------------
@tool
def wikipedia_search(query: str) -> str:
    """
    通过官方 Wikipedia API 检索权威百科词条、技术术语定义、历史背景与企业概况。
    返回真实的维基百科正文摘要与参考链接。
    """
    print(f"  [Real Tool: Wikipedia] 正在真实检索维基百科 -> '{query}'")
    try:
        import wikipedia
        wikipedia.set_lang("zh")  # 优先中文维基
        try:
            summary = wikipedia.summary(query, sentences=4)
            page = wikipedia.page(query)
            return (
                f"【维基百科词条】: {page.title}\n"
                f"【条目链接】: {page.url}\n"
                f"【权威摘要】:\n{summary}"
            )
        except Exception:
            # 中文未搜到时尝试英文维基
            wikipedia.set_lang("en")
            summary = wikipedia.summary(query, sentences=4)
            page = wikipedia.page(query)
            return (
                f"【Wikipedia Entry】: {page.title}\n"
                f"【URL】: {page.url}\n"
                f"【Summary】:\n{summary}"
            )
    except Exception as e:
        print(f"  [Real Tool: Wikipedia] 检索遇到网络波动: {e}")

    return f"【Wikipedia 检索】未找到与 '{query}' 相关的词条。"


# ----------------------------------------------------
# 3. 真实 DuckDuckGo 互联网实时搜索工具 (Real Web Search)
# ----------------------------------------------------
@tool
def web_search(query: str) -> str:
    """
    通过搜索引擎实时检索互联网最新的公开网页资讯、技术博客、行业动态与评测。
    返回真实的网页标题、正文摘要和来源 URL。
    """
    print(f"  [Real Tool: Web Search] 正在真实检索互联网网页 -> '{query}'")
    try:
        from duckduckgo_search import DDGS
        ddgs = DDGS(timeout=5)
        results = list(ddgs.text(query, max_results=3))
        if results:
            snippets = []
            for item in results:
                title = item.get("title", "未命名网页")
                body = item.get("body", "")
                link = item.get("href", "")
                snippets.append(
                    f"【网页标题】: {title}\n"
                    f"【内容摘要】: {body}\n"
                    f"【来源网址】: {link}"
                )
            return "\n\n" + "-"*40 + "\n\n".join(snippets)
    except Exception as e:
        print(f"  [Real Tool: Web Search] 联网检索遇到网络波动: {e}")

    return f"【Web 实时搜索】未检索到关于 '{query}' 的最新网页。"


# ----------------------------------------------------
# 4. 真实 Markdown 研报文件落盘工具 (Real File IO)
# ----------------------------------------------------
@tool
def save_markdown_report(content: str, filename: str = "research_report.md") -> str:
    """
    将生成的 Markdown 格式完整研究报告真实写入本地 outputs 目录中。
    参数：
      content: Markdown 文本内容
      filename: 目标文件名 (如 deepseek_v3_research.md)
    """
    output_dir = Path(__file__).parent / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)

    if not filename.endswith(".md"):
        filename += ".md"

    target_path = output_dir / filename
    target_path.write_text(content, encoding="utf-8")
    print(f"  [Real Tool: Save] 研报已成功落盘至真实文件 -> {target_path}")
    return str(target_path)


# 导出真实工具列表
research_tools = [arxiv_paper_search, wikipedia_search, web_search, save_markdown_report]