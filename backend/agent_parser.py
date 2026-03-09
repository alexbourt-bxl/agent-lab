"""Extract agent configs from workflow code."""

import re
from typing import Any


def extract_string_argument(arguments: str, argument_name: str) -> str | None:
    match = re.search(
        rf'{argument_name}\s*=\s*(?P<quote>["\'])(?P<value>.*?)(?P=quote)',
        arguments,
        re.DOTALL,
    )
    if match is None:
        return None

    return match.group("value")


def extract_input_source_variable(arguments: str) -> str | None:
    match = re.search(
        r'input\s*=\s*(?P<source_variable>\w+)\.output',
        arguments,
    )
    if match is None:
        return None

    return match.group("source_variable")


def extract_start_argument(arguments: str) -> bool:
    match = re.search(
        r'start\s*=\s*(?P<value>True|False|true|false)',
        arguments,
    )
    if match is None:
        return False

    return match.group("value").lower() == "true"


def _extract_class_attrs(
    code: str,
    start: int,
    end: int,
) -> dict[str, Any]:
    from tools import TOOL_REGISTRY

    body = code[start:end]
    attrs: dict[str, Any] = {}
    name_match = re.search(r'name\s*=\s*["\']([^"\']*)["\']', body)
    role_match = re.search(r'role\s*=\s*["\']([^"\']*)["\']', body)
    tools_match = re.search(r"tools\s*=\s*\[([^\]]+)\]", body)
    max_rounds_match = re.search(r"max_rounds\s*=\s*(\d+)", body)
    if name_match:
        attrs["name"] = name_match.group(1)
    if role_match:
        attrs["role"] = role_match.group(1)
    if tools_match:
        tool_names = [
            t.strip() for t in tools_match.group(1).split(",")
        ]
        attrs["tools"] = [
            TOOL_REGISTRY[t]
            for t in tool_names
            if t in TOOL_REGISTRY
        ]
    else:
        attrs["tools"] = []
    attrs["max_rounds"] = int(max_rounds_match.group(1)) if max_rounds_match else 8
    return attrs


def extract_agent_configs(code: str) -> list[dict[str, Any]]:
    class_matches = list(re.finditer(r"class (\w+)\(Agent\):\s*", code))
    classes_by_name: dict[str, dict[str, Any]] = {}

    for i, match in enumerate(class_matches):
        class_name = match.group(1)
        body_start = match.end()
        body_end = (
            class_matches[i + 1].start()
            if i + 1 < len(class_matches)
            else len(code)
        )
        next_class = re.search(r"\nclass \w+\(Agent\)", code[body_start:])
        if next_class:
            body_end = body_start + next_class.start()
        attrs = _extract_class_attrs(code, body_start, body_end)
        classes_by_name[class_name] = {
            "name": attrs.get("name", class_name),
            "role": attrs.get("role", ""),
            "tools": attrs.get("tools", []),
            "max_rounds": attrs.get("max_rounds", 8),
        }

    configs: list[dict[str, Any]] = []
    for class_name in classes_by_name:
        pattern = rf"(\w+)\s*=\s*{re.escape(class_name)}\s*\(\s*([^)]*)\)"
        for m in re.finditer(pattern, code):
            variable = m.group(1)
            arguments = m.group(2)
            task = extract_string_argument(arguments, "task") or extract_string_argument(
                arguments, "goal"
            )
            if not task:
                continue
            configs.append(
                {
                    "variable": variable,
                    "className": class_name,
                    "name": (
                        str(classes_by_name[class_name]["name"]).strip()
                        or class_name
                    ),
                    "role": str(classes_by_name[class_name]["role"] or ""),
                    "task": task,
                    "inputSourceVariable": extract_input_source_variable(
                        arguments
                    ),
                    "start": extract_start_argument(arguments),
                    "tools": classes_by_name[class_name]["tools"],
                    "max_rounds": classes_by_name[class_name]["max_rounds"],
                }
            )
            break

    def order_key(c: dict[str, Any]) -> int:
        return code.index(f'{c["variable"]} = {c["className"]}')

    configs.sort(key=order_key)
    return configs
