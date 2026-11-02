pub(super) fn frontmatter_value(text: &str, key: &str) -> Option<String> {
    let mut lines = text.lines();
    if lines.next()?.trim_end_matches([' ', '\t']) != "---" {
        return None;
    }
    let body: Vec<_> = lines
        .take_while(|line| line.trim_end_matches([' ', '\t']) != "---")
        .collect();
    // A closing delimiter is required, even for a plain value.
    if !text
        .lines()
        .skip(1)
        .any(|line| line.trim_end_matches([' ', '\t']) == "---")
    {
        return None;
    }
    for (i, line) in body.iter().enumerate() {
        let Some(value) = line.strip_prefix(&format!("{key}:")) else {
            continue;
        };
        let value = value.trim_matches([' ', '\t']);
        if value.starts_with(['>', '|']) {
            let block: Vec<_> = body[i + 1..]
                .iter()
                .take_while(|line| line.trim().is_empty() || line.starts_with(char::is_whitespace))
                .map(|line| line.trim())
                .collect();
            return Some(
                block
                    .join(if value.starts_with('>') { " " } else { "\n" })
                    .trim()
                    .into(),
            );
        }
        if value.len() >= 2
            && (value.starts_with('"') && value.ends_with('"')
                || value.starts_with('\'') && value.ends_with('\''))
        {
            return Some(value[1..value.len() - 1].into());
        }
        return Some(value.split(" #").next().unwrap().trim_end().into());
    }
    None
}
