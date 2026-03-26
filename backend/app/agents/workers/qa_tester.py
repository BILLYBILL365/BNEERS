from __future__ import annotations

from pydantic import BaseModel
from app.services.llm import LLMService


class QATestPlan(BaseModel):
    test_cases: list[str]    # list of test function names
    testing_framework: str   # "pytest"
    coverage_target: int     # percentage


class QATester:
    """Generates a test plan for a code scaffold."""

    SYSTEM = (
        "You are a QA engineer. Generate pytest test plans for FastAPI applications. "
        "Be thorough but focus on business-critical paths."
    )

    def __init__(self, llm: LLMService) -> None:
        self._llm = llm

    async def create_plan(self, product_name: str, code_files: list[str]) -> QATestPlan:
        prompt = (
            f"Create a test plan for: {product_name}\n"
            f"Files to test: {', '.join(code_files)}\n"
            "List test case names, the testing framework, and coverage target."
        )
        return await self._llm.call(
            system=self.SYSTEM,
            prompt=prompt,
            output_schema=QATestPlan,
        )
