import json
from typing import Any, AsyncIterator, Protocol

import httpx
from storage import load_settings


class LLMClient(Protocol):
    """Provider-neutral LLM client interface."""

    async def generate(
        self,
        prompt: str,
        model: str | None = None,
        system: str | None = None,
    ) -> str:
        ...

    async def generate_stream(
        self,
        prompt: str,
        model: str | None = None,
        system: str | None = None,
    ) -> AsyncIterator[str]:
        ...

    async def list_models(self) -> list[str]:
        ...


def _normalize_llm_server_url(raw: str) -> str:
    url = raw.strip()
    if not url.startswith(("http://", "https://")):
        url = f"http://{url}"
    return f"{url.rstrip('/')}/api/generate"


class OllamaInterface:
    def __init__(
        self,
        base_url: str | None = None,
        timeout: float | None = None,
        default_model: str | None = None,
        settings: dict[str, Any] | None = None,
    ) -> None:
        if settings is None:
            settings = load_settings()
        llm_server = str(settings.get("llm_server", "http://192.168.129.11:11434"))
        self.base_url = base_url or _normalize_llm_server_url(llm_server)
        self.timeout = timeout if timeout is not None else float(settings.get("timeout", 240.0))
        self.default_model = default_model or str(settings.get("model", "qwen3:4b"))

    async def generate(
        self,
        prompt: str,
        model: str | None = None,
        system: str | None = None,
    ) -> str:
        selected_model = model or self.default_model
        payload: dict[str, object] = (
            {
                "model": selected_model,
                "prompt": prompt,
                "stream": False,
            }
        )
        if system is not None and system != "":
            payload["system"] = system

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(self.base_url, json=payload)
                response.raise_for_status()
        except httpx.ReadTimeout as error:
            return f"Error: Ollama timed out after {self.timeout:.0f}s."
        except httpx.RequestError as error:
            return f"Error: Ollama is not reachable. {error!s}"
        except httpx.HTTPStatusError as error:
            return f"Error: Ollama returned status {error.response.status_code}."

        data = response.json()
        return str(data.get("response", ""))

    async def generate_stream(
        self,
        prompt: str,
        model: str | None = None,
        system: str | None = None,
    ) -> AsyncIterator[str]:
        selected_model = model or self.default_model
        payload: dict[str, object] = {
            "model": selected_model,
            "prompt": prompt,
            "stream": True,
        }
        if system is not None and system != "":
            payload["system"] = system

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream("POST", self.base_url, json=payload) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            data = json.loads(line)
                            chunk = data.get("response", "")
                            if isinstance(chunk, str) and chunk:
                                yield chunk
                        except json.JSONDecodeError:
                            continue
        except httpx.ReadTimeout:
            yield f"Error: Ollama timed out after {self.timeout:.0f}s."
        except httpx.RequestError as error:
            yield f"Error: Ollama is not reachable. {error!s}"
        except httpx.HTTPStatusError:
            yield "Error: Ollama returned a non-2xx status."

    async def list_models(self) -> list[str]:
        return await list_available_ollama_models(self.base_url)


def get_llm_client(settings: dict[str, Any] | None = None) -> OllamaInterface:
    """
    Return the appropriate LLM client for the given settings.
    Currently always returns Ollama; extend for other providers later.
    """
    return OllamaInterface(settings=settings)


def get_ollama_tags_url(base_url: str | None = None) -> str:
    generate_url = base_url or OllamaInterface().base_url
    if generate_url.endswith("/api/generate"):
        return generate_url.replace("/api/generate", "/api/tags")

    return f"{generate_url.rstrip('/')}/api/tags"


async def list_available_ollama_models(base_url: str | None = None) -> list[str]:
    tags_url = get_ollama_tags_url(base_url)

    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(tags_url)
        response.raise_for_status()

    payload = response.json()
    models = payload.get("models", [])
    if not isinstance(models, list):
        return []

    available_models: list[str] = []

    for model in models:
        if not isinstance(model, dict):
            continue

        model_name = model.get("name")
        if isinstance(model_name, str) and model_name not in available_models:
            available_models.append(model_name)

    return available_models
