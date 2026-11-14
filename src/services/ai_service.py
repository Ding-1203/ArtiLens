import os
import re
import json
from typing import List, Dict, Any

import requests
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from langchain.chains import RetrievalQA
from langchain_community.chat_models.tongyi import ChatTongyi
from langchain_core.prompts import ChatPromptTemplate
from langchain.schema import Document
from langgraph.graph import StateGraph, END

from configs import DATA_DIR

import time  # 用于访问时间限制
from typing import List, Dict, Any, TypedDict, Annotated, Literal, Optional
from operator import itemgetter

# --- LangChain 新增依赖 ---
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.tools import tool, Tool
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

# 导入 Paper 模型，以便访问其属性
from models.paper import Paper

from sqlalchemy.orm import Session
from models.db import get_db_session
from models.paper import ChatSession
from fastapi import Depends

from pathlib import Path
import zhipuai


class S2State(TypedDict):
    title: str
    s2_id: str | None
    references: List[Dict]
    citations: List[Dict]
    final_result: str | Dict


class AIService:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv('DASHSCOPE_API_KEY')
        self.llm = ChatTongyi(
            # name="qwen-turbo",
            # name="qwen-max",
            name="qwen-plus",
            streaming=True,
            api_key=self.api_key
        )
        self.zhipu_api_key = os.getenv('ZHIPU_API_KEY')
        if self.zhipu_api_key:
            self.zhipu_client = zhipuai.ZhipuAI(api_key=self.zhipu_api_key)
        else:
            self.zhipu_client = None
            print("[WARNING] ZHIPU_API_KEY not found. Image understanding will be disabled.")
        self.embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2"
        )
        # self.embeddings = OpenAIEmbeddings()
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            length_function=len,
        )
        self.vectorstore = None
        self.qa_chain = None
        self.rag_search_tool = self._get_rag_search_tool()
        self.generate_mindmap_mermaid = self._get_generate_mindmap_mermaid_tool()
        self.generate_flowchart_mermaid = self._get_generate_flowchart_mermaid_tool()

        # 查看被引用文献基本信息
        # 我们不再从环境变量中读取S2_API_KEY，强制使用无Key模式
        # S2 API 配置
        self.s2_api_base = "https://api.semanticscholar.org/graph/v1"

        # --- 新增: Agent 相关变量 ---
        self.agent_executor = None

    def _simple_prompt(self, user_msg: str, system_msg: str = "") -> str:
        messages = []
        if system_msg:
            messages.append({"role": "system", "content": system_msg})
        messages.append({"role": "user", "content": user_msg})

        answer = self.llm.invoke(messages).content
        print(f"[LLM] answer: {answer[:20]}...")
        return answer

    def setup_rag(self, paper_content: str, paper_id: int):
        """设置RAG系统"""
        try:
            # 分割文档
            texts = self.text_splitter.split_text(paper_content)
            documents = [Document(page_content=text) for text in texts]

            # 创建向量存储
            persist_directory = os.path.join(DATA_DIR, "chroma_db", f"paper_{paper_id}")
            self.vectorstore = Chroma.from_documents(
                documents=documents,
                embedding=self.embeddings,
                persist_directory=persist_directory
            )

            # 创建QA链
            self.qa_chain = RetrievalQA.from_chain_type(
                llm=self.llm,
                chain_type="refine",
                retriever=self.vectorstore.as_retriever(search_kwargs={"k": 5}),
                return_source_documents=True
            )

            return True
        except Exception as e:
            print(f"Error setting up RAG: {str(e)}")
            return False

    def load_rag(self, paper_id: int):
        """加载已存在的RAG系统"""
        try:
            persist_directory = os.path.join(DATA_DIR, "chroma_db", f"paper_{paper_id}")
            if os.path.exists(persist_directory):
                self.vectorstore = Chroma(
                    persist_directory=persist_directory,
                    embedding_function=self.embeddings
                )

                self.qa_chain = RetrievalQA.from_chain_type(
                    llm=self.llm,
                    chain_type="refine",
                    retriever=self.vectorstore.as_retriever(search_kwargs={"k": 5}),
                    return_source_documents=True
                )

                return True
            return False
        except Exception as e:
            print(f"Error loading RAG: {str(e)}")
            return False

    def generate_single_sentence_summary(self, abstract: str, title: str):
        """一句话概括"""
        system_prompt = """
        你是一名学术助手，尤其擅长捕捉重点、理解和概括
        """
        user_prompt = f"""
        结合以下内容，为论文生成一个一句话概括
        用一句话或一小段话通俗地解释这篇论文在做什么：

        论文标题：{title}
        论文摘要：{abstract}

        要求：
        1. 用通俗易懂的语言
        2. 突出论文的核心贡献
        3. 控制在50字以内
        """

        return self._simple_prompt(system_prompt, user_prompt)

    def generate_abstract(self, abstract: str) -> str:
        """生成简明摘要"""
        system_prompt = """
        你是一位精通英文和简体中文的专业翻译，尤其擅长将专业学术论文翻译成浅显易懂的科普文章。
        """
        user_prompt = f"""
        请将以下英文学术论文的摘要部分内容翻译成简体中文，保持学术性和准确性：

        {abstract}

        翻译要求：
        1. 保持原文的学术风格
        2. 专业术语要准确
        3. 语言要流畅自然
        """

        return self._simple_prompt(user_prompt, system_prompt)

    def extract_key_content(self, key_sections: dict, title: str) -> str:
        """提取关键内容"""
        introduction_text = key_sections.get("introduction", "not found introduction")
        method_text = key_sections.get("method", "not found method")
        experiments_text = key_sections.get("experiments", "not found experiments")
        conclusion_text = key_sections.get("conclusion", "not found conclusion")
        system_prompt = """
        你是一位专业的学术助手，尤其擅长阅读、理解学术论文
        """
        user_prompt = f"""
        请基于以下论文内容，提取并总结关键信息：

        论文标题：{title}
        
        论文主要章节内容：
        <introduction部分>: {introduction_text}
        <method部分>: {method_text}
        <experiments部分>: {experiments_text}
        <conclusion部分>: {conclusion_text}

        请参考以下格式总结：
        - **研究问题**：本论文试图解决的核心问题是什么？研究背景是什么？
        - **提出的方法**：作者提出了什么方法？它的核心思想和创新点是什么？（作为重点可以相对详细一些）
        - **实验设置与结果**：作者是如何进行实验的？实验结果是否证明了方法的有效性？
        - **结论与未来工作**：论文得出的主要结论是什么？有没有提出未来的研究方向？

        每项用不超过5句话概括，简明扼要、专业准确，逻辑清晰。
        请输出为 Markdown 格式，**仅**输出 markdown 源码，不要用 <code> 或 ```markdown 代码块 包裹
        """

        return self._simple_prompt(user_prompt, system_prompt)

    # def translate_text(self, text: str) -> str:
    #     """翻译文本"""
    #     system_prompt = """
    #     你是一位精通英文和简体中文的专业翻译
    #     """
    #     user_prompt = f"""
    #     请将以下英文学术论文内容翻译成简体中文，保持学术性和准确性：
    #
    #     {text}
    #
    #     翻译要求：
    #     1. 保持原文的学术风格
    #     2. 专业术语要准确
    #     3. 语言要流畅自然
    #     """
    #
    #     return self._simple_prompt(user_prompt, system_prompt)

    # def extract_terminology_list(self, text: str) -> list:
    #     """
    #     返回论文中若干关键术语的列表，不要解释。
    #     """
    #     system_prompt = """
    #     你是一名学术助手，擅长从论文中识别关键术语。请严格根据用户指令，从文本中提取术语，格式规范、简洁清晰。
    #     """
    #
    #     user_prompt = f"""
    #     请从以下论文内容中提取5到10个最重要的专业术语。仅返回术语本身，每行一个，**不要添加解释、标点或编号**，不要空行，输出如下格式：
    #
    #     术语1
    #     术语2
    #     ...
    #     术语10
    #
    #     论文正文如下：
    #     {text}
    #     """
    #     resp = self._simple_prompt(user_prompt, system_prompt)
    #     return [line.strip() for line in resp.splitlines() if line.strip()]

    def extract_terminology_list(self, text: str) -> list:
        """
        返回论文若干关键术语及中文翻译。格式为 [{'en':..., 'zh':...}, ...]
        """
        system_prompt = """
        你是一名学术助手，擅长从论文中识别关键英文术语并给出准确的中文译名。
        """

        user_prompt = f"""
        请从以下论文内容中，提取5到10个最重要的英文专业术语，并给出对应的中文翻译，只返回术语对，中英文以逗号相隔，每个术语输出一行，格式如下：
        英文术语1, 中文译名1
        英文术语2, 中文译名2
        ...
        
        例如：
        Overfitting, 过拟合
        Gradient Descent, 梯度下降
        ...
        
        不要加编号、解释、标点，严格用英文逗号分割。不要有多余空行。
        论文正文如下：
        {text}
        """
        resp = self._simple_prompt(user_prompt, system_prompt)
        term_pairs = []
        for line in resp.splitlines():
            if not line.strip():
                continue
            parts = [p.strip() for p in line.split(',', 1)]
            if len(parts) == 2:
                term_pairs.append({'en': parts[0], 'zh': parts[1]})
        return term_pairs

    def analyze_research_context(self, title: str, abstract: str, key_content: str, references: str) -> str:
        """分析研究脉络"""
        system_prompt = """
        你是一名学术助手，有充足的学术论文知识储备，尤其擅长梳理论文研究脉络
        """
        user_prompt = f"""
        **你必须严格遵守以下输出规则：**
        1. 仅输出Markdown源码，不要任何额外文本
        2. 绝对禁止使用代码块包裹(如```markdown或<code>)
        3. 必须包含以下四个h2标题(##)：
            ## 研究领域和方向
            ## 相关研究历程
            ## 学术贡献与定位
            ## 后续研究方向

        基于以下论文信息进行分析：
        **本篇论文标题**：{title}
        **本篇论文摘要**：{abstract}
        **本篇论文关键内容**：{key_content}
        **参考文献**：{references}

        分析要求：
        - 研究领域和方向
        - 相关研究历程：结合 该领域经典论文 以及 本篇论文相关参考文献 梳理 该研究领域的研究历程
        - 学术贡献与定位：对比说明本篇论文突破性贡献
        - 后续研究方向：提出2-4个可行方向

        **再次强调**：只输出Markdown源码！以###标题开头直接进入内容！
        """

        return self._simple_prompt(system_prompt, user_prompt)

    def safe_text(self, text: str):
        if not isinstance(text, str):
            return text

        # 转义反斜杠（避免 \beta 等）
        text = text.replace('\\', '\\\\')

        # 清理非法或残缺变量占位符（如 t-1）
        text = re.sub(r'\{[^}]*\}', '[变量]', text)  # 替换 f-string 风格的占位符

        # 去除非 ascii 控制字符（防止编码错误）
        text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F]', '', text)

        return text

    def safe_prompt_from_rag(self, query_text: str, result_text: str) -> str:
        prompt_template = """
        你是一名学术论文阅读助手，需要耐心而细致地解答用户的问题
        
        【用户的问题】
        {}
        
        【你需要做的】
        请结合以下RAG检索的内容，作为你的专业背景知识，回答用户的问题，提供一个学术权威又通俗易懂的解释：
        {}
        
        """
        return prompt_template.format(query_text, self.safe_text(result_text))

    # 【tips】
    # 如果RAG检索结果没有足够的有效信息，可以结合如下论文全文内容来进行回答:
    # {}

    def get_history_prompt(self, db: Session, paper_id: int, max_records: int = 5) -> str:
        chats = (
            db.query(ChatSession)
            .filter_by(paper_id=paper_id)
            .order_by(ChatSession.timestamp.asc())
            .limit(max_records)
            .all()
        )
        history_text = ""
        for chat in chats:
            history_text += f"User: {chat.question}\nAgent: {chat.answer}\n"
        return history_text

    def agentic_answer(self, question: str, paper: Paper, db: Session) -> Dict[str, Any]:
        """
        使用 Agent 来回答问题，返回统一格式：
        {
            "answer": "...",
            "diagram": { ... } 或 None
        }
        """
        self.setup_agent(paper)

        if not self.agent_executor:
            return {
                "answer": "Agent 未初始化，请稍后再试。",
                "diagram": None
            }

        history_prompt = self.get_history_prompt(db, paper.id, 10)
        full_prompt = f"下面是本篇论文相关的历史问答，供参考：\n{history_prompt}\n **下面是用户当前提出的问题，请据此输出：**：\n{question}"
        print(f"[AGENT_INVOKE] Invoking agent with question: '{full_prompt}'")

        response = self.agent_executor.invoke({"input": full_prompt})
        print(f"[AGENT_INVOKE] Get Raw response: '{response}'")

        output = response.get("output", "").strip()

        try:
            # 尝试解析 JSON 格式
            data = json.loads(output)

            # 容错处理：字段不全时补齐
            return {
                "answer": data.get("answer", "").strip(),
                "diagram": data.get("diagram", None)
            }

        except json.JSONDecodeError:
            # 非 JSON 格式：为普通文本，仍包装成统一结构
            print("[AGENT_INVOKE] Non-JSON plain text response.")
            return {
                "answer": output,
                "diagram": None
            }

    def setup_agent(self, paper: Paper):
        """
        根据指定的论文，配置一个具备工具调用能力的 Agent。
        """
        print(f"[AGENT] Setting up agent for paper_id: {paper.id}")

        if not self.load_rag(paper.id):
            print(f"[AGENT_WARNING] Could not load RAG for paper {paper.id}. RAG tool will be unavailable.")

        # 工具链
        tools = [self.rag_search_tool, self.generate_mindmap_mermaid, self.generate_flowchart_mermaid]

        paper_context = f"""
            # 论文核心信息
            ## 标题: {paper.title}
            ## 摘要: {paper.summary}
            ## 关键内容总结:
            {paper.key_content}
            ## 研究脉络：
            {paper.research_context}
            """

        # 这就是 Few-shot 示例。
        json_format_example = """{
        "diagram": {
            "type": "mermaid",
            "code": "mindmap\\n  root(论文关键内容)\\n    (研究问题)\\n      (研究目标)\\n    (主要方法)\\n    (实验设计)\\n    (主要贡献)",
            "title": "论文关键内容思维导图"
        },
        "answer": "这是为您生成的图表："
    }"""

        final_system_prompt_text = f"""
你是一名论文分析专家，具备自主规划和工具调用能力，能够帮助用户理解复杂学术论文内容。你拥有如下三种工具：

1. **rag_search_tool**：用于从论文全文及相关论文中查找具体细节、背景知识或答案片段。
2. **generate_mindmap_mermaid_tool**：生成思维导图。
3. **generate_flowchart_mermaid_tool**：生成流程图。

【核心回答策略】
- **遇到所有问题时，先用 rag_search_tool 检索背景知识。**
- **如果 rag_search_tool 没有返回有效内容（如“未找到”“无法回答”等），请直接结合论文的摘要、核心内容等原文信息（在后面会给出）自行总结回答，不要回答“无法回答”或“找不到”。**
- **如用户要求画思维导图或流程图，应基于rag_search_tool结果（如无有效内容则fallback原文核心信息）调用相应工具生成图表。**
- **你的最终输出**：严格按照JSON格式，直接以{{开头，不要用```json作为开头，json输出中应该包含以下字段：

{{
  "answer": "回答文本（可为空）",
  "diagram": {{
    "type": "mermaid",
    "title": "图标题",
    "code": "Mermaid代码"
  }} 或 null
}}


{paper_context}
"""

        prompt_messages = [
            SystemMessage(content=final_system_prompt_text),
            HumanMessage(content="请画一张XXX的流程图。"),
            AIMessage(content=json_format_example),
            ("user", "{input}"),
            ("placeholder", "{agent_scratchpad}")
        ]

        prompt_template = ChatPromptTemplate.from_messages(prompt_messages)
        agent = create_tool_calling_agent(self.llm, tools, prompt_template)

        self.agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)
        print(f"[AGENT] Agent for paper_id: {paper.id} is ready.")

    def _get_rag_search_tool(self):
        @tool
        def rag_search(query: str) -> str:
            """
            当你需要回答关于论文具体细节的问题时，使用此工具。
            它会从论文全文中搜索并找到最相关的答案。
            输入应该是用户的原始问题或你需要查找的具体主题。
            """
            print(f"[AGENT_TOOL] Calling RAG Search Tool with query: '{query}'")
            if not self.qa_chain:
                return "RAG 知识库未加载。无法回答问题。"
            try:
                result = self.qa_chain.invoke({"query": query})
                print(f"[AGENT_TOOL] RAG Search Tool Result: '{result}'")
                # prompt = self.safe_prompt_from_rag(query, result["result"])
                # print(f"[AGENT_TOOL] Final Prompt: '{prompt}']")
                # res = self.llm.invoke(prompt).content  # 直接调用 llm
                if isinstance(result, str):
                    return result
                elif isinstance(result, list):
                    return "\n".join([str(x) for x in result])
                else:
                    return str(result)
            except Exception as e:
                return f"RAG 搜索时出错: {str(e)}"

        return Tool.from_function(
            func=rag_search,
            name="rag_search_tool",
            description="从论文全文中搜索并回答具体问题，输入应为用户的自然语言问题。"
        )

    def _get_generate_mindmap_mermaid_tool(self):
        @tool
        def generate_mindmap_mermaid(topic: str, content: Optional[str] = None) -> str:
            """
            当用户要求生成思维导图（mindmap）时使用此工具。
            'topic' 参数是思维导图的中心主题。
            'content' 用于生成导图的详细文本。
            """
            print(f"[AGENT_TOOL] Calling Mindmap Tool for topic: '{topic}'")

            if content is None:
                print(f"Mindmap content not provided for topic '{topic}'. Performing RAG search.")
                content = self.rag_search_tool.invoke(topic)  # 直接调用另一个工具
                if (content is None) or ("未能找到" in content) or ("无法回答" in content):
                    return f"无法为主题 '{topic}' 生成思维导图，因为在论文中找不到相关内容。"

            prompt = f"""
            你是一个数据可视化专家。请根据以下内容，并且精炼概括出关键内容，控制文本长度，创建一个 Mermaid.js 格式的思维导图。
            思维导图应以 '{topic}' 为中心主题，并清晰地展示信息的层级结构。

            内容:
            ---
            {content}
            ---

            请严格按照 Mermaid mindmap 语法输出，不要包含任何其他解释或注释，直接给出代码。
            """
            if not self.llm:
                return "LLM 未初始化。"
            res = self.llm.invoke(prompt).content
            if isinstance(res, str):
                return res
            elif isinstance(res, list):
                return "\n".join([str(x) for x in res])
            else:
                return str(res)

        return Tool.from_function(
            func=generate_mindmap_mermaid,
            name="generate_mindmap_mermaid_tool",
            description="当用户要求生成思维导图（mindmap）时使用此工具。"
        )

    def _get_generate_flowchart_mermaid_tool(self):
        @tool
        def generate_flowchart_mermaid(topic: str, content: Optional[str] = None) -> str:
            """
            当用户要求生成流程图（flowchart）来描述流程或步骤时使用此工具。
            'topic' 参数是流程图的标题。
            'content' 描述流程步骤的详细文本，不允许置空
            """
            print(f"[AGENT_TOOL] Calling Flowchart Tool for topic: '{topic}'")

            if content is None:
                print(f"Flowchart content not provided for topic '{topic}'. Performing RAG search.")
                content = self.rag_search_tool.invoke(topic)  # 直接调用另一个工具
                if (content is None) or ("未能找到" in content) or ("无法回答" in content):
                    return f"无法为主题 '{topic}' 生成流程图，因为在论文中找不到相关内容。"

            prompt = f"""
            你是一个流程图绘制专家。请根据以下描述的流程，并且精炼概括出关键内容，控制文本长度，创建一个 Mermaid.js 格式的自顶向下（TD）流程图。
            流程图标题应为 '{topic}'。

            流程描述内容:
            ---
            {content}
            ---

            请严格按照 Mermaid graph TD 语法输出，不要包含任何其他解释或注释，直接给出代码。
            """
            if not self.llm:
                return "LLM 未初始化。"
            res = self.llm.invoke(prompt).content
            if isinstance(res, str):
                return res
            elif isinstance(res, list):
                return "\n".join([str(x) for x in res])
            else:
                return str(res)

        return Tool.from_function(
            func=generate_flowchart_mermaid,
            name="generate_flowchart_mermaid_tool",
            description="当用户要求生成流程图（flowchart）时使用此工具。"
        )

    # --- 新增：带重试机制的API请求器 ---
    # def _make_s2_api_request(self, url: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    #     max_retries = 3
    #     initial_delay = 5  # 初始等待5秒
    #     for attempt in range(max_retries):
    #         try:
    #             response = requests.get(
    #                 url,
    #                 params=params,
    #                 headers={},  # 强制使用免费API
    #                 timeout=15  # 设置请求超时
    #             )
    #             response.raise_for_status()  # 对4xx/5xx错误抛出HTTPError
    #             return response.json()
    #         except requests.RequestException as e:
    #             if e.response is not None and e.response.status_code == 429:
    #                 wait_time = initial_delay * (2 ** attempt)  # 指数增加等待时间
    #                 print(
    #                     f"[S2_API_HANDLER] Rate limit exceeded (429). Retrying in {wait_time} seconds... (Attempt {attempt + 1}/{max_retries})")
    #                 time.sleep(wait_time)
    #             else:
    #                 print(f"[S2_API_HANDLER] API request failed at {url}. Error: {e}")
    #                 if e.response:
    #                     print(f"[S2_API_HANDLER] Response content: {e.response.text}")
    #                 return None
    #     print(f"[S2_API_HANDLER] Failed to get a successful response from {url} after {max_retries} attempts.")
    #     return None
    #
    # def _search_paper(self, state: S2State) -> S2State:
    #     title = state['title']
    #     print(f"[S2_SEARCH] Searching for paper with title: {title}")
    #     url = f"{self.s2_api_base}/paper/search"
    #     params = {"query": title, "fields": "title", "limit": 1}
    #     data = self._make_s2_api_request(url, params)
    #     if data and data.get('total', 0) > 0 and data.get('data'):
    #         s2_id = data['data'][0]['paperId']
    #         found_title = data['data'][0]['title']
    #         print(f"[S2_SEARCH] Found a match. S2 ID: {s2_id}, Title: {found_title}")
    #         return {**state, "s2_id": s2_id}
    #     else:
    #         print(f"[S2_SEARCH] Paper not found on Semantic Scholar for title: '{title}'")
    #         return {**state, "s2_id": None}
    #
    # def _fetch_references_and_citations(self, state: S2State) -> S2State:
    #     s2_id = state['s2_id']
    #     fields = "title,publicationDate,citationCount"
    #
    #     def fetch_data(endpoint: str) -> List[Dict]:
    #         url = f"{self.s2_api_base}/paper/{s2_id}/{endpoint}"
    #         params = {"fields": fields, "limit": 10}  # 获取前10条
    #         print(f"[S2_FETCH] Calling API: {url}")
    #         response_data = self._make_s2_api_request(url, params)
    #         if response_data:
    #             data = response_data.get('data', [])
    #             print(f"[S2_FETCH] Successfully fetched {len(data)} items from '{endpoint}'.")
    #             return data
    #         return []  # 如果请求失败，返回空列表
    #
    #     references_data = fetch_data("references")
    #     citations_data = fetch_data("citations")
    #     references = [item['citedPaper'] for item in references_data if item.get('citedPaper')]
    #     citations = [item['citingPaper'] for item in citations_data if item.get('citingPaper')]
    #     print(f"[S2_FETCH] Extracted {len(references)} references and {len(citations)} citations.")
    #     return {**state, "references": references, "citations": citations}
    #
    # def _compile_results(self, state: S2State) -> S2State:
    #     references = state.get("references", [])
    #     citations = state.get("citations", [])
    #     print(f"[S2_COMPILE] Compiling final result with {len(references)} references and {len(citations)} citations.")
    #     result = {
    #         "references": references,
    #         "citations": citations
    #     }
    #     return {**state, "final_result": json.dumps(result, ensure_ascii=False)}
    #
    # def _decide_to_fetch(self, state: S2State) -> str:
    #     if state.get('s2_id'):
    #         print("[S2_DECIDE] S2 ID found. Proceeding to fetch data.")
    #         return "fetch"
    #     else:
    #         print("[S2_DECIDE] S2 ID not found. Skipping fetch.")
    #         return "not_found"
    #
    # def _handle_not_found(self, state: S2State) -> S2State:
    #     print("[S2_NOT_FOUND] Finalizing process as paper was not found.")
    #     return {**state, "final_result": "在Semantic Scholar API无法查询到该论文"}
    #
    # def fetch_related_papers(self, title: str) -> Dict[str, Any]:
    #     workflow = StateGraph(S2State)
    #     workflow.add_node("search", self._search_paper)
    #     workflow.add_node("fetch", self._fetch_references_and_citations)
    #     workflow.add_node("compile", self._compile_results)
    #     workflow.add_node("not_found", self._handle_not_found)
    #     workflow.set_entry_point("search")
    #     workflow.add_conditional_edges(
    #         "search",
    #         self._decide_to_fetch,
    #         {"fetch": "fetch", "not_found": "not_found"}
    #     )
    #     workflow.add_edge("fetch", "compile")
    #     workflow.add_edge("compile", END)
    #     workflow.add_edge("not_found", END)
    #     graph = workflow.compile()
    #     initial_state = {"title": title, "s2_id": None, "references": [], "citations": [], "final_result": {}}
    #     print(f"[S2_WORKFLOW] Starting related papers workflow for title: '{title}'")
    #     final_state = graph.invoke(initial_state)
    #     print(f"[S2_WORKFLOW] Workflow completed.")
    #     return {
    #         "s2_id": final_state.get('s2_id'),
    #         "related_papers_json": final_state.get('final_result')
    #     }

    # --- 新增：上下文感知的高质量交互式翻译方法 ---

    def interactive_translate_streaming(self, selected_text: str, key_content: str):
        """
        流式翻译：逐步返回翻译结果
        """
        # 使用 LangChain 或其他 API 进行流式翻译
        print(f"[TRANSLATE] Streaming translation for text: '{selected_text[:50]}...'")
        translation_prompt = f"""
        你是一位精通简体中文的专业翻译，尤其擅长将专业学术论文翻译成浅显易懂的科普文章。请你帮我将以下英文段落翻译成中文，风格与中文科普读物相似。

        这是整篇论文的背景内容，有助于你理解上下文和专业术语：
        <full_context>
        {key_content}
        </full_context>

        以下是需要翻译的英文段落：
        {selected_text}

        翻译基本规则：
    - 翻译时要准确传达原文的事实和背景。
    - 即使意译也要保留原始段落格式，以及保留术语，例如 FLAC，JPEG 等。保留公司缩写，例如 Microsoft, Amazon, OpenAI 等。
    - 人名不翻译
    - 同时要保留引用的论文，例如 [20] 这样的引用。
    - 对于 Figure 和 Table，翻译的同时保留原有格式，例如：“Figure 1: ”翻译为“图-1：”，“Table 1: ”翻译为：“表-1：”。
    - 全角括号换成半角括号，并在左括号前面加半角空格，右括号后面加半角空格。
    - 需要输出为 Markdown 格式，**仅**输出 markdown 源码，不要用 <code> 或 ```markdown 代码块 包裹
    - 在翻译专业术语时，第一次出现时要在括号里面写上英文原文，例如：“生成式 AI (Generative AI)”，之后就可以只写中文了。
        """

        messages = [HumanMessage(content=translation_prompt)]
        # 关键：用stream(messages)流式输出
        for chunk in self.llm.stream(messages):
            content = getattr(chunk, "content", None)
            if content:
                yield content

    def explain_term_streaming(self, term: str, key_content: str):
        """
        流式关键词解释：逐步返回解释结果
        """
        print(f"[EXPLAIN] Streaming explanation for term: '{term}'")
        explanation_prompt = f"""
    你是一位擅长科普和学术解读的专业知识讲解者。请结合以下论文的背景和内容，用简明、通俗、准确的语言解释给定术语，适合非专业人士理解。

    论文内容（供你参考）：
    <full_context>
    {key_content}
    </full_context>

    需要解释的术语：
    {term}

    你的输出要求：
    - 必须聚焦于术语本身，参考论文上下文进行通俗解释。
    - 不要生成列表，只解释本术语。
    - 格式为 Markdown 段落。
    - 不要引用原文，不要附加“以下是解释”等废话，直接输出解释内容。
    """

        messages = [HumanMessage(content=explanation_prompt)]
        # 关键：流式输出LLM结果
        for chunk in self.llm.stream(messages):  # 这里沿用你的流式LLM实例
            content = getattr(chunk, "content", None)
            if content:
                yield content

    def understand_image_stream(self, image_url: str, context: str, caption: str):
        if not self.zhipu_client:
            yield "Error: Zhipu AI client is not initialized. Please set the ZHIPU_API_KEY environment variable."
            return

        print(f"[ZHIPU_V] Analyzing image using GLM-4V. URL: {image_url}")
        # print(f"[ZHIPU_V] Context: {context}")
        print(f"[ZHIPU_V] Caption: {caption}")

        prompt = f"""
    你是一个专业、耐心的论文阅读助手
    用户希望你帮忙分析一张论文里的**图片（非表格、非公式）**。

    {'- **图注**: "' + caption + '"' if caption else ''}
    {'- **论文上下文**: "' + context + '"' if context else ''}
    - **图片链接**: 已通过 URL 提供
    
    具体来说，你可能需要：
    识别图片类型（如显微照片/流程图/数据可视化）及其在文中的核心功能  
    解码关键元素（坐标轴/图例/标注的学术含义，理解数据趋势或对比关系等）
    关联上下文（如何支撑作者论点，或者和作者的论述内容有何关系）

    **在这个基础上，向用户详细解析这张图片，注意语言流畅，不要定式化分点罗列**
    **输出一定要专业且通俗易懂、充分结合图片标注和文章内容来理解**
    请输出为 Markdown 格式，**仅**输出 markdown 源码，不要用 <code> 或 ```markdown 代码块 包裹！
    """
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_url}},
                    {"type": "text", "text": prompt}
                ]
            }
        ]
        try:
            response = self.zhipu_client.chat.completions.create(
                model="glm-4v-plus",
                messages=messages,
                stream=True,
            )
            for chunk in response:
                if chunk.choices[0].delta and chunk.choices[0].delta.content:
                    token = chunk.choices[0].delta.content
                    yield token
        except Exception as e:
            yield f"Zhipu API Error: {str(e)}"

    def understand_table_stream(self, image_url: str, context: str, caption: str):
        if not self.zhipu_client:
            yield "Error: Zhipu AI client is not initialized. Please set the ZHIPU_API_KEY environment variable."
            return

        prompt = f"""
    你是一个专业、耐心的论文阅读助手
    用户希望你帮忙分析一张论文里的**表格**图片。

    {'- **表格标注/图注**: "' + caption + '"' if caption else ''}
    {'- **论文上下文**: "' + context + '"' if context else ''}
    - **表格图片已通过 URL 提供**

    具体来说，你可能需要：
    识别表格类型、主题及其在文中的核心功能定位
    解码关键元素（每一列/行的含义和单位，理解数据关系和核心数据等）
    关联上下文（理解表格传达的主旨观点，如何支撑作者论点，或者和作者的论述内容有何关系）

    **在这个基础上，向用户详细解析这张表格，注意语言流畅，不要定式化分点罗列（不过如果需要也可以按你自己的逻辑格式化输出）**
    **输出一定要专业且通俗易懂、充分结合图片标注和文章内容来理解**
    请输出为 Markdown 格式，**仅**输出 markdown 源码，不要用 <code> 或 ```markdown 代码块 包裹！
    """
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_url}},
                    {"type": "text", "text": prompt}
                ]
            }
        ]
        try:
            response = self.zhipu_client.chat.completions.create(
                model="glm-4v-plus",
                messages=messages,
                stream=True,
            )
            for chunk in response:
                if chunk.choices[0].delta and chunk.choices[0].delta.content:
                    token = chunk.choices[0].delta.content
                    yield token
        except Exception as e:
            yield f"Zhipu API Error: {str(e)}"

    def understand_formula_stream(self, image_url: str, context: str, caption: str):
        if not self.zhipu_client:
            yield "Error: Zhipu AI client is not initialized. Please set the ZHIPU_API_KEY environment variable."
            return

        prompt = f"""
    你是一个专业、耐心的论文阅读助手
    用户希望你帮忙分析一张论文里的**数学公式**（以图片形式提供）。
    
    【请按照下列格式输出】
    1. 整段回答用 Markdown 排版，**仅**输出原始Markdown源码，不要用任何代码块如<code>或```markdown包裹
    2. **如果回答中包含公式/符号，公式/符号必须使用LaTeX格式输出**：
       - **整段公式：用 $$...$$ 包裹（块级模式）**
       - **小段变量/符号/公式：用 $...$ 包裹（行内模式）**
    
    【具体要求】
    **具体来说，你需要按照下面的结构思考和输出分析**：
    识别公式结构及符号定义（可以先对公式中的每个变量和符号逐一解释）
    理解公式的数学意义和内涵
    理解公式在论文中的定位（是本文核心方法所涉及的公式，或是参考的公式等）
    关联上下文（理解公式在论文中的作用/推理/用途，甚至考虑其实际应用场景等）
    
    【参考资料】
    {'- **公式注解**: "' + caption + '"' if caption else ''}
    {'- **论文上下文**: "' + context + '"' if context else ''}
    - **公式图片通过 URL 提供**
    
    注意输出格式，Markdown+LaTeX（latex格式的公式/数学符号**一定要**用 $$...$$ 或 $...$ 包裹，**一定不要**用 \( \) 包裹，不然会渲染失败！）
    
    【错误输出格式示例】：
    Q = W_Q^{{(i)}} \cdot \\varphi_i(z_t), \quad K = W_K^{{(i)}} \cdot \\tau_\\theta(y), \quad V = W_V^{{(i)}} \cdot \\tau_\\theta(y).
    - \( Q \): 输入特征或查询向量。
    - \( W_Q^{{(i)}} \): 第 \( i \) 层的查询权重矩阵。
    
    【正确输出格式示例（但是内容不要按这个来）】：
    $$Q = W_Q^{{(i)}} \cdot \\varphi_i(z_t), \quad K = W_K^{{(i)}} \cdot \\tau_\\theta(y), \quad V = W_V^{{(i)}} \cdot \\tau_\\theta(y).$$
    - $ Q $: 输入特征或查询向量。
    - $ W_Q^{{(i)}} $: 第 $ i $ 层的查询权重矩阵。
    """
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_url}},
                    {"type": "text", "text": prompt}
                ]
            }
        ]
        try:
            response = self.zhipu_client.chat.completions.create(
                model="glm-4v-plus",
                messages=messages,
                stream=True,
            )
            for chunk in response:
                if chunk.choices[0].delta and chunk.choices[0].delta.content:
                    token = chunk.choices[0].delta.content
                    print(token, end='')
                    yield token
        except Exception as e:
            yield f"Zhipu API Error: {str(e)}"
