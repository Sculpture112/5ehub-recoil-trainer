"""Build an additive, reversible patch for the mirrored 5EHub Workshop VPK."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib
import json
import shutil
import struct
import sys
import zlib
from blake3 import blake3

ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / "build/5ehub-clean-baseline"
SOURCE_PACKAGE = LAB / "workshop-mirror/3086023598"
OUTPUT_PACKAGE = LAB / "patched-workshop/3086023598"
RECOIL_PACKAGE = Path(
    r"C:\Program Files (x86)\Steam\steamapps\workshop\content\730\3100869952\3100869952_dir.vpk"
)
COMPILED_SCRIPT = LAB / "compiled/5e_aimhub.workshop-patched.vjs_c"
REPORT = LAB / "patched-workshop/package-patch-report.json"
ORIGINAL_SCRIPT_KEY = "scripts/vscripts/build/7ychu5/5e_aimhub/5e_aimhub.vjs_c"
NEW_ARCHIVE_INDEX = 2
EXPECTED_ORIGINAL_ENTRIES = 882
MAGIC = 0x55AA1234
ENTRY = struct.Struct("<IHHIIH")
ARCHIVE_MD5 = struct.Struct("<HHII16s")

ASSET_KEYS = (
    "models/ulletical/recoil_master/patterns/dot_single_001.vmdl_c",
    "materials/ulletical/colors/white.vmat_c",
    "materials/ulletical/colors/white_vmat_g_tcolor_7ab53e0a.vtex_c",
)


@dataclass(frozen=True)
class VpkEntry:
    key: str
    crc: int
    preload: int
    archive: int
    offset: int
    length: int
    terminator: int
    preload_bytes: bytes


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_directory(path: Path) -> tuple[bytes, dict[str, VpkEntry], bytes, bytes, bytes]:
    data = path.read_bytes()
    if len(data) < 28:
        raise ValueError(f"Truncated VPK directory: {path}")
    magic, version, tree_size, file_data_size, archive_md5_size, other_md5_size, signature_size = struct.unpack_from(
        "<7I", data
    )
    if magic != MAGIC or version != 2:
        raise ValueError(f"Expected a VPK v2 directory: {path}")
    tree_start = 28
    tree_end = tree_start + tree_size
    data_end = tree_end + file_data_size
    archive_end = data_end + archive_md5_size
    other_end = archive_end + other_md5_size
    if other_end + signature_size != len(data):
        raise ValueError("VPK sections do not match file length")
    if file_data_size:
        raise ValueError("Source package has embedded file data; refusing unsafe repack")
    tree = data[tree_start:tree_end]
    archive_md5 = data[data_end:archive_end]
    other_md5 = data[archive_end:other_end]
    signature = data[other_end:]
    if len(archive_md5) % ARCHIVE_MD5.size or len(other_md5) != 48:
        raise ValueError("Unexpected VPK checksum section layout")

    cursor = 0

    def read_cstring() -> str:
        nonlocal cursor
        try:
            end = tree.index(0, cursor)
        except ValueError as error:
            raise ValueError("Unterminated string in VPK tree") from error
        result = tree[cursor:end].decode("utf-8")
        cursor = end + 1
        return result

    entries: dict[str, VpkEntry] = {}
    while True:
        extension = read_cstring()
        if not extension:
            break
        while True:
            directory = read_cstring()
            if not directory:
                break
            while True:
                filename = read_cstring()
                if not filename:
                    break
                if cursor + ENTRY.size > len(tree):
                    raise ValueError("Truncated VPK entry")
                crc, preload, archive, offset, length, terminator = ENTRY.unpack_from(tree, cursor)
                cursor += ENTRY.size
                if cursor + preload > len(tree) or terminator != 0xFFFF:
                    raise ValueError("Invalid VPK entry terminator or preload length")
                preload_bytes = tree[cursor:cursor + preload]
                cursor += preload
                key = (directory + "/" if directory != " " else "") + filename
                if extension != " ":
                    key += "." + extension
                if key in entries:
                    raise ValueError(f"Duplicate VPK path: {key}")
                entries[key] = VpkEntry(
                    key, crc, preload, archive, offset, length, terminator, preload_bytes
                )
    if cursor != len(tree):
        raise ValueError("VPK tree parser did not consume the declared tree")
    return tree, entries, archive_md5, other_md5, data


def split_key(key: str) -> tuple[str, str, str]:
    path, slash, filename = key.rpartition("/")
    if not slash:
        path = " "
    basename, dot, extension = filename.rpartition(".")
    if not dot:
        basename, extension = filename, " "
    return extension or " ", path or " ", basename


def write_tree(entries: dict[str, VpkEntry]) -> bytes:
    groups: dict[str, dict[str, list[VpkEntry]]] = {}
    for entry in entries.values():
        extension, directory, _ = split_key(entry.key)
        groups.setdefault(extension, {}).setdefault(directory, []).append(entry)

    tree = bytearray()
    for extension in sorted(groups):
        tree.extend(extension.encode("utf-8") + b"\0")
        for directory in sorted(groups[extension]):
            tree.extend(directory.encode("utf-8") + b"\0")
            for entry in sorted(groups[extension][directory], key=lambda item: split_key(item.key)[2]):
                basename = split_key(entry.key)[2]
                tree.extend(basename.encode("utf-8") + b"\0")
                tree.extend(
                    ENTRY.pack(
                        entry.crc,
                        entry.preload,
                        entry.archive,
                        entry.offset,
                        entry.length,
                        entry.terminator,
                    )
                )
                tree.extend(entry.preload_bytes)
            tree.extend(b"\0")
        tree.extend(b"\0")
    tree.extend(b"\0")
    return bytes(tree)


def read_asset_entries() -> dict[str, bytes]:
    sys.path.insert(0, str(ROOT / "tools"))
    import vpk

    contents = vpk.read(RECOIL_PACKAGE)
    return {key: contents[key] for key in ASSET_KEYS}


def build_archive_md5(volume: bytes, archive_index: int) -> bytes:
    result = bytearray()
    for offset in range(0, len(volume), 1024 * 1024):
        block = volume[offset:offset + 1024 * 1024]
        result.extend(
            ARCHIVE_MD5.pack(
                archive_index,
                1,
                offset,
                len(block),
                blake3(block).digest(length=16),
            )
        )
    return bytes(result)


def write_directory(path: Path, tree: bytes, volume: bytes, archive_md5: bytes) -> None:
    header = struct.pack(
        "<7I", MAGIC, 2, len(tree), 0, len(archive_md5), 48, 0
    )
    prefix = header + tree + archive_md5
    other_md5 = hashlib.md5(tree).digest() + hashlib.md5(archive_md5).digest()
    other_md5 += hashlib.md5(prefix + other_md5).digest()
    path.write_bytes(prefix + other_md5)


def read_entry(path: Path, entry: VpkEntry) -> bytes:
    if entry.archive == 0x7FFF:
        raise ValueError("Unexpected embedded entry in this split VPK")
    volume_path = path.with_name(path.stem.removesuffix("_dir") + f"_{entry.archive:03}.vpk")
    with volume_path.open("rb") as stream:
        stream.seek(entry.offset)
        payload = entry.preload_bytes + stream.read(entry.length)
    if len(payload) != entry.preload + entry.length or zlib.crc32(payload) & 0xFFFFFFFF != entry.crc:
        raise ValueError(f"VPK payload CRC/size check failed: {entry.key}")
    return payload


def validate_md5_records(blob: bytes, volumes: dict[int, bytes]) -> None:
    if len(blob) % ARCHIVE_MD5.size:
        raise ValueError("Archive MD5 section length is invalid")
    coverage: dict[int, int] = {archive: 0 for archive in volumes}
    for offset in range(0, len(blob), ARCHIVE_MD5.size):
        archive, flags, start, length, digest = ARCHIVE_MD5.unpack_from(blob, offset)
        volume = volumes.get(archive)
        if flags != 1 or volume is None or start != coverage.get(archive, -1):
            raise ValueError(f"Unexpected archive MD5 record for volume {archive} at {start}")
        block = volume[start:start + length]
        if len(block) != length or blake3(block).digest(length=16) != digest:
            raise ValueError(f"Archive chunk hash mismatch in volume {archive} at {start}")
        coverage[archive] = start + length
    if coverage != {archive: len(volume) for archive, volume in volumes.items()}:
        raise ValueError(f"Archive MD5 coverage mismatch: {coverage}")


def main() -> None:
    if not COMPILED_SCRIPT.is_file():
        raise FileNotFoundError(COMPILED_SCRIPT)
    if not RECOIL_PACKAGE.is_file():
        raise FileNotFoundError(RECOIL_PACKAGE)

    source_dir = SOURCE_PACKAGE / "3086023598_dir.vpk"
    _, source_entries, source_archive_md5, _, source_bytes = parse_directory(source_dir)
    if len(source_entries) != EXPECTED_ORIGINAL_ENTRIES:
        raise ValueError(f"Expected {EXPECTED_ORIGINAL_ENTRIES} original Workshop entries, got {len(source_entries)}")
    if ORIGINAL_SCRIPT_KEY not in source_entries:
        raise ValueError("Original Workshop main VJS_C entry is missing")
    if any(key in source_entries for key in ASSET_KEYS):
        raise ValueError("One or more RecoilMaster assets already exist in the original package")

    source_volumes = {
        0: (SOURCE_PACKAGE / "3086023598_000.vpk").read_bytes(),
        1: (SOURCE_PACKAGE / "3086023598_001.vpk").read_bytes(),
    }
    validate_md5_records(source_archive_md5, source_volumes)

    additions = read_asset_entries()
    if set(additions) != set(ASSET_KEYS):
        raise ValueError("RecoilMaster package is missing one or more required original assets")
    replacements = {ORIGINAL_SCRIPT_KEY: COMPILED_SCRIPT.read_bytes(), **additions}
    new_archive = bytearray()
    output_entries = dict(source_entries)
    for key, payload in replacements.items():
        offset = len(new_archive)
        new_archive.extend(payload)
        extension, directory, basename = split_key(key)
        normalized_key = (directory + "/" if directory != " " else "") + basename
        if extension != " ":
            normalized_key += "." + extension
        if normalized_key != key:
            raise ValueError(f"Cannot normalize VPK path: {key}")
        output_entries[key] = VpkEntry(
            key=key,
            crc=zlib.crc32(payload) & 0xFFFFFFFF,
            preload=0,
            archive=NEW_ARCHIVE_INDEX,
            offset=offset,
            length=len(payload),
            terminator=0xFFFF,
            preload_bytes=b"",
        )

    new_archive_bytes = bytes(new_archive)
    new_md5 = build_archive_md5(new_archive_bytes, NEW_ARCHIVE_INDEX)
    archive_md5 = source_archive_md5 + new_md5
    tree = write_tree(output_entries)

    OUTPUT_PACKAGE.mkdir(parents=True, exist_ok=True)
    for suffix in ("_000.vpk", "_001.vpk"):
        shutil.copy2(SOURCE_PACKAGE / f"3086023598{suffix}", OUTPUT_PACKAGE / f"3086023598{suffix}")
    shutil.copy2(SOURCE_PACKAGE / "publish_data.txt", OUTPUT_PACKAGE / "publish_data.txt")
    (OUTPUT_PACKAGE / "3086023598_002.vpk").write_bytes(new_archive_bytes)
    write_directory(OUTPUT_PACKAGE / "3086023598_dir.vpk", tree, new_archive_bytes, archive_md5)

    output_dir = OUTPUT_PACKAGE / "3086023598_dir.vpk"
    _, parsed_output_entries, parsed_archive_md5, _, _ = parse_directory(output_dir)
    expected_count = len(source_entries) + len(ASSET_KEYS)
    if len(parsed_output_entries) != expected_count or set(parsed_output_entries) != set(source_entries) | set(ASSET_KEYS):
        raise ValueError("Patched VPK entry inventory does not match expected inventory")
    for key, original_entry in source_entries.items():
        if key == ORIGINAL_SCRIPT_KEY:
            continue
        if parsed_output_entries[key] != original_entry:
            raise ValueError(f"Original VPK entry metadata changed unexpectedly: {key}")
    output_volumes = {
        0: (OUTPUT_PACKAGE / "3086023598_000.vpk").read_bytes(),
        1: (OUTPUT_PACKAGE / "3086023598_001.vpk").read_bytes(),
        NEW_ARCHIVE_INDEX: new_archive_bytes,
    }
    validate_md5_records(parsed_archive_md5, output_volumes)
    for archive in (0, 1):
        if output_volumes[archive] != source_volumes[archive]:
            raise ValueError(f"Original outer volume {archive} was not copied byte-for-byte")

    # The project's VPK reader checks the CRC and size of every entry.
    sys.path.insert(0, str(ROOT / "tools"))
    import vpk

    all_payloads = vpk.read(output_dir)
    if len(all_payloads) != expected_count:
        raise ValueError(f"VPK round-trip found {len(all_payloads)} payloads instead of {expected_count}")
    if all_payloads[ORIGINAL_SCRIPT_KEY] != COMPILED_SCRIPT.read_bytes():
        raise ValueError("Compiled script payload did not survive VPK round-trip")
    for key, payload in additions.items():
        if all_payloads[key] != payload:
            raise ValueError(f"RecoilMaster asset did not survive VPK round-trip: {key}")
    for key in ("maps/5e_aimhub.vpk", "maps/officialmapshub.vpk", "maps/skybox/skybox.vpk"):
        if read_entry(source_dir, source_entries[key]) != read_entry(output_dir, parsed_output_entries[key]):
            raise ValueError(f"Nested map resource changed: {key}")

    report = {
        "sourcePackageMirror": str(SOURCE_PACKAGE),
        "outputPackage": str(OUTPUT_PACKAGE),
        "originalEntryCount": len(source_entries),
        "patchedEntryCount": len(parsed_output_entries),
        "replacedEntry": ORIGINAL_SCRIPT_KEY,
        "addedEntries": list(ASSET_KEYS),
        "nestedMapEntriesPreservedByteForByte": [
            "maps/5e_aimhub.vpk",
            "maps/officialmapshub.vpk",
            "maps/skybox/skybox.vpk",
        ],
        "archiveLayout": {
            "originalVolumesPreservedByteForByte": [
                "3086023598_000.vpk",
                "3086023598_001.vpk",
            ],
            "newVolume": "3086023598_002.vpk",
            "newVolumePayloadBytes": len(new_archive_bytes),
            "originalArchiveMd5RecordsPreserved": len(source_archive_md5) // ARCHIVE_MD5.size,
            "newArchiveMd5Records": len(new_md5) // ARCHIVE_MD5.size,
            "originalSignatureSectionBytes": struct.unpack_from("<I", source_bytes, 24)[0],
            "patchedSignatureSectionBytes": 0,
            "signatureNote": "The original VPK signature cannot remain valid after local edits; the patched directory VPK is unsigned.",
        },
        "sha256": {
            path.name: sha256(path)
            for path in sorted(OUTPUT_PACKAGE.glob("*"))
            if path.is_file()
        },
    }
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
