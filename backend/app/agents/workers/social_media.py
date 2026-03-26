from __future__ import annotations

from pydantic import BaseModel
from app.services.llm import LLMService


class SocialPosts(BaseModel):
    twitter: list[str]   # 1-3 tweets
    linkedin: list[str]  # 1-2 LinkedIn posts


class SocialMedia:
    SYSTEM = "You are a social media manager for a SaaS startup. Write engaging posts."

    def __init__(self, llm: LLMService) -> None:
        self._llm = llm

    async def create_posts(self, product_name: str) -> SocialPosts:
        prompt = (
            f"Create launch social media posts for: {product_name}\n"
            "Provide 2 tweets (max 280 chars each) and 1 LinkedIn post."
        )
        return await self._llm.call(system=self.SYSTEM, prompt=prompt, output_schema=SocialPosts)
