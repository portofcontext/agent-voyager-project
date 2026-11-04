"""Reading a `SKILL.md`'s frontmatter without a YAML parser."""

import re

_FRONTMATTER = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(\r?\n|\Z)", re.DOTALL)


def frontmatter_value(skill_md: str, key: str) -> str | None:
    """The top-level `key` in a `SKILL.md`'s frontmatter, or None when it has
    none. Handles plain and quoted values, trailing comments, and `>` and `|`
    block values."""
    frontmatter = _FRONTMATTER.match(skill_md)
    if frontmatter is None:
        return None
    lines = frontmatter.group(1).splitlines()
    for i, line in enumerate(lines):
        match = re.match(rf"^{re.escape(key)}:[ \t]*(.*?)[ \t]*$", line)
        if match is None:
            continue
        value = match.group(1)
        if value[:1] in (">", "|"):
            block = []
            for more in lines[i + 1 :]:
                if more.strip() and not more[:1].isspace():
                    break
                block.append(more.strip())
            return (" " if value[0] == ">" else "\n").join(block).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            return value[1:-1]
        return value.split(" #", 1)[0].rstrip()
    return None
