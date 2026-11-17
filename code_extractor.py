import re


def extract_java_code(response_text: str) -> str:
    """
    Pull the java code out of a ```java ... ``` fence.
    Falls back to the raw text if no fence is found (some models omit fences).
    """
    match = re.search(r"```(?:java)?\s*\n(.*?)```", response_text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return response_text.strip()


def extract_public_class_name(code: str) -> str:
    """
    javac requires the file name to match the public class name.
    Falls back to the first class/interface/enum declaration if no public class exists.
    """
    match = re.search(r"public\s+(?:final\s+|abstract\s+)?class\s+(\w+)", code)
    if match:
        return match.group(1)
    match = re.search(r"\b(?:class|interface|enum)\s+(\w+)", code)
    if match:
        return match.group(1)
    raise ValueError("Could not find any class declaration in generated code")
