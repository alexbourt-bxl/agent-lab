import json
from pathlib import Path
import sys
import time

import httpx


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


class OllamaInterface:
    def __init__(
        self,
        base_url: str = "http://192.168.129.11:11434/api/generate",
        timeout: float = 240.0,
    ) -> None:
        self.base_url = base_url
        self.timeout = timeout

    async def generate(self, prompt: str, model: str = "qwen3:4b") -> str:
        payload = (
            {
                "model": model,
                "prompt": prompt,
                "stream": False,
            }
        )

        try:
            # region agent log
            _debug_log(
                "H2",
                "ollama_generate_start",
                {
                    "baseUrl": self.base_url,
                    "model": model,
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
