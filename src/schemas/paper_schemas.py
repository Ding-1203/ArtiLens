from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime

class PaperResponse(BaseModel):
    id: int
    filename: str
    original_filename: str
    file_path: str
    upload_time: datetime
    user_id: int

    title: Optional[str]
    authors: Optional[str]
    published_time: Optional[str]
    arxiv_url: Optional[str]
    abstract: Optional[str]
    summary: Optional[str]
    key_content: Optional[str]
    terminology: Optional[str]
    research_context: Optional[str]
    processing_status: Optional[str]
    s2_id: Optional[str]
    related_papers_json: Optional[str]
    full_text: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class ParsedDataSummary(BaseModel):
    sections_count: int
    tables_count: int
    images_count: int
    formulas_count: int
    references_count: int


class PaperAnalysisResult(BaseModel):
    message: str
    paper: PaperResponse
    parsed_data: ParsedDataSummary


class InteractiveTranslateRequest(BaseModel):
    text: str

class ExplainTermRequest(BaseModel):
    term: str

#新加入，图像公式理解调用的数据类型
class ImageUnderstandRequest(BaseModel):
    image_data: str  # base64 encoded image
    type: str
    context_text: Optional[str] = ""
    caption_text: Optional[str] = ""
