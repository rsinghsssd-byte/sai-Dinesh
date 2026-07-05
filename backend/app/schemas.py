from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator

from .preprocessing import SUPPORTED_LANGUAGES


class AnalyzeRequest(BaseModel):
    repo_urls: List[str] = Field(..., min_length=2, max_length=20)
    language: str
    branch: str = "main"
    similarity_threshold: float = Field(0.75, ge=0.0, le=1.0)

    @field_validator("language")
    @classmethod
    def language_supported(cls, v: str) -> str:
        v = v.lower()
        if v not in SUPPORTED_LANGUAGES:
            raise ValueError(f"Unsupported language '{v}'. Supported: {list(SUPPORTED_LANGUAGES)}")
        return v

    @field_validator("repo_urls")
    @classmethod
    def urls_look_valid(cls, v: List[str]) -> List[str]:
        cleaned = []
        for url in v:
            url = url.strip()
            if not (url.startswith("https://github.com/") or url.startswith("git@github.com:")):
                raise ValueError(f"'{url}' does not look like a GitHub repository URL.")
            cleaned.append(url)
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("Duplicate repository URLs are not allowed.")
        return cleaned


class JobCreatedResponse(BaseModel):
    job_id: str
    status: str


class JobStatusResponse(BaseModel):
    id: str
    status: str
    progress: int
    progress_message: str
    error: Optional[str] = None
