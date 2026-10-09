"""Package this pinned source version; never take files from another workspace."""
from pathlib import Path
import hashlib
import json
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / 'build/5ehub-20261009'
NOTICE = '补丁只会修改训练地图，不会触发任何反作弊.txt'


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    manifest = json.loads((ROOT / 'release/manifest.json').read_text(encoding='utf-8'))
    folder = ROOT / 'dist/5EHub-Recoil-Patch-20261010'
    folder.mkdir(parents=True, exist_ok=True)
    for subdir in ('payload', 'reference', 'helper'):
        (folder / subdir).mkdir(exist_ok=True)
    for name in ('3086023598_dir.vpk', '3086023598_002.vpk'):
        shutil.copy2(LAB / 'patched-workshop/3086023598' / name, folder / 'payload' / name)
    shutil.copy2(LAB / 'workshop-mirror/3086023598/3086023598_dir.vpk', folder / 'reference/3086023598_dir.vpk')
    shutil.copy2(ROOT / 'build/5ehub-assist/dist/5EHubAssist.exe', folder / 'helper/5EHubAssist.exe')
    shutil.copy2(ROOT / 'licenses/Python-LICENSE.txt', folder / 'helper/Python-LICENSE.txt')
    for path in (ROOT / 'installer').iterdir():
        if path.is_file():
            shutil.copy2(path, folder / path.name)
    manifest['patchDirSha256'] = digest(folder / 'payload/3086023598_dir.vpk')
    manifest['patchDataSha256'] = digest(folder / 'payload/3086023598_002.vpk')
    manifest['helper']['sha256'] = digest(folder / 'helper/5EHubAssist.exe')
    (folder / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (folder / NOTICE).write_bytes(b'')
    output = ROOT / 'dist/5EHub-Recoil-Patch.zip'
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(folder.rglob('*')):
            if path.is_file():
                archive.write(path, path.relative_to(folder.parent).as_posix())
    print(json.dumps({'zip': str(output), 'sha256': digest(output), 'version': manifest['version']}))


if __name__ == '__main__':
    main()
