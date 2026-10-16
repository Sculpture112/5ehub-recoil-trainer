"""Exercise the distributed buttons with the frozen adapter and no Python dependency."""
import json
import os
import subprocess
import unittest
from pathlib import Path
from verify_5ehub_adaptive import AdaptiveTests, PACKAGE, DIR, quote
import patch_5ehub_workshop_package as vpk

class PortableTests(AdaptiveTests):
    def root_command(self,target,script,extra='',ok=True):
        assert target.resolve().is_relative_to(self.root.resolve())
        code="function Get-Process { [CmdletBinding()] param([string]$Name) if($Name -ne 'cs2'){throw 'Unexpected lookup'} }\n"
        code+=extra+'\n'+script
        env=os.environ.copy();env['FIVEHUB_ADAPT_CACHE']=str(self.cache)
        result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-Command',code],
                              capture_output=True,encoding='utf-8',errors='replace',timeout=90,env=env)
        self.assertEqual(result.returncode==0,ok,result.stdout+result.stderr)
        return result
    def button(self,target,action='Install',ok=True):
        return self.root_command(target,f'& {quote(PACKAGE/"patch.ps1")} -Action {action} -TargetPath {quote(target)}',ok=ok)
    def test_portable_buttons_install_repeat_check_and_restore(self):
        target,native=self.fixture()
        self.button(target);self.button(target);self.button(target,'Check')
        state=json.loads((target/'.aim-recoil-patch-backup/state.json').read_text(encoding='utf-8-sig'))
        self.assertEqual(state['version'],'2026.10.16-integrated-12-adaptive')
        self.assertEqual(vpk.sha256(target/DIR),state['patchDirSha256'])
        self.button(target,'Restore')
        self.assertEqual(vpk.sha256(target/DIR),vpk.sha256(native/DIR))
        self.assertFalse((target/state['patchDataFile']).exists())
    def test_launch_automatically_installs_after_native_resource_update(self):
        target,native=self.fixture();self.button(target)
        updated,base_hashes=self.rewrite_native(target,native)
        game=self.root/'game path/cs2.exe';game.parent.mkdir();game.write_bytes(b'not executed')
        starts=self.root/'starts.json'
        mock=f'''
function Get-CimInstance {{}}
function Start-Process {{
 param([string]$FilePath,[string]$ArgumentList,[string]$WorkingDirectory,[string]$WindowStyle,[switch]$PassThru)
 @{{file=$FilePath;args=$ArgumentList}} | ConvertTo-Json -Compress | Add-Content -LiteralPath {quote(starts)} -Encoding UTF8
 if($PassThru){{[pscustomobject]@{{Id=12345}}}}
}}
'''
        self.root_command(target,f'& {quote(PACKAGE/"launch.ps1")} -GamePath {quote(game)} -TargetPath {quote(target)}',extra=mock)
        state=json.loads((target/'.aim-recoil-patch-backup/state.json').read_text(encoding='utf-8-sig'))
        self.assertEqual(state['originalDirSha256'],updated)
        self.assertEqual(vpk.sha256(target/DIR),state['patchDirSha256'])
        self.assert_bases(target,base_hashes)
        records=[json.loads(line) for line in starts.read_text(encoding='utf-8-sig').splitlines()]
        self.assertEqual(len(records),2)
        self.assertIn('-worldwide',records[0]['args'])
        self.assertIn('+map_workshop 3086023598 5e_aimhub',records[0]['args'])
    def test_portable_failure_is_explicit_and_does_not_modify_the_map(self):
        target,native=self.fixture()
        self.rewrite_native(target,native,lambda body:body.replace(b'const ModeMgr =',b'const UnsupportedModeManager =',1))
        before={p.name:vpk.sha256(p) for p in target.glob('*.vpk')}
        result=self.button(target,ok=False)
        self.assertIn('MAP_API_CHANGED',result.stdout)
        self.assertNotIn('ACCESS_DENIED',result.stdout)
        self.assertEqual(before,{p.name:vpk.sha256(p) for p in target.glob('*.vpk')})
        self.assertFalse((target/'.aim-recoil-patch-backup').exists())

if __name__=='__main__':
    suite=unittest.TestSuite(PortableTests(name) for name in PortableTests.__dict__ if name.startswith('test_'))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(not result.wasSuccessful())
