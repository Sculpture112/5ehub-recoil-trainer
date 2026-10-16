"""Real VPK fixtures: two native versions, future updates, refusal and recovery."""
import importlib
import json
import os
import shutil
import struct
import subprocess
import tempfile
import unittest
import zlib
from dataclasses import replace
from pathlib import Path
import patch_5ehub_workshop_package as vpk

adapter=importlib.import_module('5ehub_adaptive')
ROOT=Path(__file__).resolve().parents[1]
FIXTURES=Path(os.environ.get('FIVEHUB_FIXTURES_ROOT',str(ROOT)))
PACKAGE=Path(os.environ.get('FIVEHUB_PACKAGE_ROOT',str(ROOT/'dist/5EHub-Recoil-Patch-20261016-adaptive')))
TOOLS=ROOT/'installer'
DIR='3086023598_dir.vpk'

def quote(value):return "'"+str(value).replace("'","''")+"'"

class AdaptiveTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='adaptive-test-',dir=ROOT/'build')
        self.root=Path(self.temp.name);self.cache=self.root/'cache'
        self.installer=self.root/'installer';self.installer.mkdir()
        for name in ['patch-lib.ps1','adaptive-lib.ps1']:
            (self.installer/name).write_text((TOOLS/name).read_text(encoding='utf-8-sig'),encoding='utf-8-sig')
    def tearDown(self):
        assert self.root.resolve().is_relative_to((ROOT/'build').resolve())
        self.temp.cleanup()
    def fixture(self,version='20261013'):
        native=FIXTURES/('build/5ehub-'+version+'/workshop-mirror/3086023598')
        target=self.root/version/"中文 空格's library/steamapps/workshop/content/730/3086023598"
        target.mkdir(parents=True)
        for name in ['3086023598_000.vpk','3086023598_001.vpk']:os.link(native/name,target/name)
        shutil.copy2(native/DIR,target/DIR)
        return target,native
    def prepare(self,target,action='Install',package=PACKAGE):
        return Path(adapter.prepare(package,target,self.cache,action)['packageRoot'])
    def patch(self,target,generated,action='Install',extra='',ok=True):
        assert target.resolve().is_relative_to(self.root.resolve())
        code="function Get-Process { [CmdletBinding()] param([string]$Name) if($Name -ne 'cs2'){throw 'Unexpected lookup'} }\n"
        code+=f'. {quote(self.installer/"patch-lib.ps1")}\n'+extra
        code+=f'Invoke-MapPatch -PackageRoot {quote(generated)} -TargetPath {quote(target)} -Action {action}'
        result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-Command',code],
                              capture_output=True,encoding='utf-8',errors='replace',timeout=45)
        self.assertEqual(result.returncode==0,ok,result.stdout+result.stderr)
        return result
    def rewrite_native(self,target,native,script_edit=None,extra_volume=False,geometry=False):
        _,entries,_,_,_=vpk.parse_directory(native/DIR)
        volumes={n:(native/f'3086023598_{n:03}.vpk').read_bytes() for n in (0,1)}
        if script_edit:
            key=vpk.ORIGINAL_SCRIPT_KEY
            raw=vpk.read_entry(native/DIR,entries[key]);row,start,body=adapter.resource_data(raw)
            changed=script_edit(body)
            resource=bytearray(raw[:start]+changed)
            struct.pack_into('<I',resource,0,len(resource));struct.pack_into('<I',resource,row+8,len(changed))
            body=bytes(resource)
        else:
            key='maps/5e_aimhub.vpk' if geometry else 'cfg/crosshair/donk.cfg'
            body=vpk.read_entry(native/DIR,entries[key])+b'\n// new resource fixture\n'
        index=2 if extra_volume else 1
        offset=0 if extra_volume else len(volumes[1])
        volumes[index]=(b'' if extra_volume else volumes[1])+body
        entries[key]=replace(entries[key],archive=index,offset=offset,length=len(body),crc=zlib.crc32(body)&0xffffffff,preload=0,preload_bytes=b'')
        path=target/f'3086023598_{index:03}.vpk'
        if path.exists():path.unlink() # Never write through a hard link to the native fixture.
        path.write_bytes(volumes[index])
        hashes=b''.join(vpk.build_archive_md5(volumes[n],n) for n in sorted(volumes))
        vpk.write_directory(target/DIR,vpk.write_tree(entries),b'',hashes)
        return vpk.sha256(target/DIR),{f'3086023598_{n:03}.vpk':vpk.sha256(target/f'3086023598_{n:03}.vpk') for n in volumes}
    def assert_bases(self,target,hashes):
        for name,expected in hashes.items():self.assertEqual(vpk.sha256(target/name),expected)
    def test_two_real_versions_install_repeat_restore_reinstall(self):
        for version in ['20261009','20261013']:
            with self.subTest(version=version):
                target,native=self.fixture(version);original=vpk.sha256(native/DIR)
                hashes={f'3086023598_{n:03}.vpk':vpk.sha256(native/f'3086023598_{n:03}.vpk') for n in (0,1)}
                generated=self.prepare(target);self.patch(target,generated)
                backup=target/'.aim-recoil-patch-backup'/DIR;stamp=backup.stat().st_mtime_ns
                state=json.loads((backup.parent/'state.json').read_text(encoding='utf-8-sig'))
                self.assertEqual(state['adaptiveReceipt']['schema'],1)
                again=self.prepare(target);self.patch(target,again)
                self.assertEqual(backup.stat().st_mtime_ns,stamp)
                self.patch(target,self.prepare(target,'Restore'),'Restore')
                self.assertEqual(vpk.sha256(target/DIR),original)
                self.assertFalse((target/state['patchDataFile']).exists());self.assert_bases(target,hashes)
                self.patch(target,self.prepare(target));self.assertEqual(vpk.sha256(backup),original)
    def test_resource_update_is_rebased_and_restore_keeps_new_native_map(self):
        target,native=self.fixture();self.patch(target,self.prepare(target))
        old=vpk.sha256(native/DIR)
        updated,hashes=self.rewrite_native(target,native)
        self.patch(target,self.prepare(target));self.assert_bases(target,hashes)
        backup=target/'.aim-recoil-patch-backup'
        self.assertEqual(vpk.sha256(backup/DIR),updated)
        history=list((backup/'history').glob('*/'+DIR))
        self.assertEqual(len(history),1);self.assertEqual(vpk.sha256(history[0]),old)
        self.patch(target,self.prepare(target,'Restore'),'Restore')
        self.assertEqual(vpk.sha256(target/DIR),updated);self.assert_bases(target,hashes)
    def test_unrelated_native_script_update_is_preserved(self):
        target,native=self.fixture()
        self.rewrite_native(target,native,lambda body:body+b'\n// compatible future native script addition\n')
        generated=self.prepare(target);m=json.loads((generated/'manifest.json').read_text(encoding='utf-8'))
        _,entries,*_=vpk.parse_directory(generated/'payload'/DIR)
        e=entries[vpk.ORIGINAL_SCRIPT_KEY]
        raw=(generated/'payload'/m['patchDataFile']).read_bytes()[e.offset:e.offset+e.length]
        body=adapter.resource_data(raw)[2]
        self.assertIn(b'compatible future native script addition',body)
        self.assertTrue(body.endswith((PACKAGE/'adaptive/extension.js').read_bytes()))
    def test_interface_change_refuses_before_map_writes(self):
        target,native=self.fixture()
        self.rewrite_native(target,native,lambda body:body.replace(b'const ModeMgr =',b'const RenamedModeManager =',1))
        before={p.name:vpk.sha256(p) for p in target.glob('*.vpk')}
        with self.assertRaises(adapter.AdaptError) as error:self.prepare(target)
        self.assertEqual(error.exception.code,'MAP_API_CHANGED')
        self.assertEqual(before,{p.name:vpk.sha256(p) for p in target.glob('*.vpk')})
        self.assertFalse((target/'.aim-recoil-patch-backup').exists())
    def test_native_third_volume_is_never_overwritten(self):
        target,native=self.fixture();original,hashes=self.rewrite_native(target,native,extra_volume=True)
        generated=self.prepare(target);m=json.loads((generated/'manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(m['patchDataFile'],'3086023598_003.vpk')
        self.patch(target,generated);self.assert_bases(target,hashes)
        self.patch(target,self.prepare(target,'Restore'),'Restore')
        self.assertEqual(vpk.sha256(target/DIR),original);self.assert_bases(target,hashes)
        self.assertFalse((target/'3086023598_003.vpk').exists())
    def test_damaged_volume_is_not_relabelled_as_compatible(self):
        target,_=self.fixture();path=target/'3086023598_001.vpk';path.unlink();path.write_bytes(b'damaged download')
        before=vpk.sha256(target/DIR)
        with self.assertRaises(adapter.AdaptError) as error:self.prepare(target)
        self.assertEqual(error.exception.code,'MAP_CONTENT_DAMAGED')
        self.assertEqual(vpk.sha256(target/DIR),before)
    def test_restore_after_incompatible_native_update_does_not_require_hooks(self):
        target,native=self.fixture();self.patch(target,self.prepare(target))
        updated,_=self.rewrite_native(target,native,lambda body:body.replace(b'const ModeMgr =',b'const RenamedModeManager =',1))
        self.patch(target,self.prepare(target,'Restore'),'Restore')
        self.assertEqual(vpk.sha256(target/DIR),updated)
        self.assertFalse((target/'3086023598_002.vpk').exists())
        with self.assertRaises(adapter.AdaptError) as error:self.prepare(target)
        self.assertEqual(error.exception.code,'MAP_API_CHANGED')
    def test_unverified_training_scene_is_refused_before_writes(self):
        target,native=self.fixture();self.rewrite_native(target,native,geometry=True)
        before=vpk.sha256(target/DIR)
        with self.assertRaises(adapter.AdaptError) as error:self.prepare(target)
        self.assertEqual(error.exception.code,'MAP_LAYOUT_CHANGED')
        self.assertEqual(vpk.sha256(target/DIR),before)
    def test_known_patch_without_backup_can_be_adopted(self):
        target,native=self.fixture();old=FIXTURES/'dist/5EHub-Recoil-Patch-20261016-map-update/payload'
        for name in [DIR,'3086023598_002.vpk']:shutil.copy2(old/name,target/name)
        generated=self.prepare(target);self.patch(target,generated)
        self.assertEqual(vpk.sha256(target/'.aim-recoil-patch-backup'/DIR),vpk.sha256(native/DIR))
        self.patch(target,self.prepare(target,'Restore'),'Restore')
        self.assertEqual(vpk.sha256(target/DIR),vpk.sha256(native/DIR))
    def test_publish_failure_rolls_back_new_map_and_old_receipt(self):
        target,native=self.fixture();self.patch(target,self.prepare(target))
        updated,_=self.rewrite_native(target,native)
        backup=target/'.aim-recoil-patch-backup';receipt=(backup/'state.json').read_bytes()
        data=(target/'3086023598_002.vpk').read_bytes()
        extra='''$script:failed=$false
function Copy-Item { param([string]$LiteralPath,[string]$Destination)
 if(-not $script:failed -and $LiteralPath.EndsWith('next-dir.vpk')){$script:failed=$true;throw 'simulated publication failure'}
 Microsoft.PowerShell.Management\\Copy-Item -LiteralPath $LiteralPath -Destination $Destination
}
'''
        self.patch(target,self.prepare(target),extra=extra,ok=False)
        self.assertEqual(vpk.sha256(target/DIR),updated)
        self.assertEqual((target/'3086023598_002.vpk').read_bytes(),data)
        self.assertEqual((backup/'state.json').read_bytes(),receipt)

if __name__=='__main__':unittest.main(verbosity=2)
