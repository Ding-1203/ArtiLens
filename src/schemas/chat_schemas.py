from pydantic import BaseModel, ConfigDict
from typing import List, Optional
from datetime import datetime


class QuestionRequest(BaseModel):
    user_id: int = 0
    question: str


class ChatResponse(BaseModel):
    id: int
    paper_id: int
    user_id: int
    question: str
    answer: str
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)



