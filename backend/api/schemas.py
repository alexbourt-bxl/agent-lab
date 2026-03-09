"""Pydantic request/response models."""

from pydantic import BaseModel


class RunRequest(BaseModel):
    code: str
    sessionId: str
    maxRounds: int | None = 8


class SessionFileUpdateRequest(BaseModel):
    content: str


class SettingsUpdateRequest(BaseModel):
    model: str
    timeout: float
    llm_server: str


class SaveAgentRequest(BaseModel):
    name: str
    role: str = ""
    tools: list[str] = []
    code: str = ""
