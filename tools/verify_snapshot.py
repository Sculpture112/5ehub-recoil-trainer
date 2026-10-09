"""Verify source/catalog consistency and optionally the exact historical ZIP."""
import argparse
import hashlib
import json
import marshal
import tempfile
import types
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def executable_code(code):
    if isinstance(code, types.CodeType):
        return (code.co_code, tuple(executable_code(x) for x in code.co_consts), code.co_names,
                code.co_varnames, code.co_argcount, code.co_posonlyargcount, code.co_kwonlyargcount,
                code.co_flags, code.co_freevars, code.co_cellvars, code.co_exceptiontable)
    return code


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--zip', type=Path)
    args = parser.parse_args()
    manifest = json.loads((ROOT / 'release/manifest.json').read_text(encoding='utf-8'))
    evidence = json.loads((ROOT / 'release/source-verification.json').read_text(encoding='utf-8'))
    profiles = json.loads((ROOT / 'data/calibration/weapon-profiles.json').read_text(encoding='utf-8'))
    display = json.loads((ROOT / 'data/calibration/fixed-camera-display.json').read_text(encoding='utf-8'))['profiles']
    assert {name: len(p['recoil']) for name, p in profiles.items()} == manifest['weaponProfiles']
    assert {name: len(p) for name, p in display.items()} == manifest['weaponProfiles']
    assert manifest['version'] == evidence['version'] == '2026.10.10-integrated-6'
    helper_source = (ROOT / 'tools/5ehub_view_bridge.py').read_text(encoding='utf-8')
    assert 'TrainingGuard' not in helper_source
    assert 'akbridgeguard' not in (ROOT / 'src/diagnostics/5ehub-local-guide.js').read_text(encoding='utf-8')
    assert 'BV1PBp46rEYw' in (ROOT / 'README.md').read_text(encoding='utf-8')
    if args.zip:
        assert hashlib.sha256(args.zip.read_bytes()).hexdigest() == evidence['zipSha256'], 'Not the selected historical ZIP'
        with zipfile.ZipFile(args.zip) as archive:
            assert archive.testzip() is None
            prefix = archive.namelist()[0].split('/')[0] + '/'
            assert json.loads(archive.read(prefix + 'manifest.json')) == manifest
            for path in (ROOT / 'installer').iterdir():
                if path.is_file():
                    assert archive.read(prefix + path.name) == path.read_bytes(), path.name
            from PyInstaller.archive.readers import CArchiveReader
            with tempfile.TemporaryDirectory() as folder:
                exe = Path(folder) / 'helper.exe'
                exe.write_bytes(archive.read(prefix + 'helper/5EHubAssist.exe'))
                assert hashlib.sha256(exe.read_bytes()).hexdigest() == manifest['helper']['sha256']
                embedded = marshal.loads(CArchiveReader(str(exe)).extract('5ehub_view_bridge'))
                assert executable_code(embedded) == executable_code(compile(helper_source, '<snapshot>', 'exec'))
            import patch_5ehub_workshop_package as vpk
            with tempfile.TemporaryDirectory() as folder:
                directory = Path(folder) / '3086023598_dir.vpk'
                directory.write_bytes(archive.read(prefix + 'payload/3086023598_dir.vpk'))
                _, entries, _, _, _ = vpk.parse_directory(directory)
                entry = entries[vpk.ORIGINAL_SCRIPT_KEY]
                data = archive.read(prefix + 'payload/3086023598_002.vpk')
                script = entry.preload_bytes + data[entry.offset:entry.offset + entry.length]
                assert hashlib.sha256(script).hexdigest() == evidence['scriptPayloadSha256']
    print('PASS: integrated-6 source snapshot, 16 weapon profiles, tutorial link' +
          (', exact ZIP/installer/helper/script correspondence' if args.zip else ''))


if __name__ == '__main__':
    main()
