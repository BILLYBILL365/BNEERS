from __future__ import annotations

from pydantic import BaseModel
from app.services.llm import LLMService


class ContentPackage(BaseModel):
    landing_page_headline: str
    landing_page_body: str
    blog_post_titles: list[str]
    email_subject: str


class ContentWriter:
    SYSTEM = "You are a SaaS copywriter. Write compelling, conversion-focused content."

    def __init__(self, llm: LLMService) -> None:
        self._llm = llm

    async def create(self, product_name: str, target_market: str) -> ContentPackage:
        prompt = (
            f"Create marketing content for: {product_name}\n"
            f"Target market: {target_market}\n"
            "Provide: landing page headline, landing page body (3 paragraphs), "
            "blog post titles (3), and email subject line."
        )
        return await self._llm.call(system=self.SYSTEM, prompt=prompt, output_schema=ContentPackage)
