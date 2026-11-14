import os
import uuid
import json
import threading
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends, Request, BackgroundTasks, Query
from fastapi.responses import StreamingResponse, JSONResponse
from sqlalchemy.orm import Session

from models.db import get_db_session
from models.paper import Paper, ChatSession
from services.pdf_parser import PDFParser
from services.ai_service import AIService

from pydantic import BaseModel
from schemas.paper_schemas import *
from schemas.chat_schemas import *

from configs import DATA_DIR
from services.tools import *

from services.tools import _upload_to_oss

router = APIRouter(prefix="/papers", tags=["papers"])

UPLOAD_FOLDER = os.path.join(DATA_DIR, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


@router.get("/search_arxiv")
async def search_arxiv_api(
        title: str = Query(..., description="要搜索的论文标题"),
        max_results: int = Query(5, description="最多返回多少条结果")
):
    """
    按标题搜索arXiv论文（返回多条）。
    """
    if not title or not title.strip():
        raise HTTPException(status_code=400, detail="title参数不能为空")

    results = search_arxiv(title, timeout=5, max_results=max_results)
    return JSONResponse(content=results, status_code=200)  # 直接返回数组


# ========== 上传论文 ==========
@router.post("/upload")
async def upload_paper(
        file: UploadFile = File(...),
        user_id: int = Form(0),
        db: Session = Depends(get_db_session),
):
    print(f"[UPLOAD] 用户 user_id={user_id} 上传文件 filename={file.filename}")
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Invalid file type")

    filename = f"{uuid.uuid4()}_{file.filename}"
    file_path = os.path.join(UPLOAD_FOLDER, filename)

    with open(file_path, "wb") as f:
        f.write(await file.read())

    paper = Paper(
        filename=filename,
        original_filename=file.filename,
        file_path=file_path,
        user_id=user_id,
        processing_status="uploaded"
    )
    db.add(paper)
    db.commit()
    db.refresh(paper)

    print(f"[UPLOAD] 文件已保存到 file_path={paper.file_path}, paper_id={paper.id}")

    return {
        "message": "File uploaded successfully",
        "paper_id": paper.id,
        "filename": paper.original_filename
    }


# ========== 异步分析论文 ==========
@router.post("/{paper_id}/analyze/async")
async def start_async_analysis(paper_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db_session)):
    """启动异步分析任务"""
    print(f"[ASYNC_ANALYZE] 启动异步分析 paper_id={paper_id}")
    paper = db.query(Paper).get(paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    if paper.processing_status == 'processing':
        raise HTTPException(status_code=400, detail="Paper is already being processed")

    # 立即设置为处理中状态
    paper.processing_status = 'processing'
    db.commit()

    # 添加后台任务
    background_tasks.add_task(analyze_paper_background, paper_id)

    return {
        "message": "Analysis started in background",
        "paper_id": paper_id,
        "status": "processing"
    }


# ========== 后台分析函数 ==========
def analyze_paper_background(paper_id: int):
    """后台执行分析任务"""
    print(f"[BACKGROUND] 开始后台分析 paper_id={paper_id}")

    # 创建新的数据库会话
    from models.db import SessionLocal
    db = SessionLocal()

    try:
        paper = db.query(Paper).get(paper_id)
        if not paper:
            print(f"[BACKGROUND] Paper not found: {paper_id}")
            return

        # 执行分析逻辑（复制自原有的analyze_paper函数）
        parser = PDFParser()
        parsed_data = parser.parse_pdf(paper.id, paper.file_path)
        print(f"[BACKGROUND] PDF 解析完毕")

        ai_service = AIService()

        paper.title = parsed_data.get('title', paper.original_filename)
        db.commit()
        print(f"[BACKGROUND] 已保存 paper.title: {paper.title}")

        abstract = None
        if parsed_data.get('title', ''):
            this_paper = next(iter(search_arxiv(paper.title, timeout=5)), None)
            print("[arxiv_paper]", this_paper)
            if this_paper and this_paper['published']:
                paper.published_time = this_paper['published'][:10]
            else:
                paper.published_time = ""
            db.commit()
            print(f"[BACKGROUND] 已保存 paper.published_time: {paper.published_time}")

            if this_paper and this_paper['link']:
                paper.arxiv_url = this_paper['link']
            else:
                paper.arxiv_url = ""
            db.commit()
            print(f"[BACKGROUND] 已保存 paper.arxiv_url: {paper.arxiv_url}")

            if this_paper and this_paper['authors']:
                paper.authors = ', '.join(this_paper['authors'])
            else:
                paper.authors = ', '.join(parsed_data.get('authors', []))
            db.commit()
            print(f"[BACKGROUND] 已保存 paper.authors: {paper.authors}")

            if this_paper and this_paper['summary']:
                abstract = this_paper['summary']
            else:
                abstract = parsed_data.get('abstract', '')

        if abstract:
            paper.abstract = ai_service.generate_abstract(abstract)
            print(f"[BACKGROUND] 已翻译并保存：摘要 paper.abstract: {paper.abstract[:100]}...")
        else:
            paper.abstract = f"未提取到有效摘要"
            print(f"[BACKGROUND] 未提取到有效摘要")
        db.commit()

        if paper.abstract and paper.title:
            paper.summary = ai_service.generate_single_sentence_summary(paper.abstract, paper.title)
            print(f"[BACKGROUND] 已生成并保存：一句话概括 paper.summary")
        else:
            paper.summary = f"这是一篇关于{paper.title}的学术论文。"
        db.commit()

        key_sections = extract_core_sections(parsed_data.get('sections', []))

        if key_sections:
            paper.key_content = ai_service.extract_key_content(key_sections, paper.title)
            print(f"[BACKGROUND] 已生成并保存 paper.key_content")
        else:
            paper.key_content = "未提取到有效的 key_sections"
        db.commit()

        # if paper.abstract:
        #     paper.translation = ai_service.translate_text(paper.abstract)
        #     print(f"[BACKGROUND] 已完成摘要翻译（目前是demo版本）")
        # else:
        #     paper.translation = "未提取到有效的摘要内容"
        # db.commit()
        # paper.translation = "弃用"
        # db.commit()

        full_text = parsed_data.get('full_text', '')
        paper.full_text = full_text
        db.commit()
        print(f"[BACKGROUND] 已保存：全文 paper.full_text")

        if full_text:
            terms_list = ai_service.extract_terminology_list(full_text[:5000])
            paper.terminology = json.dumps(terms_list, ensure_ascii=False)
            print(f"[BACKGROUND] 已生成并保存：关键词列表 paper.terminology = {paper.terminology}")
        else:
            paper.terminology = paper.terminology = json.dumps([], ensure_ascii=False)
            print(f"[BACKGROUND] 未提取到 full_text 文本内容, 生成关键词失败。")
        db.commit()

        reference_list = parsed_data.get('references', [])
        paper.research_context = ai_service.analyze_research_context(
            paper.title, paper.abstract, paper.key_content, paper.related_papers_json
        )
        db.commit()
        print(f"[BACKGROUND] 已生成并保存：研究脉络 paper.research_context")

        related_papers = []
        for ref in reference_list[:20]:
            title = extract_reference_title(ref)
            arxiv_paper = next(iter(search_arxiv(title, timeout=1.0)), None)
            if arxiv_paper:
                related_papers.append(arxiv_paper)
        paper.related_papers_json = json.dumps(related_papers, ensure_ascii=False, indent=2)
        db.commit()
        print(f"[BACKGROUND] 已生成并保存：参考文献 paper.related_papers — 搜索到有效参考文献共 {len(related_papers)} 篇")

        # # --- 新增：调用Semantic Scholar服务 ---
        # print(f"[BACKGROUND] Fetching related papers from Semantic Scholar for title: {paper.title}")
        # related_data = ai_service.fetch_related_papers(paper.title)
        # paper.s2_id = related_data.get('s2_id')
        # paper.related_papers_json = related_data.get('related_papers_json')
        # db.commit()
        # print(f"[BACKGROUND] Semantic Scholar data fetched. S2 ID: {paper.s2_id}")

        # 构建增强内容
        rag_chunks = build_rag_chunks(related_papers)

        print(f"[BACKGROUND] RAG chunks built: {len(rag_chunks)} items")
        print(f"[BACKGROUND] RAG chunks[0]: {rag_chunks[0] if rag_chunks else 'No chunks available'}")

        # 拼接为一个整体string
        augmented_full_text = "[本篇论文（默认的论文）OUR ARTICLE]\n" + full_text + "\n\n" + "\n\n".join(rag_chunks)
        print(f"[BACKGROUND] augmented_full_text length: {len(augmented_full_text)}")

        if augmented_full_text:
            ai_service.setup_rag(augmented_full_text, paper.id)
            print(f"[BACKGROUND] RAG setup completed")

        paper.processing_status = 'completed'
        db.commit()

        print(f"[BACKGROUND] Paper {paper_id} analysis completed")

    except Exception as e:
        print(f"[BACKGROUND] Analysis failed for paper {paper_id}: {str(e)}")
        paper = db.query(Paper).get(paper_id)
        if paper:
            paper.processing_status = 'failed'
            db.commit()
    finally:
        db.close()


# ========== 查询分析状态 ==========
from datetime import datetime

@router.get("/{paper_id}/status")
async def get_analysis_status(paper_id: int, db: Session = Depends(get_db_session)):
    paper = db.query(Paper).get(paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    TOTAL_SIM_TIME = 120  # 总模拟时长，单位秒
    PHASES = [
        {"name": "pdf_parsing", "weight": 0.35, "desc": "正在解析PDF...", "check": lambda p: bool(p.title)},
        {"name": "title", "weight": 0.02, "desc": "提取标题...", "check": lambda p: bool(p.title)},
        {"name": "authors", "weight": 0.03, "desc": "提取作者...", "check": lambda p: bool(p.authors)},
        {"name": "summary", "weight": 0.05, "desc": "生成概述...", "check": lambda p: bool(p.summary)},
        {"name": "abstract", "weight": 0.10, "desc": "理解摘要...", "check": lambda p: bool(p.abstract)},
        {"name": "key_content", "weight": 0.10, "desc": "分析关键内容...", "check": lambda p: bool(p.key_content)},
        {"name": "terminology", "weight": 0.05, "desc": "分析关键术语...", "check": lambda p: bool(p.terminology)},
        {"name": "research_context", "weight": 0.10, "desc": "分析研究脉络...",
         "check": lambda p: bool(p.research_context)},
        {"name": "rag", "weight": 0.2, "desc": "正在构建RAG问答系统...",
         "check": lambda p: p.processing_status == "completed"},
    ]

    # 计算每阶段的max_time
    for phase in PHASES:
        phase["max_time"] = TOTAL_SIM_TIME * phase["weight"]

    # 分析开始时间，用 upload_time 或分析真正启动时的时间字段
    start_time = paper.upload_time if hasattr(paper, "upload_time") else datetime.now()
    now = datetime.now()
    elapsed = (now - start_time).total_seconds()

    progress = 0.0
    acc_time = 0
    progress_details = []

    for phase in PHASES:
        # 检查本阶段是否已完成（用实际字段判断）
        if phase["check"](paper):
            progress += phase["weight"] * 100
            acc_time += phase["max_time"]
            progress_details.append(phase["desc"].replace("...", "完成"))
            continue

        # 还未完成的阶段，平滑推进
        local_elapsed = max(0, elapsed - acc_time)
        percent = min(1.0, local_elapsed / phase["max_time"])
        progress += phase["weight"] * percent * 100
        # 本阶段描述
        progress_details.append(phase["desc"])
        break  # 只推进到第一个未完成的阶段

    # 如果彻底完成
    if paper.processing_status == "completed":
        progress = 100
        progress_details = ["分析完成"]

    # 保证不会超过99%，只有最后一刻才100%
    progress = int(min(progress, 99)) if paper.processing_status != "completed" else 100

    return {
        "paper_id": paper_id,
        "status": paper.processing_status,
        "progress": progress,
        "progress_details": progress_details,
        "title": paper.title,
        "authors": paper.authors
    }


# ========== 获取单篇论文 ==========
@router.get("/{paper_id}", response_model=PaperResponse)
async def get_paper(paper_id: int, db: Session = Depends(get_db_session)):
    paper = db.query(Paper).get(paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    return PaperResponse.model_validate(paper)


# ========== 获取论文列表 ==========
@router.get("/", response_model=List[PaperResponse])
async def get_papers(user_id: int = 0, db: Session = Depends(get_db_session)):
    papers = db.query(Paper).filter_by(user_id=user_id).order_by(Paper.upload_time.desc()).all()
    return [PaperResponse.model_validate(p) for p in papers]


# ========== 聊天问答 ==========
@router.post("/{paper_id}/chat", response_model=ChatResponse)
async def chat_with_paper(paper_id: int, request_data: QuestionRequest, db: Session = Depends(get_db_session)):
    print(f"[CHAT] user_id={request_data.user_id} asking: question='{request_data.question}' for paper_id={paper_id}")
    paper = db.query(Paper).get(paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    ai_service = AIService()
    try:
        result_dict = ai_service.agentic_answer(request_data.question, paper, db)
        print(f"[CHAT] Agent result received: {result_dict}")
        print(f"[CHAT] LLM answer completed")

        # --- 将结果字典序列化为 JSON 字符串存入数据库 ---
        # 这样前端就能收到完整的结构化信息
        answer_content = json.dumps(result_dict, ensure_ascii=False)

        chat_session = ChatSession(
            paper_id=paper_id,
            user_id=request_data.user_id,
            question=request_data.question,
            answer=answer_content
        )
        db.add(chat_session)
        db.commit()
        db.refresh(chat_session)

        print(f"[CHAT] Saved chat session id={chat_session.id}")

        return ChatResponse(
            id=chat_session.id,
            paper_id=paper_id,
            user_id=request_data.user_id,
            question=request_data.question,
            # answer=result['answer'],
            answer=answer_content,
            timestamp=chat_session.timestamp,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat failed: {str(e)}")


# ========== 聊天历史记录 ==========
@router.get("/{paper_id}/chat/history", response_model=List[ChatResponse])
async def get_chat_history(paper_id: int, user_id: int = 0, db: Session = Depends(get_db_session)):
    chats = db.query(ChatSession).filter_by(paper_id=paper_id, user_id=user_id).order_by(
        ChatSession.timestamp.asc()).all()
    return [ChatResponse.model_validate(chat) for chat in chats]


# ========== 删除聊天历史记录 ==========
@router.delete("/{paper_id}/chat/history")
async def delete_chat_history(paper_id: int, user_id: int = 0, db: Session = Depends(get_db_session)):
    """删除特定论文的聊天历史记录"""
    try:
        # 检查论文是否存在
        paper = db.query(Paper).get(paper_id)
        if not paper:
            raise HTTPException(status_code=404, detail="Paper not found")

        # 删除该论文的所有聊天记录
        deleted_count = db.query(ChatSession).filter_by(paper_id=paper_id, user_id=user_id).delete()
        db.commit()

        print(f"[CHAT] Deleted {deleted_count} chat sessions for paper_id={paper_id}, user_id={user_id}")
        return {"message": f"Successfully deleted {deleted_count} chat records", "deleted_count": deleted_count}

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete chat history: {str(e)}")


# 后端流式翻译 API 路由
@router.post("/{paper_id}/interactive-translate")
async def interactive_streaming_translate_selection(
        paper_id: int,
        request_data: InteractiveTranslateRequest,
        db: Session = Depends(get_db_session)
):
    paper = db.query(Paper).get(paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    key_content = paper.key_content

    if not key_content:
        raise HTTPException(status_code=404, detail="无法获取已存储的论文全文以提供翻译上下文。请确认论文已成功分析。")

    try:
        ai_service = AIService()

        # 定义生成翻译内容的流式函数
        def generate_translation():
            selected_text = request_data.text
            for part in ai_service.interactive_translate_streaming(selected_text, key_content):
                yield f"data: {json.dumps({'content': part})}\n\n"

        return StreamingResponse(generate_translation(), media_type="text/event-stream")

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Translation failed: {str(e)}")


@router.post("/{paper_id}/explain-term")
async def interactive_streaming_explain_term(
        paper_id: int,
        request_data: ExplainTermRequest,  # 包含 term(str)
        db: Session = Depends(get_db_session)
):
    paper = db.query(Paper).get(paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    key_content = paper.key_content
    if not key_content:
        raise HTTPException(status_code=404, detail="无法获取已存储的论文关键内容。")

    try:
        ai_service = AIService()
        term = request_data.term

        def generate_explanation():
            for part in ai_service.explain_term_streaming(term, key_content):
                yield f"data: {json.dumps({'content': part})}\n\n"

        return StreamingResponse(generate_explanation(), media_type="text/event-stream")

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Explanation failed: {str(e)}")


# ========== 修改后的图像处理路由 ==========
@router.post("/{paper_id}/understand-image")
async def understand_image(
        paper_id: int,
        request_data: ImageUnderstandRequest,
        db: Session = Depends(get_db_session)
):
    paper = db.query(Paper).get(paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    # 将图像上传到阿里云oss
    image_url = _upload_to_oss(request_data.image_data)

    if not image_url:
        raise HTTPException(status_code=500, detail="Failed to upload image to cloud storage.")

    content_type = request_data.type
    context_text = paper.key_content
    caption_text = request_data.caption_text

    # 流式输出
    def stream_image_analysis():
        ai_service = AIService()
        try:
            if content_type == "image":
                generator = ai_service.understand_image_stream(
                    image_url=image_url,
                    context=context_text,
                    caption=caption_text
                )
            elif content_type == "table":
                generator = ai_service.understand_table_stream(
                    image_url=image_url,
                    context=context_text,
                    caption=caption_text
                )
            elif content_type == "formula":
                generator = ai_service.understand_formula_stream(
                    image_url=image_url,
                    context=context_text,
                    caption=caption_text
                )
            else:
                yield f"data: {json.dumps({'error': '未知的分析类型'}, ensure_ascii=False)}\n\n"
                return

            for chunk in generator:
                yield f"data: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"
        except Exception as e:
            error_content = {"error": f"An error occurred during streaming: {str(e)}"}
            yield f"data: {json.dumps(error_content, ensure_ascii=False)}\n\n"

    # 返回流式响应
    return StreamingResponse(stream_image_analysis())
