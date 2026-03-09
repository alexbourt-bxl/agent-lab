"""Extract workflow and agent class code from combined script."""

import re


def _extract_workflow_and_agent_code(code: str) -> tuple[str, dict[str, str]]:
    """Extract workflow code and agent class code from combined code."""
    workflow_code = ""
    agent_code: dict[str, str] = {}

    class_matches = list(re.finditer(r"class (\w+)\(Agent\):\s*", code))
    for i, match in enumerate(class_matches):
        class_name = match.group(1)
        body_start = match.end()
        next_class = re.search(r"\nclass \w+\(Agent\)", code[body_start:])
        next_inst = re.search(r"\n([A-Za-z_]\w*)\s*=\s*\w+\s*\(", code[body_start:])
        class_end = len(code)
        if next_class and next_inst:
            class_end = body_start + min(next_class.start(), next_inst.start())
        elif next_class:
            class_end = body_start + next_class.start()
        elif next_inst:
            class_end = body_start + next_inst.start()
        elif i + 1 < len(class_matches):
            class_end = class_matches[i + 1].start()
        class_block = code[match.start() : class_end].strip()
        agent_code[class_name] = class_block

    first_inst = re.search(r"\n([A-Za-z_]\w*)\s*=\s*\w+\s*\(", code)
    if first_inst:
        workflow_code = code[first_inst.start() :].lstrip()
    elif not class_matches:
        workflow_code = code.strip()

    return workflow_code, agent_code


def _get_agent_name_from_class(class_code: str) -> str | None:
    """Extract agent display name from class body (name attr or class name)."""
    match = re.search(r'name\s*=\s*["\']([^"\']*)["\']', class_code)
    if match and match.group(1).strip():
        return match.group(1).strip()
    match = re.search(r"class (\w+)\(Agent\)", class_code)
    return match.group(1) if match else None
