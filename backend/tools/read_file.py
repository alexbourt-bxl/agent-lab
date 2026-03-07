from tool import Tool


def create_read_file(handler):
    class ReadFile(Tool):
        def __init__(self) -> None:
            super().__init__(
                name="read_file_tool",
                description="Read the contents of a markdown file from the session directory by filename.",
                handler=handler,
            )

    return ReadFile
