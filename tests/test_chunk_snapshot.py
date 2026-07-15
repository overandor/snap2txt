from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


class ChunkSnapshotTests(unittest.TestCase):
    def test_exact_reconstruction_and_zip_contents(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        script = repo_root / "tools" / "chunk_snapshot.py"

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "project_contents.txt"
            output_dir = root / "chunks"
            archive = root / "snapshot.zip"

            original = b"".join(
                f"line {number}\n".encode("utf-8")
                for number in range(1, 1601)
            ) + b"final line without newline"
            source.write_bytes(original)

            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    str(source),
                    "--output-dir",
                    str(output_dir),
                    "--chunk-lines",
                    "800",
                    "--archive-name",
                    archive.name,
                    "--source-label",
                    "hf://spaces/example/project",
                ],
                cwd=root,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

            manifest = json.loads((output_dir / "index.json").read_text())
            self.assertEqual(manifest["source_lines"], 1601)
            self.assertEqual(manifest["chunk_count"], 3)
            self.assertTrue(manifest["reconstruction_verified"])
            self.assertEqual(manifest["chunks"][0]["start_line"], 1)
            self.assertEqual(manifest["chunks"][0]["end_line"], 800)
            self.assertEqual(manifest["chunks"][-1]["start_line"], 1601)
            self.assertEqual(manifest["chunks"][-1]["end_line"], 1601)

            reconstructed = b"".join(
                (output_dir / chunk["file"]).read_bytes()
                for chunk in manifest["chunks"]
            )
            self.assertEqual(reconstructed, original)

            with zipfile.ZipFile(archive) as bundle:
                self.assertEqual(
                    bundle.read("full/project_contents.txt"),
                    original,
                )
                self.assertIn("index.json", bundle.namelist())
                self.assertIn("index.md", bundle.namelist())
                self.assertIn("checksums.sha256", bundle.namelist())


if __name__ == "__main__":
    unittest.main()
