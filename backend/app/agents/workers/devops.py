from __future__ import annotations

from typing import Any
from pydantic import BaseModel
from app.services.llm import LLMService


class DeploymentConfig(BaseModel):
    dockerfile: str
    railway_config: dict[str, Any]
    environment_variables: list[str]
    deploy_steps: list[str]


class DevOps:
    """Generates deployment configuration for Railway."""

    SYSTEM = (
        "You are a DevOps engineer specializing in Railway deployments. "
        "Generate Dockerfiles and Railway config files."
    )

    def __init__(self, llm: LLMService) -> None:
        self._llm = llm

    async def create_config(self, product_name: str) -> DeploymentConfig:
        prompt = (
            f"Generate Railway deployment configuration for: {product_name}\n"
            "Include: Dockerfile, railway.json config, required env vars, deploy steps."
        )
        return await self._llm.call(
            system=self.SYSTEM,
            prompt=prompt,
            output_schema=DeploymentConfig,
        )
