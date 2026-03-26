from __future__ import annotations

from pydantic import BaseModel
from app.services.llm import LLMService


class CodeScaffold(BaseModel):
    project_structure: list[str]  # list of file paths
    main_code: str                 # content of entry point file
    dependencies: list[str]        # pip packages
    setup_instructions: str


class CodeWriter:
    """Generates MVP code scaffold for a SaaS product."""

    SYSTEM = (
        "You are a senior Python developer specializing in SaaS MVPs. "
        "Generate clean, production-ready FastAPI application scaffolding."
    )

    def __init__(self, llm: LLMService) -> None:
        self._llm = llm

    async def write(self, product_name: str, product_description: str) -> CodeScaffold:
        prompt = (
            f"Create a FastAPI MVP scaffold for: {product_name}\n"
            f"Description: {product_description}\n\n"
            "Include: project structure (file paths), main entry point code, "
            "pip dependencies, and setup instructions."
        )
        return await self._llm.call(
            system=self.SYSTEM,
            prompt=prompt,
            output_schema=CodeScaffold,
        )
