from __future__ import annotations

import time


class LLMClient:
    def __init__(self, provider: str, api_key: str, base_url: str | None = None) -> None:
        self.provider = provider.lower()
        if self.provider == "anthropic":
            import anthropic
            self._client = anthropic.Anthropic(api_key=api_key)
        elif self.provider == "openai":
            from openai import OpenAI
            self._client = OpenAI(api_key=api_key)
        elif self.provider == "local":
            # llama.cpp's llama-server exposes an OpenAI-compatible /v1/chat/completions
            # endpoint, so the OpenAI client works unmodified against it.
            from openai import OpenAI
            self._client = OpenAI(base_url=base_url or "http://localhost:8080/v1", api_key=api_key or "not-needed")
        else:
            raise ValueError(f"Unsupported provider: {provider!r}. Choose 'anthropic', 'openai', or 'local'.")

    def complete(
        self,
        model: str,
        system: str,
        user: str,
        max_tokens: int = 4096,
        retries: int = 3,
        retry_delay: float = 5.0,
    ) -> tuple[str, int, int]:
        last_err = None
        for attempt in range(1, retries + 1):
            try:
                return self._call(model, system, user, max_tokens)
            except Exception as e:
                last_err = e
                if attempt < retries:
                    print(f"  [llm] attempt {attempt} failed ({e.__class__.__name__}), retrying in {retry_delay}s...")
                    time.sleep(retry_delay)
        raise last_err

    def _call(self, model: str, system: str, user: str, max_tokens: int) -> tuple[str, int, int]:
        if self.provider == "anthropic":
            response = self._client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            return response.content[0].text, response.usage.input_tokens, response.usage.output_tokens

        elif self.provider in ("openai", "local"):
            response = self._client.chat.completions.create(
                model=model,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
            usage = response.usage
            input_tokens = getattr(usage, "prompt_tokens", 0) if usage else 0
            output_tokens = getattr(usage, "completion_tokens", 0) if usage else 0
            return response.choices[0].message.content, input_tokens, output_tokens
