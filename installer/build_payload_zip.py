from __future__ import annotations

import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


EXCLUDED_PARTS = {".tools.local_backup", "__pycache__"}


def build_zip(source_dir: Path, output_zip: Path) -> None:
    source_root = source_dir.resolve()
    if not (source_root / "Start_X-Amplicon_WebUI.vbs").is_file() or not (source_root / "Start_X-Amplicon_WebUI.cmd").is_file():
        raise SystemExit(f"Source directory does not look like a Windows release: {source_root}")

    temp_zip = output_zip.with_suffix(output_zip.suffix + ".tmp")
    if temp_zip.exists():
        temp_zip.unlink()

    count = 0
    total_bytes = 0
    with ZipFile(temp_zip, "w", compression=ZIP_DEFLATED, compresslevel=1) as archive:
        for path in source_root.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(source_root)
            if EXCLUDED_PARTS.intersection(relative.parts):
                continue
            archive.write(path, relative.as_posix())
            count += 1
            total_bytes += path.stat().st_size

    if output_zip.exists():
        output_zip.unlink()
    temp_zip.replace(output_zip)
    print(f"Created {output_zip}")
    print(f"Files: {count}")
    print(f"Source bytes: {total_bytes / 1024 / 1024:.2f} MB")


def main() -> None:
    script_root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", default=str(script_root.parent / "X-Amplicon_win64"))
    parser.add_argument("--output-zip", default=str(script_root.parent / "X-Amplicon_win64.zip"))
    args = parser.parse_args()
    build_zip(Path(args.source_dir), Path(args.output_zip))


if __name__ == "__main__":
    main()
