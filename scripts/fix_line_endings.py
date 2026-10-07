#!/usr/bin/env python3
"""Convert CRLF line endings back to LF in the files that run inside Linux containers.

Why this exists
---------------
On Windows, Git often checks files out with CRLF (core.autocrlf=true). A shell
script with CRLF fails inside the Linux container ("bad interpreter",
"required file not found", "$'\\r': command not found"). The worst case is
docker/postgres/init/02_schema.sh: when it fails, PostgreSQL's one-time init
stops before the reference data and the read-only role mcp_reader are created.
The container then starts "healthy" with an empty database, and the seeder
fails on its first INSERT.

Usage (from the project root, any OS):

    uv run python scripts/fix_line_endings.py             convert files, report what changed
    uv run python scripts/fix_line_endings.py --check     only report, change nothing
    uv run python scripts/fix_line_endings.py --reset-db  also wipe the database volumes

--reset-db is needed after the fix if PostgreSQL has already started once with
the broken script: the init scripts only run on an EMPTY data volume, so
fixing the files alone changes nothing. It runs `docker compose ... down -v`,
which DELETES all data in the workshop volumes, so it asks for confirmation
(skip the prompt with --yes).

Files are converted byte-for-byte (only CR immediately before LF is removed),
so Thai text and every other byte stay exactly as they were. No BOM is added.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Files that are mounted into, or copied into, a Linux container and read there.
# (YAML, JSON and Python tolerate CRLF, so they are left alone.)
PATTERNS = ("*.sh", "*.sql", "*.template", "Procfile", "Dockerfile*")
SEARCH_DIRS = ("docker", "scripts")

COMPOSE = [
    "docker", "compose", "-f", "docker/docker-compose.yml", "--env-file", ".env",
    "--profile", "demo", "down", "-v",
]


def find_files() -> list[Path]:
    found: set[Path] = set()
    for directory in SEARCH_DIRS:
        base = ROOT / directory
        if not base.is_dir():
            continue
        for pattern in PATTERNS:
            found.update(p for p in base.rglob(pattern) if p.is_file())
    return sorted(found)


def convert(path: Path, write: bool) -> int:
    """Return the number of CRLF sequences found; rewrite the file when `write`."""
    data = path.read_bytes()
    count = data.count(b"\r\n")
    if count and write:
        path.write_bytes(data.replace(b"\r\n", b"\n"))
    return count


def reset_database(assume_yes: bool) -> int:
    print("\n--reset-db: จะรัน  " + " ".join(COMPOSE))
    print("คำสั่งนี้ลบข้อมูลทั้งหมดใน volume ของ workshop (PostgreSQL, Neo4j, OpenSearch, pgAdmin)")
    if not assume_yes:
        answer = input("พิมพ์ yes เพื่อยืนยัน: ").strip().lower()
        if answer != "yes":
            print("ยกเลิก ไม่ได้ลบอะไร")
            return 1
    try:
        result = subprocess.run(COMPOSE, cwd=ROOT)
    except FileNotFoundError:
        print("ไม่พบคำสั่ง docker ในเครื่อง")
        return 1
    if result.returncode != 0:
        print("docker compose ล้มเหลว (ดูข้อความด้านบน)")
        return result.returncode
    print("\nล้างเรียบร้อย ขั้นต่อไป: ทำหัวข้อ 1 ของ INSTRUCTIONS/day0/05-setup.md ใหม่ตั้งแต่ต้น")
    print("(เปิดฐานข้อมูล แล้ว `up seeder` ให้จบ จากนั้นตรวจด้วย verify.py)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true", help="report only, change nothing")
    parser.add_argument("--reset-db", action="store_true",
                        help="after converting, run `docker compose down -v` (deletes workshop data)")
    parser.add_argument("--yes", action="store_true", help="do not ask before --reset-db")
    args = parser.parse_args()

    files = find_files()
    if not files:
        print("ไม่พบไฟล์ที่ต้องตรวจ (ต้องรันจากโฟลเดอร์โปรเจกต์ที่มี docker/)")
        return 1

    bad = 0
    for path in files:
        count = convert(path, write=not args.check)
        rel = path.relative_to(ROOT)
        if count == 0:
            print(f"  LF     {rel}")
        else:
            bad += 1
            verb = "พบ CRLF" if args.check else "แก้แล้ว"
            print(f"  CRLF   {rel}  ({verb} {count} บรรทัด)")

    if args.check:
        print(f"\nตรวจ {len(files)} ไฟล์: มี CRLF {bad} ไฟล์ (โหมด --check ไม่ได้แก้ไฟล์)")
    else:
        print(f"\nตรวจ {len(files)} ไฟล์: แปลงเป็น LF {bad} ไฟล์")

    if bad and not args.reset_db:
        print("\nหมายเหตุ: หาก PostgreSQL เคยเริ่มทำงานไปแล้วด้วยไฟล์ที่ผิด ต้องล้าง volume เพื่อให้ init รันใหม่")
        print("          รันซ้ำพร้อม --reset-db (จะถามยืนยันก่อนลบข้อมูล)")

    if args.reset_db:
        if args.check:
            print("\n--reset-db ใช้ร่วมกับ --check ไม่ได้ (ไม่ทำอะไร)")
            return 2
        return reset_database(args.yes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
