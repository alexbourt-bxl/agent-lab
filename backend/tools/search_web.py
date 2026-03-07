from tool import Tool


class SearchWeb(Tool):
    def __init__(self) -> None:
        super().__init__(
            name="web_search_tool",
            description="Search the web for information. (Not yet implemented.)",
            handler=lambda query: "SearchWeb is not yet implemented.",
        )
