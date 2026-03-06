import httpx


class OllamaInterface:
    def __init__(
        self,
        base_url: str = "http://192.168.129.11:11434/api/generate",
        timeout: float = 30.0,
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
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(self.base_url, json=payload)
                response.raise_for_status()
        except httpx.RequestError:
            return "Error: Ollama is not reachable."
        except httpx.HTTPStatusError as error:
            return f"Error: Ollama returned status {error.response.status_code}."

        data = response.json()
        return str(data.get("response", ""))
