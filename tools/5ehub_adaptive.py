"""Prepare verified local payloads; map writes remain in the transactional installer."""
from pathlib import Path
from dataclasses import replace
import argparse
import copy
import hashlib
import json
import os
import re
import shutil
import struct
import sys
import tempfile
import zlib
import patch_5ehub_workshop_package as vpk

MAP='3086023598'
DIR=MAP+'_dir.vpk'
MARKER='// Workshop-local 5EHub AK guide.'

class AdaptError(RuntimeError):
    def __init__(self,code,message):super().__init__(message);self.code=code

def fail(code,message):raise AdaptError(code,message)

def sha(path):return vpk.sha256(path)

def read_json(path):
    try:return json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError,ValueError) as error:fail('ADAPT_METADATA_INVALID',f'无法读取版本或备份记录：{path.name}；{error}')

def bounded(root,key):
    path=(root/key).resolve()
    if not path.is_relative_to(root.resolve()):fail('ADAPT_PATH_INVALID','资源路径超出补丁包。')
    return path

def resource_data(raw):
    if len(raw)<16:fail('MAP_RESOURCE_INVALID','地图主脚本资源头不完整。')
    total,version,_,relative,count=struct.unpack_from('<IHHII',raw)
    if total!=len(raw) or version!=12 or count>64:fail('MAP_RESOURCE_UNSUPPORTED','地图脚本资源格式变化，暂不能自动适配。')
    for n in range(count):
        row=8+relative+n*12
        if row+12>len(raw):fail('MAP_RESOURCE_INVALID','地图脚本资源表越界。')
        tag,offset,length=struct.unpack_from('<4sII',raw,row)
        if tag==b'DATA':
            start=row+4+offset
            if start+length!=len(raw):fail('MAP_RESOURCE_UNSUPPORTED','主脚本 DATA 不在资源末尾，未写入地图。')
            return row,start,raw[start:]
    fail('MAP_RESOURCE_INVALID','主脚本缺少 DATA。')

def patch_script(raw,spec,extension):
    row,start,body=resource_data(raw)
    try:source=body.decode('utf-8').replace('\r','')
    except UnicodeDecodeError:fail('MAP_SCRIPT_ENCODING_UNSUPPORTED','主脚本编码变化。')
    if MARKER in source or '__codexPreferencesReady' in source:
        fail('MAP_ALREADY_MODIFIED','主脚本已有训练补丁，但缺少可验证的配套备份；未叠加修改。')
    missing=[name for name in spec['required'] if name not in source]
    if missing:fail('MAP_API_CHANGED','新版原图缺少训练接口：'+', '.join(missing))
    failures=[]
    for plan in spec['plans']:
        edited=source
        for number,patch in enumerate(plan['patches']):
            hits=edited.count(patch['old'])
            if hits!=1:
                failures.append(f"{plan['label']} 接入点 {number+1} 匹配 {hits} 处")
                break
            edited=edited.replace(patch['old'],patch['new'],1)
        else:
            data=edited.rstrip().encode('utf-8')+b'\n\n'+extension
            payload=bytearray(raw[:start]+data)
            struct.pack_into('<I',payload,0,len(payload));struct.pack_into('<I',payload,row+8,len(data))
            return bytes(payload),plan['label']
    fail('MAP_HOOK_CHANGED','原图关键接入点变化，自动适配已停止；'+ '；'.join(failures))

def entry_bytes(entry,volumes):
    if entry.archive not in volumes:fail('MAP_VOLUME_MISSING',f'地图数据卷 {entry.archive:03} 缺失。')
    body=entry.preload_bytes+volumes[entry.archive][entry.offset:entry.offset+entry.length]
    if len(body)!=entry.preload+entry.length or zlib.crc32(body)&0xffffffff!=entry.crc:
        fail('MAP_CONTENT_DAMAGED',f'原图资源校验失败：{entry.key}。请等待下载完成，或验证/重新下载原图。')
    return body

def parse(path):
    try:
        parsed=vpk.parse_directory(path)
        tree,_,records,other,raw=parsed
        header=struct.unpack_from('<7I',raw)
        end=28+header[2]+header[3]+header[4]
        if (hashlib.md5(tree).digest()!=other[:16] or hashlib.md5(records).digest()!=other[16:32]
                or hashlib.md5(raw[:end+32]).digest()!=other[32:]):
            fail('MAP_INDEX_DAMAGED','地图索引自身校验失败；未写入地图。')
        return parsed
    except (OSError,ValueError,struct.error,UnicodeError) as error:
        fail('MAP_INDEX_UNSUPPORTED','地图索引无法验证：'+str(error))

def known_records(manifest):
    records=copy.deepcopy(manifest.get('previousMaps',[]))
    original=manifest['originalDirSha256']
    current=next((x for x in records if x['originalDirSha256']==original),None)
    if current is None:
        current={'originalDirSha256':original,'patches':[]};records.append(current)
    pair={key:manifest[key] for key in ('patchDirSha256','patchDataSha256')}
    if pair not in current['patches']:current['patches'].append(pair)
    return records

def validate_receipt(target,state,records):
    if not state:return
    keys=('schema','originalDirSha256','patchDirSha256','patchDataSha256')
    if not all(key in state for key in keys) or state['schema']!=1:
        fail('BACKUP_MANIFEST_INVALID','地图备份记录缺少必要信息。')
    if any(not re.fullmatch('[0-9a-fA-F]{64}',str(state[key])) for key in keys[1:]):
        fail('BACKUP_MANIFEST_INVALID','地图备份校验信息无效。')
    data_name=state.get('patchDataFile',MAP+'_002.vpk')
    if not re.fullmatch(MAP+r'_\d{3}\.vpk',str(data_name)) or int(data_name[-7:-4])<2:
        fail('BACKUP_MANIFEST_INVALID','备份记录中的新增分卷路径无效。')
    original=target/'.aim-recoil-patch-backup'/DIR
    if not original.is_file() or sha(original)!=state['originalDirSha256']:
        fail('BACKUP_CONTENT_MISMATCH','原图备份缺失或损坏，未覆盖当前地图。')
    pair={key:state[key] for key in ('patchDirSha256','patchDataSha256')}
    known=any(record['originalDirSha256']==state['originalDirSha256'] and pair in record['patches'] for record in records)
    adaptive=state.get('adaptiveReceipt',{})
    if not known and not (adaptive.get('schema')==1 and re.fullmatch('[0-9a-f]{64}',adaptive.get('recipeSha256',''))):
        fail('BACKUP_PATCH_UNKNOWN','旧补丁无法识别，请保留备份和错误报告。')
    if not known:
        existing=next((record for record in records if record['originalDirSha256']==state['originalDirSha256']),None)
        if existing is None:records.append({'originalDirSha256':state['originalDirSha256'],'patches':[pair]})
        else:existing['patches'].append(pair)

def prepare(package,target,cache_root,action='Install'):
    package=Path(package).resolve();target=Path(target).resolve();cache_root=Path(cache_root).resolve()
    if target.name!=MAP or target.parent.name!='730':fail('MAP_PATH_INVALID','目标不是 730/3086023598 地图目录。')
    manifest=read_json(package/'manifest.json');adaptive=manifest.get('adaptive',{})
    if manifest.get('mapId')!=MAP or adaptive.get('schema')!=1:fail('ADAPT_PACKAGE_INVALID','自动适配包格式无效。')
    for relative,expected in adaptive['files'].items():
        path=bounded(package,relative)
        if not path.is_file() or sha(path)!=expected:fail('ADAPT_PACKAGE_DAMAGED','自动适配资源损坏或缺失：'+relative)
    helper=bounded(package,manifest['helper']['path'])
    if not helper.is_file() or sha(helper)!=manifest['helper']['sha256']:fail('ADAPT_PACKAGE_DAMAGED','辅助程序损坏，未写入地图。')
    if getattr(sys,'frozen',False) and sha(Path(sys.executable))!=adaptive['sha256']:
        fail('ADAPT_PACKAGE_DAMAGED','自动适配程序与版本清单不匹配。')
    spec=read_json(package/'adaptive/recipe.json')
    extension=(package/'adaptive/extension.js').read_bytes()
    records=known_records(manifest)
    state_path=target/'.aim-recoil-patch-backup/state.json'
    state=read_json(state_path) if state_path.exists() else None
    validate_receipt(target,state,records)
    live=target/DIR
    if not live.is_file():fail('MAP_DOWNLOAD_INCOMPLETE','原地图目录卷未下载完成。')
    live_sha=sha(live);original_path=live;adopt=None
    if state and live_sha==state['patchDirSha256'] and state.get('installed',True):
        old_data=target/state.get('patchDataFile',MAP+'_002.vpk')
        if not old_data.is_file() or sha(old_data)!=state['patchDataSha256']:
            fail('PATCH_PAIR_MISMATCH','已安装补丁的目录卷和新增数据卷不配套。')
        original_path=state_path.parent/DIR
    elif live_sha not in {record['originalDirSha256'] for record in records}:
        for record in records:
            for pair in record['patches']:
                if live_sha==pair['patchDirSha256']:
                    residue=target/(MAP+'_002.vpk')
                    if not residue.is_file() or sha(residue)!=pair['patchDataSha256']:
                        fail('PATCH_PAIR_MISMATCH','旧补丁的数据卷缺失或不配套。')
                    reference=package/'adaptive/baselines'/(record['originalDirSha256']+'.vpk')
                    if not reference.is_file():fail('BACKUP_REQUIRED','旧补丁需要原版目录备份才能自动迁移。')
                    original_path=reference
                    if not state:adopt={**pair,'patchDataFile':MAP+'_002.vpk'}
    _,entries,archive_md5,_,original_index=parse(original_path)
    if spec['scriptKey'] not in entries or 'maps/5e_aimhub.vpk' not in entries:
        fail('MAP_IDENTITY_UNVERIFIED','索引未包含预期的 5EHub 地图与主脚本。')
    archives=sorted({entry.archive for entry in entries.values()})
    if any(index>=1000 for index in archives) or not {0,1}.issubset(archives):
        fail('MAP_LAYOUT_UNSUPPORTED','地图分卷结构暂不支持自动适配。')
    volumes={};base_hashes={};stamps={}
    for index in archives:
        path=target/f'{MAP}_{index:03}.vpk'
        if not path.is_file():fail('MAP_DOWNLOAD_INCOMPLETE','原地图缺少 '+path.name)
        stat=path.stat();stamps[path.name]=(stat.st_size,stat.st_mtime_ns)
        volumes[index]=path.read_bytes();base_hashes[path.name]=hashlib.sha256(volumes[index]).hexdigest()
    try:vpk.validate_md5_records(archive_md5,volumes)
    except ValueError as error:fail('MAP_CONTENT_DAMAGED','原图数据卷与索引校验不一致：'+str(error))
    for entry in entries.values():entry_bytes(entry,volumes)
    native=entry_bytes(entries[spec['scriptKey']],volumes)
    recipe_hash=sha(package/'adaptive/recipe.json')
    # A current adaptive install can always be restored from its exact receipt,
    # even if a future package no longer recognizes that script's hook plan.
    restore_native=action=='Restore' and not (state and live_sha==state['patchDirSha256'])
    if action=='Restore' and state and live_sha==state['patchDirSha256']:
        patched=entry_bytes(parse(live)[1][spec['scriptKey']],{**volumes,int(state.get('patchDataFile',MAP+'_002.vpk').split('_')[-1].split('.')[0]):(target/state.get('patchDataFile',MAP+'_002.vpk')).read_bytes()})
        plan='verified-installed-receipt'
    elif restore_native:patched,plan=native,'restore-native-only'
    else:
        for key,expected in spec.get('protectedResources',{}).items():
            if key not in entries or hashlib.sha256(entry_bytes(entries[key],volumes)).hexdigest() not in expected:
                fail('MAP_LAYOUT_CHANGED','训练场景本体出现尚未验证的变化，已停止安装，避免沿用不匹配的坐标。')
        patched,plan=patch_script(native,spec,extension)
    index=max(2,max(archives)+1)
    if action=='Restore' and state:
        previous_index=int(state.get('patchDataFile',MAP+'_002.vpk')[-7:-4])
        if previous_index not in archives:index=previous_index
    data_name=f'{MAP}_{index:03}.vpk'
    residue=target/data_name
    known_data={pair['patchDataSha256'] for record in records for pair in record['patches']}
    if residue.exists() and sha(residue) not in known_data:
        fail('PATCH_RESIDUE_UNKNOWN','目标新增分卷已有未知文件：'+data_name+'；未覆盖。')
    # Own generated receipts add their exact payload to the recognized set.
    additions={} if restore_native else {key:(package/'adaptive/assets'/key).read_bytes() for key in spec['assetKeys']}
    if any(key in entries for key in additions):fail('MAP_ASSET_COLLISION','原图已包含训练补丁模型路径，无法确认修改来源。')
    payloads={spec['scriptKey']:patched,**additions}
    generated_entries=dict(entries);data=bytearray()
    for key,body in payloads.items():
        generated_entries[key]=vpk.VpkEntry(key,zlib.crc32(body)&0xffffffff,0,index,len(data),len(body),0xffff,b'')
        data.extend(body)
    original_sha=hashlib.sha256(original_index).hexdigest()
    fingerprint=hashlib.sha256(json.dumps({'index':original_sha,'base':base_hashes,'recipe':recipe_hash,
                                         'files':adaptive['files'],'generator':adaptive['sha256'],'packageManifest':sha(package/'manifest.json'),'version':manifest['version'],
                                         'action':action,'previous':records},sort_keys=True).encode()).hexdigest()
    target_key=hashlib.sha256(str(target).casefold().encode()).hexdigest()[:24]
    parent=cache_root/target_key;parent.mkdir(parents=True,exist_ok=True)
    output=parent/fingerprint
    workspace=Path(tempfile.mkdtemp(prefix='prepare-',dir=parent))
    try:
        for name in ('payload','reference','helper'):(workspace/name).mkdir()
        (workspace/'payload'/data_name).write_bytes(data)
        vpk.write_directory(workspace/'payload'/DIR,vpk.write_tree(generated_entries),bytes(data),archive_md5+vpk.build_archive_md5(bytes(data),index))
        _,checked,md5,*_=parse(workspace/'payload'/DIR)
        try:vpk.validate_md5_records(md5,{**volumes,index:bytes(data)})
        except ValueError as error:fail('ADAPT_OUTPUT_INVALID',str(error))
        for key,entry in checked.items():
            value=entry_bytes(entry,{**volumes,index:bytes(data)})
            if value!=(payloads[key] if key in payloads else entry_bytes(entries[key],volumes)):
                fail('ADAPT_OUTPUT_INVALID','输出资源内容不一致：'+key)
        (workspace/'reference'/DIR).write_bytes(original_index)
        shutil.copy2(helper,workspace/'helper/5EHubAssist.exe')
        result=copy.deepcopy(manifest);result.pop('adaptive',None)
        result.update(baseVolumes=base_hashes,originalDirSha256=original_sha,patchDirSha256=sha(workspace/'payload'/DIR),
                      patchDataSha256=sha(workspace/'payload'/data_name),patchDataFile=data_name,previousMaps=records)
        result['knownMaps']=[{'label':'本机自动校验的兼容原图','date':'local','baseVolumes':base_hashes}]
        result['adaptiveGenerated']={'schema':1,'recipeSha256':recipe_hash,'plan':plan,'target':str(target),
                                     'fingerprint':fingerprint,'nativeScriptSha256':hashlib.sha256(native).hexdigest(),
                                     'verifiedEntries':len(checked),'sourceEntries':len(entries)}
        if adopt:result['adaptiveAdopt']=adopt
        # Reused cache paths are published only if their immutable payload agrees.
        for name in ('manifest.json','known-manifest.json'):
            (workspace/name).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        for name,(length,stamp) in stamps.items():
            stat=(target/name).stat()
            if (stat.st_size,stat.st_mtime_ns)!=(length,stamp):fail('MAP_CHANGED_DURING_ADAPT','Steam 正在改动地图，请等下载完成后重试。')
        if sha(live)!=live_sha:fail('MAP_CHANGED_DURING_ADAPT','地图索引在生成期间发生变化。')
        if output.exists():
            cached=read_json(output/'manifest.json')
            if cached!=result or sha(output/'payload'/DIR)!=result['patchDirSha256'] or sha(output/'payload'/data_name)!=result['patchDataSha256']:
                fail('ADAPT_CACHE_DAMAGED','本机生成缓存校验失败，请保留报告；未写入地图。')
        else:
            if not workspace.resolve().is_relative_to(parent) or not output.resolve().is_relative_to(parent):
                fail('ADAPT_PATH_INVALID','生成目录超出本机缓存范围。')
            workspace.rename(output)
        return {'ok':True,'packageRoot':str(output),'target':str(target),'plan':plan,'baseVolumes':base_hashes,
                'sourceEntries':len(entries),'verifiedEntries':len(checked),'patchDataFile':data_name}
    finally:
        if workspace.exists():
            if not workspace.resolve().is_relative_to(parent.resolve()):raise RuntimeError('Unsafe temporary path')
            shutil.rmtree(workspace)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--package',type=Path,required=True)
    parser.add_argument('--target',type=Path,required=True);parser.add_argument('--cache-root',type=Path)
    parser.add_argument('--result',type=Path,required=True);parser.add_argument('--action',choices=['Install','Restore','Check'],default='Install')
    args=parser.parse_args()
    cache=args.cache_root or Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'5EHub-Recoil-Patch/adapted'
    try:result=prepare(args.package,args.target,cache,args.action)
    except AdaptError as error:result={'ok':False,'code':error.code,'message':str(error)}
    except (OSError,ValueError,struct.error) as error:result={'ok':False,'code':'ADAPT_READ_FAILED','message':str(error)}
    args.result.write_text(json.dumps(result,ensure_ascii=True,indent=2),encoding='utf-8')
    print(json.dumps({'ok':result['ok'],'code':result.get('code','OK')}),flush=True)
    raise SystemExit(0 if result['ok'] else 1)

if __name__=='__main__':main()
