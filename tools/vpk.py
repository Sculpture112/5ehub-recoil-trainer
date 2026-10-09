"""Read and package small, single-file Valve VPK archives for local builds."""
from pathlib import Path
from collections import defaultdict
import struct
import zlib
import hashlib

MAGIC=0x55AA1234


def read(path):
    path=Path(path)
    data=path.read_bytes()
    magic,version,tree_size=struct.unpack_from('<3I',data)
    if magic!=MAGIC or version not in (1,2):
        raise ValueError('Not a supported VPK')
    start=12 if version==1 else 28
    cursor=start
    entries={}

    def string():
        nonlocal cursor
        end=data.index(b'\0',cursor)
        value=data[cursor:end].decode('utf-8')
        cursor=end+1
        return value

    while (ext:=string()):
        while (directory:=string()):
            while (name:=string()):
                crc,preload,archive,offset,length,terminator=struct.unpack_from('<IHHIIH',data,cursor)
                cursor+=18
                if terminator!=0xffff:
                    raise ValueError('VPK entry terminator is invalid')
                body=data[cursor:cursor+preload]
                cursor+=preload
                if archive==0x7fff:
                    body+=data[start+tree_size+offset:start+tree_size+offset+length]
                else:
                    volume=path.with_name(path.stem.removesuffix('_dir')+f'_{archive:03}.vpk')
                    with volume.open('rb') as stream:
                        stream.seek(offset)
                        body+=stream.read(length)
                if len(body)!=preload+length or zlib.crc32(body)&0xffffffff!=crc:
                    raise ValueError(f'VPK checksum/size mismatch: {directory}/{name}.{ext}')
                key=(directory+'/' if directory!=' ' else '')+name+('.'+ext if ext!=' ' else '')
                entries[key]=body
    if cursor!=start+tree_size:
        raise ValueError('VPK tree does not end at declared boundary')
    return entries


def write(path,entries):
    groups=defaultdict(lambda:defaultdict(list))
    offset=0
    body=bytearray()
    for name,payload in sorted(entries.items()):
        parts=Path(name.replace('\\','/'))
        directory=parts.parent.as_posix()
        directory=' ' if directory=='.' else directory
        extension=parts.suffix[1:] or ' '
        basename=parts.stem if extension!=' ' else parts.name
        groups[extension][directory].append((basename,payload,offset))
        body.extend(payload)
        offset+=len(payload)
    tree=bytearray()
    for extension,dirs in sorted(groups.items()):
        tree.extend(extension.encode()+b'\0')
        for directory,files in sorted(dirs.items()):
            tree.extend(directory.encode()+b'\0')
            for basename,payload,offset in files:
                tree.extend(basename.encode()+b'\0')
                tree.extend(struct.pack('<IHHIIH',zlib.crc32(payload)&0xffffffff,0,0x7fff,offset,len(payload),0xffff))
            tree.extend(b'\0')
        tree.extend(b'\0')
    tree.extend(b'\0')
    archive_md5=struct.pack('<3I16s',0x7fff,0,len(body),hashlib.md5(body).digest())
    header=struct.pack('<7I',MAGIC,2,len(tree),len(body),len(archive_md5),48,0)
    before_checksums=header+tree+body+archive_md5
    checksums=hashlib.md5(tree).digest()+hashlib.md5(archive_md5).digest()
    checksums+=hashlib.md5(before_checksums+checksums).digest()
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(before_checksums+checksums)
    if read(path)!=entries:
        raise ValueError('Packaged VPK failed the content roundtrip')
