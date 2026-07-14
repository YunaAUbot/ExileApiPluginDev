"""Seek-based inspection for ExileAPI's TAR-backed .exapisnap archives.

The indexer reads TAR headers only and seeks over member bodies. It never
extracts an archive or loads a multi-gigabyte snapshot into memory.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

BLOCK_SIZE = 512
MAX_PAX_BYTES = 1_048_576


def _tar_number(value: bytes) -> int:
    value = value.rstrip(b"\0 ")
    if not value:
        return 0
    if value[0] & 0x80:  # GNU base-256 encoding
        return int.from_bytes(value, "big", signed=True)
    return int(value, 8)


def _tar_text(value: bytes) -> str:
    return value.split(b"\0", 1)[0].decode("utf-8", errors="replace")


def _round_block(size: int) -> int:
    return ((size + BLOCK_SIZE - 1) // BLOCK_SIZE) * BLOCK_SIZE


def _pax_attributes(payload: bytes) -> dict[str, str]:
    attributes: dict[str, str] = {}
    cursor = 0
    while cursor < len(payload):
        space = payload.find(b" ", cursor)
        if space < 0:
            break
        try:
            record_length = int(payload[cursor:space])
        except ValueError:
            break
        record = payload[space + 1 : cursor + record_length].rstrip(b"\n")
        key, separator, value = record.partition(b"=")
        if separator:
            attributes[key.decode("utf-8", errors="replace")] = value.decode("utf-8", errors="replace")
        cursor += record_length
    return attributes


def build_index(snapshot: Path) -> dict[str, object]:
    """Return a compact header-only TAR index for an ExileAPI snapshot."""
    entries: list[dict[str, object]] = []
    pending_pax: dict[str, str] = {}
    pending_long_name: str | None = None
    with snapshot.open("rb") as stream:
        while True:
            header_offset = stream.tell()
            header = stream.read(BLOCK_SIZE)
            if not header or len(header) != BLOCK_SIZE:
                break
            if header == b"\0" * BLOCK_SIZE:
                break
            size = _tar_number(header[124:136])
            type_flag = _tar_text(header[156:157]) or "0"
            name = _tar_text(header[0:100])
            prefix = _tar_text(header[345:500])
            if prefix:
                name = f"{prefix}/{name}"
            data_offset = stream.tell()
            if type_flag in {"x", "g"}:
                if size > MAX_PAX_BYTES:
                    raise ValueError(f"PAX header at {header_offset} exceeds {MAX_PAX_BYTES} bytes")
                attributes = _pax_attributes(stream.read(size))
                if type_flag == "g":
                    pending_pax.update(attributes)
                else:
                    pending_pax = attributes
                stream.seek(data_offset + _round_block(size))
                continue
            if type_flag == "L":
                if size > MAX_PAX_BYTES:
                    raise ValueError(f"GNU long-name header at {header_offset} exceeds {MAX_PAX_BYTES} bytes")
                pending_long_name = _tar_text(stream.read(size))
                stream.seek(data_offset + _round_block(size))
                continue
            path = pending_pax.pop("path", pending_long_name or name)
            pending_long_name = None
            entries.append({"path": path, "offset": data_offset, "size": size, "type": type_flag})
            stream.seek(data_offset + _round_block(size))
    stat = snapshot.stat()
    return {
        "schema_version": 1,
        "snapshot": snapshot.name,
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "entries": entries,
    }


def load_or_build_index(snapshot: Path, cache_dir: Path) -> dict[str, object]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{snapshot.name}.index.json"
    stat = snapshot.stat()
    try:
        cached = json.loads(cache_file.read_text(encoding="utf-8"))
        if cached.get("size") == stat.st_size and cached.get("mtime_ns") == stat.st_mtime_ns:
            return cached
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    index = build_index(snapshot)
    temporary = cache_file.with_suffix(".tmp")
    temporary.write_text(json.dumps(index, separators=(",", ":")), encoding="utf-8")
    os.replace(temporary, cache_file)
    return index


def select_entries(index: dict[str, object], prefix: str = "", query: str = "", limit: int = 100) -> list[dict[str, object]]:
    if not 1 <= limit <= 1000:
        raise ValueError("limit must be between 1 and 1000.")
    prefix_folded = prefix.casefold()
    query_folded = query.casefold()
    selected = []
    for entry in index["entries"]:
        path = str(entry["path"])
        if prefix and not path.casefold().startswith(prefix_folded):
            continue
        if query and query_folded not in path.casefold():
            continue
        selected.append(entry)
        if len(selected) >= limit:
            break
    return selected


def filter_entries(index: dict[str, object], include_terms: list[str], exclude_terms: list[str], limit: int) -> list[dict[str, object]]:
    """Filter indexed paths without touching archive member bodies."""
    if not 1 <= limit <= 1000:
        raise ValueError("limit must be between 1 and 1000.")
    include = [term.casefold() for term in include_terms if term.strip()]
    exclude = [term.casefold() for term in exclude_terms if term.strip()]
    if not include:
        raise ValueError("include_terms must contain at least one non-empty term.")
    matches = []
    for entry in index["entries"]:
        path = str(entry["path"])
        folded_path = path.casefold()
        if not all(term in folded_path for term in include) or any(term in folded_path for term in exclude):
            continue
        matches.append(entry)
        if len(matches) >= limit:
            break
    return matches


def top_level_summary(index: dict[str, object], limit: int = 100) -> list[dict[str, object]]:
    groups: dict[str, dict[str, int]] = {}
    for entry in index["entries"]:
        path = str(entry["path"])
        top_level = path.split("/", 1)[0] or "."
        group = groups.setdefault(top_level, {"entries": 0, "bytes": 0})
        group["entries"] += 1
        group["bytes"] += int(entry["size"])
    return [{"path": path, **values} for path, values in sorted(groups.items())[:limit]]


def read_member(snapshot: Path, index: dict[str, object], path: str, max_bytes: int) -> bytes:
    if not 1 <= max_bytes <= 500_000:
        raise ValueError("max_bytes must be between 1 and 500000.")
    entry = next((item for item in index["entries"] if item["path"] == path), None)
    if entry is None:
        raise ValueError("Path is not present in the snapshot index.")
    if entry["type"] not in {"0", "", "7"}:
        raise ValueError("The selected path is not a regular file.")
    with snapshot.open("rb") as stream:
        stream.seek(int(entry["offset"]))
        return stream.read(min(int(entry["size"]), max_bytes))
