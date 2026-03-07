from typing import Callable


class Tool:
    def __init__(
        self,
        name: str,
        description: str = "",
        handler: Callable[..., str] | None = None,
    ) -> None:
        self.name = name
        self.description = description
        self.handler = handler
