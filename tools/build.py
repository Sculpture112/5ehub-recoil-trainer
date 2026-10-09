"""Build the integrated-6 source using locally installed Workshop content."""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / 'build/5ehub-20261009'
SCRIPT = 'scripts/vscripts/build/7ychu5/5e_aimhub/5e_aimhub.vjs_c'
SOURCE_SHA = '7f6176ba68a22b2a43617214422a43b426e328a697131277c285507a522f45e9'
OUTPUT_SHA = 'aade6ff3e2d035c00f58e25bbf5a9ef954127ef4cd320eb5f36e6fecaa6d0e7f'


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def run(args):
    subprocess.run([str(arg) for arg in args], cwd=ROOT, check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--game-root', required=True, type=Path, help='Counter-Strike Global Offensive directory')
    parser.add_argument('--workshop-root', required=True, type=Path, help='workshop/content/730 directory')
    parser.add_argument('--source2viewer', required=True, type=Path)
    parser.add_argument('--stage', choices=('source', 'map', 'helper', 'all'), default='all')
    args = parser.parse_args()
    manifest = json.loads((ROOT / 'release/manifest.json').read_text(encoding='utf-8'))
    if args.stage in ('source', 'map', 'all'):
        original = args.workshop_root / manifest['mapId']
        mirror = LAB / 'workshop-mirror' / manifest['mapId']
        mirror.mkdir(parents=True, exist_ok=True)
        for name, expected in manifest['baseVolumes'].items():
            if digest(original / name) != expected:
                raise ValueError('Original map version mismatch: ' + name)
            shutil.copy2(original / name, mirror / name)
        directory = next((path for path in [original / '3086023598_dir.vpk', original / '.aim-recoil-patch-backup/3086023598_dir.vpk']
                          if path.is_file() and digest(path) == manifest['originalDirSha256']), None)
        if directory is None:
            raise ValueError('Matching original map directory or backup required')
        shutil.copy2(directory, mirror / directory.name)
        publish = original / 'publish_data.txt'
        if publish.is_file():
            shutil.copy2(publish, mirror / publish.name)
        else:
            (mirror / 'publish_data.txt').write_text('', encoding='utf-8')
        source = LAB / 'source/5e_aimhub.original.js'
        source.parent.mkdir(parents=True, exist_ok=True)
        run([args.source2viewer.resolve(), '-i', mirror / '3086023598_dir.vpk', '-f', SCRIPT, '-d', '-o', source])
        if digest(source) != SOURCE_SHA:
            raise ValueError('Decompiled original script does not match this source snapshot')
        import prepare_5ehub_workshop_patch as prepare
        prepare.LAB = LAB
        prepare.SOURCE = source
        prepare.OUTPUT = LAB / 'source/5e_aimhub.workshop-patched.js'
        prepare.REPORT = LAB / 'source/workshop-source-patch.json'
        prepare.main()
        if digest(prepare.OUTPUT) != OUTPUT_SHA:
            raise ValueError('Generated script differs from the selected ZIP version')
        if args.stage == 'source':
            return
        addon = 'codex_5ehub_oss_integrated6'
        relative = Path('maps/scripts/vscripts/build/7ychu5/5e_aimhub/5e_aimhub.vjs')
        compile_input = args.game_root / 'content/csgo_addons' / addon / relative
        compile_input.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(prepare.OUTPUT, compile_input)
        run([args.game_root / 'game/bin/win64/resourcecompiler.exe', '-i', compile_input, '-game', args.game_root / 'game/csgo'])
        compiled = LAB / 'compiled/5e_aimhub.workshop-patched.vjs_c'
        compiled.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(args.game_root / 'game/csgo_addons' / addon / relative.with_suffix('.vjs_c'), compiled)
        import patch_5ehub_workshop_package as package
        package.LAB = LAB
        package.SOURCE_PACKAGE = mirror
        package.OUTPUT_PACKAGE = LAB / 'patched-workshop/3086023598'
        package.COMPILED_SCRIPT = compiled
        package.REPORT = LAB / 'patched-workshop/package-patch-report.json'
        package.EXPECTED_ORIGINAL_ENTRIES = 886
        package.RECOIL_PACKAGE = args.workshop_root / '3100869952/3100869952_dir.vpk'
        package.main()
    if args.stage in ('helper', 'all'):
        if sys.version_info[:2] != (3, 13):
            raise ValueError('Use Python 3.13 for this release')
        run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile', '--name', '5EHubAssist',
             '--distpath', ROOT / 'build/5ehub-assist/dist', '--workpath', ROOT / 'build/5ehub-assist/work',
             '--specpath', ROOT / 'build/5ehub-assist', ROOT / 'tools/5ehub_view_bridge.py'])
    if args.stage == 'all':
        import package_release
        package_release.main()


if __name__ == '__main__':
    main()
