from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field


class CaseCreate(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=200)
    birth_date: date
    passport_data: str = Field(..., min_length=4, max_length=200)
    damage_amount: float = Field(..., ge=0)
    submitted_by: str = Field(..., min_length=2, max_length=200)
    submitted_at: Optional[datetime] = None
    description: str = Field(..., min_length=5, max_length=2000)
    photo_url: Optional[str] = Field(default=None, max_length=2000)


class CaseRecord(CaseCreate):
    id: str
    submitted_at: datetime


class CaseListResponse(BaseModel):
    items: list[CaseRecord]
    next_cursor: Optional[str] = None
