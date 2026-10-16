"""Verify the published adaptive source and, optionally, its exact release ZIP."""
import argparse
import hashlib
import json
import marshal
import tempfile
import types
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def executable_code(value):
    if isinstance(value, types.CodeType):
        return (value.co_code, tuple(executable_code(x) for x in value.co_consts), value.co_names,
                value.co_varnames, value.co_argcount, value.co_posonlyargcount, value.co_kwonlyargcount,
                value.co_flags, value.co_freevars, value.co_cellvars, value.co_exceptiontable)
    return value


def verify(folder=ROOT, archive_path=None):
    manifest = json.loads((folder / 'release/manifest.json').read_text(encoding='utf-8'))
    evidence = json.loads((folder / 'release/source-verification.json').read_text(encoding='utf-8'))
    assert manifest['version'] == evidence['version']
    assert manifest == json.loads((folder / 'release/known-manifest.json').read_text(encoding='utf-8'))
    for name, expected in evidence['sourceFilesSha256'].items():
        assert digest((folder / name).read_bytes()) == expected, name
    profiles = json.loads((folder / 'data/calibration/weapon-profiles.json').read_text(encoding='utf-8'))
    display = json.loads((folder / 'data/calibration/fixed-camera-display.json').read_text(encoding='utf-8'))['profiles']
    assert {name: len(p['recoil']) for name, p in profiles.items()} == manifest['weaponProfiles']
    assert {name: len(p) for name, p in display.items()} == manifest['weaponProfiles']
    recipe = json.loads((folder / 'data/adaptive-recipe.json').read_text(encoding='utf-8'))
    assert len(recipe['plans']) == 2 and all(len(p['patches']) == 10 for p in recipe['plans'])
    assert recipe['protectedResources']['maps/5e_aimhub.vpk']
    extension = (folder / 'src/extension.js').read_bytes()
    assert digest(extension) == evidence['extensionSha256']
    assert digest(extension) == manifest['adaptive']['files']['adaptive/extension.js']
    assert digest((folder / 'data/adaptive-recipe.json').read_bytes()) == manifest['adaptive']['files']['adaptive/recipe.json']
    assert 'BV1PBp46rEYw' in (folder / 'README.md').read_text(encoding='utf-8')
    if not archive_path:
        return
    assert digest(archive_path.read_bytes()) == evidence['zipSha256'], 'Not the selected release ZIP'
    assert archive_path.stat().st_size == evidence['zipBytes']
    with zipfile.ZipFile(archive_path) as archive:
        assert archive.testzip() is None
        assert json.loads(archive.read('manifest.json')) == manifest
        assert archive.read('known-manifest.json') == archive.read('manifest.json')
        assert archive.read('adaptive/extension.js') == extension
        assert archive.read('adaptive/recipe.json') == (folder / 'data/adaptive-recipe.json').read_bytes()
        for source in (folder / 'installer').iterdir():
            if source.is_file():
                assert archive.read(source.name) == source.read_bytes(), source.name
        for name, expected in manifest['adaptive']['files'].items():
            assert digest(archive.read(name)) == expected, name
        from PyInstaller.archive.readers import CArchiveReader
        with tempfile.TemporaryDirectory() as temporary:
            for exe, module, expected in (
                (manifest['helper']['path'], '5ehub_view_bridge', manifest['helper']['sha256']),
                (manifest['adaptive']['executable'], '5ehub_adaptive', manifest['adaptive']['sha256']),
            ):
                data = archive.read(exe)
                assert digest(data) == expected, exe
                path = Path(temporary) / Path(exe).name
                path.write_bytes(data)
                embedded = marshal.loads(CArchiveReader(str(path)).extract(module))
                source = (folder / 'tools' / (module + '.py')).read_text(encoding='utf-8-sig')
                assert executable_code(embedded) == executable_code(compile(source, '<source>', 'exec')), module


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--zip', type=Path)
    args = parser.parse_args()
    verify(archive_path=args.zip)
    print('PASS: adaptive source, 17 profiles, tutorial' + (', exact release ZIP and executable code' if args.zip else ''))
