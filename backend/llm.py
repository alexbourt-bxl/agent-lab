import json
from pathlib import Path
import sys
import time
from typing import Any

import httpx
from storage import load_settings


DEBUG_LOG_PATH = Path(__file__).resolve().parents[1] / "debug-ecf5ab.log"


def _debug_log(hypothesis_id: str, message: str, data: dict[str, object]) -> None:
    payload = {
        "sessionId": "ecf5ab",
        "runId": "pre-fix",
        "hypothesisId": hypothesis_id,
        "location": "backend/llm.py",
        "message": message,
        "data": data,
        "timestamp": int(time.time() * 1000),
    }
    with DEBUG_LOG_PATH.open("a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(payload) + "\n")


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
            # region agent log
            _debug_log(
                "H2",
                "ollama_generate_start",
                {
                    "baseUrl": self.base_url,
                    "model": selected_model,
                    "timeout": self.timeout,
                    "pythonExecutable": sys.executable,
                    "promptLength": len(prompt),
                },
            )
            # endregion
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(self.base_url, json=payload)
                response.raise_for_status()
        except httpx.ReadTimeout as error:
            # region agent log
            _debug_log(
                "H3",
                "ollama_generate_read_timeout",
                {
                    "baseUrl": self.base_url,
                    "errorType": type(error).__name__,
                    "error": str(error),
                    "timeout": self.timeout,
                },
            )
            # endregion
            return f"Error: Ollama timed out after {self.timeout:.0f}s."
        except httpx.RequestError as error:
            # region agent log
            _debug_log(
                "H3",
                "ollama_generate_request_error",
                {
                    "baseUrl": self.base_url,
                    "errorType": type(error).__name__,
                    "error": str(error),
                },
            )
            # endregion
            return f"Error: Ollama is not reachable. {error!s}"
        except httpx.HTTPStatusError as error:
            # region agent log
            _debug_log(
                "H4",
                "ollama_generate_http_status_error",
                {
                    "baseUrl": self.base_url,
                    "statusCode": error.response.status_code,
                    "responseText": error.response.text[:400],
                },
            )
            # endregion
            return f"Error: Ollama returned status {error.response.status_code}."

        data = response.json()
        # region agent log
        _debug_log(
            "H4",
            "ollama_generate_success",
            {
                "statusCode": response.status_code,
                "hasResponseField": "response" in data,
                "responsePreview": str(data.get("response", ""))[:120],
            },
        )
        # endregion
        return str(data.get("response", ""))


def get_ollama_tags_url(base_url: str | None = None) -> str:
    generate_url = base_url or OllamaInterface().base_url
    if generate_url.endswith("/api/generate"):
        return generate_url.replace("/api/generate", "/api/tags")

    return f"{generate_url.rstrip('/')}/api/tags"


async def list_available_ollama_models(base_url: str | None = None) -> list[str]:
    tags_url = get_ollama_tags_url(base_url)

    async with httpx.AsyncClient(timeout=30.0) as client:
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
