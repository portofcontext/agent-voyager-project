export function frontmatterValue(
  text: string,
  key: "name" | "description",
): string | undefined {
  const body = /^---[ \t]*\r?\n([\s\S]*?)\r?\n---[ \t]*(?:\r?\n|$)/.exec(
    text,
  )?.[1];
  if (body === undefined) return undefined;
  const lines = body.split(/\r?\n/);
  for (let i = 0; i < lines.length; i++) {
    const match = new RegExp(`^${key}:[ \\t]*(.*?)[ \\t]*$`).exec(lines[i]);
    if (!match) continue;
    const value = match[1];
    if (value.startsWith(">") || value.startsWith("|")) {
      const block = [];
      for (const line of lines.slice(i + 1)) {
        if (line.trim() && !/^\s/.test(line)) break;
        block.push(line.trim());
      }
      return block.join(value[0] === ">" ? " " : "\n").trim();
    }
    if (
      value.length >= 2 &&
      ["'", '"'].includes(value[0]) &&
      value[0] === value.at(-1)
    )
      return value.slice(1, -1);
    return value.split(" #", 1)[0].trimEnd();
  }
  return undefined;
}

export function repr(value: string): string {
  const quote = value.includes("'") && !value.includes('"') ? '"' : "'";
  return (
    quote +
    value
      .replaceAll("\\", "\\\\")
      .replaceAll(quote, `\\${quote}`)
      .replaceAll("\n", "\\n")
      .replaceAll("\r", "\\r")
      .replaceAll("\t", "\\t") +
    quote
  );
}
