"""Rebuild both executables and package the published adaptive extension."""
import argparse
import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path
from verify_snapshot import verify

ROOT = Path(__file__).resolve().parents[1]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-package', required=True, type=Path,
                        help='Published adaptive ZIP; provides separately licensed compiled map assets')
    args = parser.parse_args()
    if sys.platform != 'win32' or sys.version_info[:2] != (3, 13):
        raise SystemExit('Build the Windows release with Python 3.13.')
    verify(archive_path=args.base_package)
    # Every path below is controlled by this repository, never the installed game.
    build = ROOT / 'build/adaptive-release'
    build.mkdir(parents=True, exist_ok=True)
    executables = {}
    for name, module in [('5EHubAssist', '5ehub_view_bridge'), ('5EHubAdapter', '5ehub_adaptive')]:
        subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile',
                        '--name', name, '--distpath', str(build / 'bin'),
                        '--workpath', str(build / ('work-' + name)), '--specpath', str(build),
                        str(ROOT / 'tools' / (module + '.py'))], cwd=ROOT, check=True)
        executables[name] = (build / 'bin' / (name + '.exe')).read_bytes()
    with zipfile.ZipFile(args.base_package) as archive:
        files = {name: archive.read(name) for name in archive.namelist() if not name.endswith('/')}
    for source in (ROOT / 'installer').iterdir():
        if source.is_file():
            files[source.name] = source.read_bytes()
    files['helper/5EHubAssist.exe'] = executables['5EHubAssist']
    files['adapter/5EHubAdapter.exe'] = executables['5EHubAdapter']
    files['adaptive/extension.js'] = (ROOT / 'src/extension.js').read_bytes()
    files['adaptive/recipe.json'] = (ROOT / 'data/adaptive-recipe.json').read_bytes()
    manifest = json.loads((ROOT / 'release/manifest.json').read_text(encoding='utf-8'))
    manifest['helper']['sha256'] = digest(files['helper/5EHubAssist.exe'])
    manifest['adaptive']['sha256'] = digest(files['adapter/5EHubAdapter.exe'])
    for name in manifest['adaptive']['files']:
        manifest['adaptive']['files'][name] = digest(files[name])
    encoded = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    files['manifest.json'] = files['known-manifest.json'] = encoded
    destination = ROOT / 'dist' / (manifest['version'] + '-source-build.zip')
    destination.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(files.items()):
            archive.writestr(name, data)
    with zipfile.ZipFile(destination) as archive:
        assert archive.testzip() is None
        for name, data in files.items():
            assert archive.read(name) == data, name
    print(json.dumps({'zip': str(destination), 'sha256': digest(destination.read_bytes())}))


if __name__ == '__main__':
    main()
