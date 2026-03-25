from __future__ import annotations

import json
from typing import Any, TypeVar
from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


class LLMService:
    """Wraps an Anthropic async client. Returns validated Pydantic models.

    Usage:
        svc = LLMService(client=AsyncAnthropic(), model="claude-sonnet-4-6")
        result = await svc.call(system="...", prompt="...", output_schema=MyModel)
    """

    def __init__(self, client: Any, model: str) -> None:
        self._client = client
        self._model = model
        self.total_input_tokens: int = 0
        self.total_output_tokens: int = 0

    async def call(
        self,
        system: str,
        prompt: str,
        output_schema: type[T],
        max_retries: int = 3,
    ) -> T:
        schema_hint = json.dumps(output_schema.model_json_schema(), indent=2)
        full_system = (
            f"{system}\n\n"
            f"Respond with ONLY valid JSON matching this schema:\n{schema_hint}"
        )
        last_error: Exception | None = None
        for _ in range(max_retries):
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=2048,
                system=full_system,
                messages=[{"role": "user", "content": prompt}],
            )
            self.total_input_tokens += response.usage.input_tokens
            self.total_output_tokens += response.usage.output_tokens
            try:
                if not response.content:
                    raise ValueError("empty content list in LLM response")
                raw_text = response.content[0].text
                return output_schema.model_validate_json(raw_text)
            except (ValidationError, ValueError, json.JSONDecodeError, IndexError) as exc:
                last_error = exc
        raise ValueError(
            f"LLM failed to return valid {output_schema.__name__} "
            f"after {max_retries} attempts: {last_error}"
        )
