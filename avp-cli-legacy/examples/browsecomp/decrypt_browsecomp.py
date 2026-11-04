#!/usr/bin/env python3
"""One-off: decrypt the BrowseComp test set CSV into a plain JSONL.

BrowseComp ships `problem` / `answer` XOR-encrypted (base64), keyed by
`SHA256(canary)` per row, so the benchmark never sits in plain text online. The
AVP `file` dataset source reads plain JSON/JSONL, so we decrypt once, locally,
into a JSONL the eval points at. The output is canary-protected benchmark data:
keep it local, do not commit it (it is gitignored).

The crypto is verbatim from openai/simple-evals `browsecomp_eval.py`.

Run from this directory so the JSONL lands next to the eval config:

    cd avp-cli/examples/browsecomp
    uv run python decrypt_browsecomp.py   # reads ~/Downloads/browse_comp_test_set.csv
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
from pathlib import Path


def derive_key(password: str, length: int) -> bytes:
    """Derive a fixed-length key from the password using SHA256."""
    hasher = hashlib.sha256()
    hasher.update(password.encode())
    key = hasher.digest()
    return key * (length // len(key)) + key[: length % len(key)]


def decrypt(ciphertext_b64: str, password: str) -> str:
    """Decrypt base64-encoded ciphertext with XOR."""
    encrypted = base64.b64decode(ciphertext_b64)
    key = derive_key(password, len(encrypted))
    decrypted = bytes(a ^ b for a, b in zip(encrypted, key, strict=True))
    return decrypted.decode()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--in",
        dest="src",
        default=str(Path.home() / "Downloads" / "browse_comp_test_set.csv"),
        help="encrypted BrowseComp CSV (default: ~/Downloads/browse_comp_test_set.csv)",
    )
    ap.add_argument(
        "--out",
        dest="dst",
        default="browse_comp.jsonl",
        help="decrypted JSONL output path (default: ./browse_comp.jsonl)",
    )
    args = ap.parse_args()

    src, dst = Path(args.src), Path(args.dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with src.open(newline="") as f, dst.open("w") as out:
        for i, row in enumerate(csv.DictReader(f)):
            canary = row["canary"]
            rec = {
                "id": str(i),
                "problem": decrypt(row["problem"], canary),
                "answer": decrypt(row["answer"], canary),
                "problem_topic": row.get("problem_topic", ""),
            }
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n += 1
    print(f"decrypted {n} rows -> {dst}")


if __name__ == "__main__":
    main()
