from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Article:
    vertical: str
    source_name: str
    source_type: str
    title: str
    url: Optional[str]
    guid: Optional[str]
    published_date: Optional[datetime]
    summary: Optional[str]
    collected_at: datetime
    confidence: Optional[str] = None
    extra: Optional[dict] = field(default=None)
    time_window: Optional[str] = None
