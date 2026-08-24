from __future__ import annotations

from typing import TypedDict


class Opportunity(TypedDict):
    id: int
    vertical: str
    use_case_id: str
    use_case: str
    technology_id: str
    technology: str
    article_count: int
    relevance: int
    confidence: int
    horizon: str
    momentum: str
    summary: str
    updated: str


class Evidence(TypedDict):
    title: str
    source: str
    source_type: str
    url: str
    date: str
    excerpt: str
    confidence: int


class SourceSummary(TypedDict):
    source: str
    label: str
    count: int
    accent: str


class DocumentItem(TypedDict):
    id: int
    company: str
    name: str
    kind: str
    status: str
    size: str
    updated: str
    selected: bool
    processed_name: str
    context_enabled: bool
    context_scope: str


class SearchResult(TypedDict):
    title: str
    url: str
    source: str
    date: str
    excerpt: str


class ReportItem(TypedDict):
    id: int
    title: str
    company: str
    sources: int
    created: str
    status: str


class ReportMetric(TypedDict):
    label: str
    value: str
    detail: str


class ReportBullet(TypedDict):
    title: str
    detail: str


class ReportRisk(TypedDict):
    title: str
    detail: str
    level: str


class ReportRange(TypedDict):
    label: str
    low: float
    high: float
    unit: str
    detail: str
