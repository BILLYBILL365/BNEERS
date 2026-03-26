from __future__ import annotations

from pydantic import BaseModel
from app.services.llm import LLMService


class AdCopy(BaseModel):
    headline: str
    body: str
    cta: str
    estimated_cpc: float  # cost per click in USD


class AdManager:
    SYSTEM = "You are a performance marketing specialist. Write high-converting ad copy."

    def __init__(self, llm: LLMService) -> None:
        self._llm = llm

    async def create_ad(self, product_name: str, budget: float) -> AdCopy:
        prompt = (
            f"Create Google/LinkedIn ad copy for: {product_name}\n"
            f"Available budget: ${budget:.2f}\n"
            "Provide: headline (max 30 chars), body (max 90 chars), CTA, estimated CPC."
        )
        return await self._llm.call(system=self.SYSTEM, prompt=prompt, output_schema=AdCopy)
