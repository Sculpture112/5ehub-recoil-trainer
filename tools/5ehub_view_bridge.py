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
import secrets
import subprocess
from collections import deque
from pathlib import Path
from fivehub_native_punch import NativePunchFeed


class TrainingEnded(RuntimeError):
    pass


def verify_game_process(game_pid=None):
    """Check public Windows process/port metadata; never read game memory."""
    if os.name != 'nt':
        raise TrainingEnded('training_process_unverified')
    pid_filter = f'$requiredPid={int(game_pid)};' if game_pid else '$requiredPid=0;'
    script = pid_filter + r'''
$ErrorActionPreference='Stop'
$listeners=@(Get-NetTCPConnection -State Listen -LocalPort 29000 -ErrorAction Stop)
$owners=@($listeners.OwningProcess | Sort-Object -Unique)
if($owners.Count -ne 1){throw 'Unverified console listener'}
$ownerId=[int]$owners[0]
if($requiredPid -and $ownerId -ne $requiredPid){throw 'Console owner mismatch'}
$game=Get-CimInstance Win32_Process -Filter "ProcessId=$ownerId" -ErrorAction Stop
@{pid=$ownerId;game=($game.Name -ieq 'cs2.exe');
  insecure=($game.CommandLine -match '(?i)(?:^|\s)-insecure(?:\s|$)');
  vconsole=($game.CommandLine -match '(?i)(?:^|\s)-vconport\s+29000(?:\s|$)')} | ConvertTo-Json -Compress
'''
    try:
        result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                                capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=15,
                                creationflags=subprocess.CREATE_NO_WINDOW, check=True)
        info = json.loads(result.stdout.strip())
        if not all(info.get(key) is True for key in ('game', 'insecure', 'vconsole')):
            raise ValueError('Required training launch parameters not verified')
        return info['pid']
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        raise TrainingEnded('training_process_unverified') from error


class TrainingGuard:
    """Fresh map acknowledgement before every write; fail closed on uncertainty."""
    def __init__(self, console):
        self.console = console
        self.nonce = None
        self.reply = None
        self.session = None
        self.client = None
        self.client_checked = 0.0
        self.last_status_request = -1.0
        self.reason = None
        self.active = False
        console.guard = self

    def observe(self, message):
        # Bot removal also logs NETWORK_DISCONNECT_KICKED. Only the local
        # client's departure is conclusive; server-side lifecycle lines alone
        # must not terminate synchronization while fresh map proofs still pass.
        if self.active and 'Disconnecting from server' in message:
            self.reason = 'training_disconnected'
        connection = re.search(r'Client:\s*Connected\s+\[([^\]]+)\]', message)
        if connection:
            self.client = connection[1]
            self.client_checked = time.monotonic()
            if self.active and not self.client.startswith('loopback:'):
                self.reason = 'nonlocal_connection'
        if re.search(r'Client:\s*(?:Not connected|Disconnected|Not running)', message, re.I):
            self.client = None
            if self.active:
                self.reason = 'training_disconnected'
        found = re.search(r'\[AK-BRIDGE-GUARD\]\s*(\{[^\r\n\x00]*\})', message)
        if found:
            try:
                info = json.loads(found[1])
            except ValueError:
                return
            if info.get('nonce') == self.nonce:
                self.reply = info
                if isinstance(info.get('screenShake'),bool):
                    self.console.last_state={**(self.console.last_state or {}),'screenShake':info['screenShake']}

    def begin(self):
        self.nonce = secrets.token_hex(12)
        self.reply = None
        now = time.monotonic()
        status = ''
        if now - self.last_status_request >= 1:
            status = 'status;'
            self.last_status_request = now
        self.console.send(status + 'akbridgeguard ' + self.nonce)

    def confirm(self, timeout=.25):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.reason:
                raise TrainingEnded(self.reason)
            if self.reply is not None and self.client is not None:
                break
            for message in self.console.read(min(.01, max(0, deadline-time.monotonic()))):
                self.observe(message)
        if self.reason:
            raise TrainingEnded(self.reason)
        info = self.reply or {}
        if info.get('protocol') != 1 or info.get('map') != '5e_aimhub' or info.get('dedicated') is not False:
            raise TrainingEnded('training_map_unverified')
        if not isinstance(info.get('session'), str) or not info['session']:
            raise TrainingEnded('training_map_unverified')
        if not self.client or not self.client.startswith('loopback:') or time.monotonic()-self.client_checked > 2.5:
            raise TrainingEnded('nonlocal_or_unverified_connection')
        if info.get('ready') is False:
            raise TrainingEnded('training_not_ready')
        if self.session is not None and self.session != info['session']:
            raise TrainingEnded('training_map_reloaded')
        self.session = info['session']
        self.active = True

    def check_observed_departure(self):
        if self.reason:
            raise TrainingEnded(self.reason)


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
        self.buffered_complete=False
        self.guard=None
        self.punch_feed=NativePunchFeed(self)
        self.read(.5) # discard all initial buffered messages, including account text

    def drain_initial_messages(self, timeout=2):
        """Old buffered disconnect lines must never count as a current departure."""
        marker='FIVEHUB-CONSOLE-READY-'+secrets.token_hex(12)
        # A buffered end marker can belong to only one console producer.
        # Require our own command round-trip after the replay, rather than
        # treating a historical end marker as proof that every stream is fresh.
        self.send('echo '+marker)
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            if any(marker in message for message in self.read(.05)):
                self.buffered_complete=True
                return
        raise TrainingEnded('console_initial_buffer_unverified')

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
                    if 'End VConsole Buffered Messages' in message:self.buffered_complete=True
                    if self.guard:self.guard.observe(message)
                    self.punch_feed.accept(message)
                    found=re.search(r'\[AK-STATE\]\s*(\{[^\r\n\x00]*\})',message)
                    if found:
                        try:self.last_state=json.loads(found.group(1))
                        except ValueError:pass
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
    expected=18 if shake else 10000
    if isinstance(shake,bool) and (shake!=previous or console.view_punch_decay!=expected):
        console.send('view_punch_decay '+('18' if shake else '10000')+';view_punch_decay')
        return shake
    return previous


def acquire_helper_lock():
    if os.name=='nt':
        kernel=ctypes.windll.kernel32
        kernel.CreateMutexW.argtypes=[ctypes.c_void_p,ctypes.c_bool,ctypes.c_wchar_p]
        kernel.CreateMutexW.restype=ctypes.c_void_p
        kernel.CloseHandle.argtypes=[ctypes.c_void_p]
        lock=kernel.CreateMutexW(None,False,'Local\\5EHubRecoilAssist29000')
        if not lock:raise OSError('Unable to create helper lock')
        if kernel.GetLastError()==183:
            kernel.CloseHandle(lock);return False
        return lock
    return None


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--seconds',type=float,default=0);parser.add_argument('--prediction',action='store_true');parser.add_argument('--wait-console',type=float,default=0);parser.add_argument('--report',type=Path);parser.add_argument('--game-pid',type=int);args=parser.parse_args()
    lock=acquire_helper_lock()
    if lock is False:return
    output=args.report or (Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'5EHub-Recoil-Patch/view-bridge.json' if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[1]/'build/display-investigation/view-bridge.json')
    output.parent.mkdir(parents=True,exist_ok=True)
    # Limit Windows timer rounding during the bounded native polling loop.
    timer=ctypes.windll.winmm if hasattr(ctypes,'windll') else None
    if timer:timer.timeBeginPeriod(1)
    deadline=time.monotonic()+max(0,args.wait_console)
    console=None;guard=None;game_pid=None
    start=time.monotonic();samples=0;peak=0;last=None;last_report=0;last_state_query=0;last_diag_query=0;last_shake=None;trend=OffsetTrend();exit_reason='time_limit'
    def report_now():
        elapsed=time.monotonic()-start
        feed=getattr(console,'punch_feed',None)
        return {'samples':samples,'seconds':elapsed,'samplesPerSecond':samples/max(.001,elapsed),'peakDelta':peak,'last':last,'state':console.last_state if console else None,'nativeRecoil':{'snapshots':feed.snapshots,'fresh':feed.fresh,'last':feed.last_snapshot} if feed else None,'screenShakeSync':{'requested':last_shake,'actualViewPunchDecay':console.view_punch_decay if console else None},'gamePid':game_pid,'exitReason':exit_reason,'lifecycle':{'map':'5e_aimhub','session':guard.session if guard else None,'freshNonceRequired':True,'localInsecureRequired':True}}
    try:
        while True:
            try:
                console=Console()
                if hasattr(console,'drain_initial_messages'):console.drain_initial_messages()
                break
            except (OSError,TrainingEnded) as error:
                if isinstance(error,TrainingEnded) and str(error)!='console_initial_buffer_unverified':raise
                if console:console.sock.close();console=None
                if time.monotonic()>=deadline:raise
                time.sleep(.5)
        game_pid=verify_game_process(args.game_pid)
        guard=TrainingGuard(console)
        # While loading, query only. Never change global settings before proof.
        while True:
            guard.begin()
            try:
                guard.confirm()
                break
            except TrainingEnded as error:
                if (guard.reply and str(error)!='training_not_ready') or time.monotonic()>=deadline:
                    raise
                time.sleep(.1)
        start=time.monotonic()
        console.send('akcamera off;r_drawviewmodel 1;firstperson')
        while args.seconds<=0 or time.monotonic()-start<args.seconds:
            cycle=time.monotonic()
            sample=console.camera_sample()
            guard.check_observed_departure()
            guard.begin()
            guard.confirm()
            if getattr(console,'punch_feed',None):console.punch_feed.tick()
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
            if isinstance((guard.reply or {}).get('screenShake'),bool):
                console.last_state={**(console.last_state or {}),'screenShake':guard.reply['screenShake']}
            last_shake=sync_screen_shake(console,last_shake)
            if time.monotonic()-last_state_query>.1:
                console.send('view_punch_decay');last_state_query=time.monotonic()
            if time.monotonic()-last_diag_query>.5:
                console.send('akdebug');last_diag_query=time.monotonic()
            if time.monotonic()-last_report>1:
                output.write_text(json.dumps(report_now(),indent=2)+'\n',encoding='utf-8')
                last_report=time.monotonic()
            time.sleep(max(0,1/128-(time.monotonic()-cycle)))
    except TrainingEnded as error:
        exit_reason=str(error)
    except (OSError,ConnectionError):
        exit_reason='console_disconnected'
    finally:
        report=report_now()
        # Do not send cleanup commands into a menu, another map, or unknown session.
        if console:console.sock.close()
        if timer:timer.timeEndPeriod(1)
        if lock:ctypes.windll.kernel32.CloseHandle(lock)
        output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({k:v for k,v in report.items() if k!='last'}),flush=True)


if __name__=='__main__':main()
