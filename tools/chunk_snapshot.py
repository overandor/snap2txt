#!/usr/bin/env python3
"""Split a Snap2Txt snapshot into indexed, integrity-checked chunks and a ZIP."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Split project_contents.txt into line-indexed chunks, build manifests, "
            "verify exact reconstruction, and create a ZIP archive."
        )
    )
    parser.add_argument(
        "input",
        nargs="?",
        default="project_contents.txt",
        help="Snap2Txt output file (default: project_contents.txt)",
    )
    parser.add_argument(
        "--output-dir",
        default="snapshot_chunks",
        help="Directory for chunks and manifests (default: snapshot_chunks)",
    )
    parser.add_argument(
        "--chunk-lines",
        type=int,
        default=800,
        help="Maximum original lines per chunk (default: 800)",
    )
    parser.add_argument(
        "--archive-name",
        default="snapshot_chunks.zip",
        help="ZIP filename created beside the output directory",
    )
    parser.add_argument(
        "--source-label",
        default=None,
        help="Human-readable source repository label for manifests",
    )
    return parser.parse_args()


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    args = parse_args()
    if args.chunk_lines < 1:
        raise SystemExit("--chunk-lines must be at least 1")

    source_path = Path(args.input).resolve()
    if not source_path.is_file():
        raise SystemExit(f"Input file not found: {source_path}")

    output_dir = Path(args.output_dir).resolve()
    archive_path = output_dir.parent / args.archive_name

    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if archive_path.exists():
        archive_path.unlink()

    source_bytes = source_path.read_bytes()
    source_lines = source_bytes.splitlines(keepends=True)
    generated_at = datetime.now(timezone.utc).isoformat()

    chunks: list[dict[str, Any]] = []
    reconstructed = bytearray()

    for offset in range(0, len(source_lines), args.chunk_lines):
        chunk_number = len(chunks) + 1
        chunk_lines = source_lines[offset : offset + args.chunk_lines]
        start_line = offset + 1
        end_line = offset + len(chunk_lines)
        chunk_bytes = b"".join(chunk_lines)
        chunk_name = (
            f"chunk_{chunk_number:04d}_"
            f"lines_{start_line:06d}-{end_line:06d}.txt"
        )
        chunk_path = output_dir / chunk_name
        chunk_path.write_bytes(chunk_bytes)
        reconstructed.extend(chunk_bytes)
        chunks.append(
            {
                "id": chunk_number,
                "file": chunk_name,
                "start_line": start_line,
                "end_line": end_line,
                "line_count": len(chunk_lines),
                "bytes": len(chunk_bytes),
                "sha256": sha256_bytes(chunk_bytes),
            }
        )

    if bytes(reconstructed) != source_bytes:
        raise RuntimeError("Chunk reconstruction differs from the source bytes")

    source_sha256 = sha256_bytes(source_bytes)
    manifest = {
        "format": "snap2txt-indexed-chunks/v1",
        "generated_at_utc": generated_at,
        "source_label": args.source_label,
        "source_file": source_path.name,
        "source_bytes": len(source_bytes),
        "source_lines": len(source_lines),
        "source_sha256": source_sha256,
        "ends_with_newline": source_bytes.endswith((b"\n", b"\r")),
        "chunk_lines_limit": args.chunk_lines,
        "chunk_count": len(chunks),
        "reconstructed_sha256": sha256_bytes(bytes(reconstructed)),
        "reconstruction_verified": True,
        "chunks": chunks,
    }
    write_json(output_dir / "index.json", manifest)

    markdown = [
        "# Indexed Snap2Txt snapshot",
        "",
        f"- Source: `{args.source_label or source_path.name}`",
        f"- Original lines: **{len(source_lines):,}**",
        f"- Original bytes: **{len(source_bytes):,}**",
        f"- Source SHA-256: `{source_sha256}`",
        f"- Chunk size limit: **{args.chunk_lines:,} lines**",
        f"- Chunk count: **{len(chunks):,}**",
        "- Reconstruction verified: **yes**",
        "",
        "## Chunks",
        "",
    ]
    for chunk in chunks:
        markdown.append(
            f"- [{chunk['file']}]({chunk['file']}) "
            f"— original lines {chunk['start_line']:,}–{chunk['end_line']:,}; "
            f"{chunk['bytes']:,} bytes; SHA-256 `{chunk['sha256']}`"
        )
    (output_dir / "index.md").write_text(
        "\n".join(markdown) + "\n",
        encoding="utf-8",
    )

    checksums = [
        f"{source_sha256}  full/{source_path.name}",
        *[
            f"{chunk['sha256']}  chunks/{chunk['file']}"
            for chunk in chunks
        ],
    ]
    (output_dir / "checksums.sha256").write_text(
        "\n".join(checksums) + "\n",
        encoding="utf-8",
    )

    with zipfile.ZipFile(
        archive_path,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        archive.writestr(f"full/{source_path.name}", source_bytes)
        archive.write(output_dir / "index.json", "index.json")
        archive.write(output_dir / "index.md", "index.md")
        archive.write(output_dir / "checksums.sha256", "checksums.sha256")
        for chunk in chunks:
            archive.write(
                output_dir / chunk["file"],
                f"chunks/{chunk['file']}",
            )

    print(
        json.dumps(
            {
                "source": str(source_path),
                "output_dir": str(output_dir),
                "archive": str(archive_path),
                "source_lines": len(source_lines),
                "source_bytes": len(source_bytes),
                "source_sha256": source_sha256,
                "chunk_count": len(chunks),
                "reconstruction_verified": True,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
