"""Local experiment: use native client camera queries; no memory access/injection."""
import argparse
import json
import re
import select
import socket
import struct
import time
import ctypes
import os
import sys
from collections import deque
from pathlib import Path


class OffsetTrend:
    """Short native-sample fit; publish capture time instead of receipt time."""
    def __init__(self):
        self.samples=deque(maxlen=3)

    def update(self, stamp, delta):
        if self.samples and (stamp-self.samples[-1][0]>.15 or any(abs(delta[k]-self.samples[-1][1][k])>1.5 for k in ['pitch','yaw'])):
            self.samples.clear()
        self.samples.append((stamp,delta.copy()))
        velocity={k:0.0 for k in ['pitch','yaw']};value=delta.copy()
        if len(self.samples)>=2:
            times=[t-stamp for t,_ in self.samples];mean=sum(times)/len(times)
            variance=sum((t-mean)**2 for t in times)
            if variance>1e-7:
                for k in velocity:
                    average=sum(d[k] for _,d in self.samples)/len(self.samples)
                    slope=sum((t-mean)*(d[k]-average) for t,(_,d) in zip(times,self.samples))/variance
                    velocity[k]=max(-35,min(35,slope))
                    value[k]=average-velocity[k]*mean
        return value,velocity


class Console:
    def __init__(self):
        self.sock=socket.create_connection(('127.0.0.1',29000),timeout=3)
        self.sock.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
        self.sock.setblocking(False)
        self.buffer=bytearray()
        self.last_state=None
        self.view_punch_decay=None
        self.read(.5) # discard all initial buffered messages, including account text

    def send(self, command):
        payload=command.encode('utf-8')+b'\0'
        self.sock.sendall(b'CMND'+struct.pack('>HIH',0xd4,12+len(payload),0)+payload)

    def read(self, timeout):
        result=[]
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            if not select.select([self.sock],[],[],max(0,deadline-time.monotonic()))[0]:break
            part=self.sock.recv(65536)
            if not part:raise ConnectionError('Native console closed')
            self.buffer.extend(part)
            while len(self.buffer)>=12:
                length=struct.unpack_from('>I',self.buffer,6)[0]
                if not 12<=length<=16777216:raise ValueError('Invalid native packet')
                if len(self.buffer)<length:break
                tag=bytes(self.buffer[:4]);payload=bytes(self.buffer[12:length]);del self.buffer[:length]
                if tag==b'PRNT':
                    message=payload.decode('utf-8',errors='replace');result.append(message)
                    found=re.search(r'\[AK-STATE\]\s*(\{[^\r\n\x00]*\})',message)
                    if found:self.last_state=json.loads(found.group(1))
                    setting=re.search(r'view_punch_decay\s*=\s*([\d.]+)',message)
                    if setting:self.view_punch_decay=float(setting.group(1))
            if result:break
        return result

    def camera_sample(self):
        self.send('getpos;getpos_exact')
        camera=raw=None
        deadline=time.monotonic()+.15
        while time.monotonic()<deadline:
            for message in self.read(.015):
                for kind,pitch,yaw in re.findall(r';(setang(?:_exact)?)\s+([\d.\-]+)\s+([\d.\-]+)',message):
                    values={'pitch':float(pitch),'yaw':float(yaw)}
                    if kind=='setang_exact':raw=values
                    else:camera=values
            if camera and raw:return camera,raw
        return None


def sync_screen_shake(console, previous):
    shake=(console.last_state or {}).get('screenShake')
    if isinstance(shake,bool) and shake!=previous:
        console.send('view_punch_decay '+('18' if shake else '10000')+';view_punch_decay')
        return shake
    return previous


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--seconds',type=float,default=0);parser.add_argument('--prediction',action='store_true');parser.add_argument('--wait-console',type=float,default=0);parser.add_argument('--report',type=Path);args=parser.parse_args()
    lock=None
    if getattr(sys,'frozen',False) and os.name=='nt':
        kernel=ctypes.windll.kernel32
        kernel.CreateMutexW.argtypes=[ctypes.c_void_p,ctypes.c_bool,ctypes.c_wchar_p]
        kernel.CreateMutexW.restype=ctypes.c_void_p
        kernel.CloseHandle.argtypes=[ctypes.c_void_p]
        lock=kernel.CreateMutexW(None,False,'Local\\5EHubRecoilAssist29000')
        if not lock:raise OSError('Unable to create helper lock')
        if kernel.GetLastError()==183:
            kernel.CloseHandle(lock);return
    output=args.report or (Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'5EHub-Recoil-Patch/view-bridge.json' if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[1]/'build/display-investigation/view-bridge.json')
    output.parent.mkdir(parents=True,exist_ok=True)
    # Limit Windows timer rounding during the bounded native polling loop.
    timer=ctypes.windll.winmm if hasattr(ctypes,'windll') else None
    if timer:timer.timeBeginPeriod(1)
    deadline=time.monotonic()+max(0,args.wait_console)
    while True:
        try:console=Console();break
        except OSError:
            if time.monotonic()>=deadline:raise
            time.sleep(.5)
    console.send('akcamera off;r_drawviewmodel 1;firstperson')
    start=time.monotonic();samples=0;peak=0;last=None;last_report=0;last_state_query=0;last_shake=None;trend=OffsetTrend()
    try:
        while args.seconds<=0 or time.monotonic()-start<args.seconds:
            cycle=time.monotonic()
            sample=console.camera_sample()
            if sample:
                camera,raw=sample
                delta={key:((camera[key]-raw[key]+180)%360)-180 for key in ['pitch','yaw']}
                stamp=time.time()
                value,velocity=trend.update(stamp,delta) if args.prediction else (delta,{'pitch':0,'yaw':0})
                console.send(f'akviewdelta {value["pitch"]:.8f} {value["yaw"]:.8f} {velocity["pitch"]:.8f} {velocity["yaw"]:.8f} {stamp:.6f}')
                samples+=1;peak=max(peak,abs(delta['pitch']),abs(delta['yaw']));last={'camera':camera,'raw':raw,'delta':delta,'published':value,'velocity':velocity,'captured':stamp}
            # Workshop ServerCommand is forbidden from changing this cvar.
            # Apply the menu's choice through the already-authorized local
            # native console, and query the actual value after every change.
            last_shake=sync_screen_shake(console,last_shake)
            if time.monotonic()-last_state_query>.1:
                console.send('akdebug');last_state_query=time.monotonic()
            if time.monotonic()-last_report>1:
                elapsed=time.monotonic()-start
                output.write_text(json.dumps({'samples':samples,'seconds':elapsed,'samplesPerSecond':samples/max(.001,elapsed),'peakDelta':peak,'last':last,'state':console.last_state,'screenShakeSync':{'requested':last_shake,'actualViewPunchDecay':console.view_punch_decay}},indent=2)+'\n',encoding='utf-8')
                last_report=time.monotonic()
            time.sleep(max(0,1/128-(time.monotonic()-cycle)))
    except (OSError,ConnectionError):
        pass # Closing the game ends the helper without an interactive error.
    finally:
        elapsed=time.monotonic()-start
        report={'samples':samples,'seconds':elapsed,'samplesPerSecond':samples/max(.001,elapsed),'peakDelta':peak,'last':last,'state':console.last_state,'screenShakeSync':{'requested':last_shake,'actualViewPunchDecay':console.view_punch_decay}}
        output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        try:console.send('akviewdelta 0 0')
        except OSError:pass
        console.sock.close()
        if timer:timer.timeEndPeriod(1)
        if lock:ctypes.windll.kernel32.CloseHandle(lock)
        print(json.dumps({k:v for k,v in report.items() if k!='last'}),flush=True)


if __name__=='__main__':main()
