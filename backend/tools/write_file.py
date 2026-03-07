from tool import Tool


def create_write_file(handler):
    class WriteFile(Tool):
        def __init__(self) -> None:
            super().__init__(
                name="write_file_tool",
                description="Write content to a markdown file in the session directory by filename.",
                handler=handler,
            )

    return WriteFile
