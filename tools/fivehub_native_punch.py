"""Existing Dual Berettas native-console recoil feed, with guarded publication."""
import json
import math
import os
import re
import time

class NativePunchFeed:
    """Observe event-base recoil through fresh native console responses.

    Only Dual Berettas need this feed. The map advances recovery every Think;
    dumps are requested on firing, not on every display frame.
    """
    def __init__(self,console):
        self.console=console;self.pending=None;self.buffer='';self.started=0
        self.index=None;self.dirty=True;self.last_request=0;self.last_shots=None
        self.last_weapon=None;self.last_controller_query=0;self.snapshots=0
        self.last_snapshot=None;self.fresh=False;self.queued=None

    def accept(self,message):
        impact=re.search(r'\[AK-IMPACT\]\s*(\{[^\r\n\x00]*\})',message)
        if impact:
            try:
                if json.loads(impact.group(1)).get('weapon')=='weapon_elite':self.dirty=True
            except ValueError:
                pass
        if not self.pending:return
        self.buffer+=message
        if len(self.buffer)>2_000_000:
            self.pending=None;self.dirty=True;self.fresh=False;return
        if 'END-'+self.pending not in message:return
        begin='BEGIN-'+self.pending;end='END-'+self.pending
        text=self.buffer.split(begin,1)[1].split(end,1)[0] if begin in self.buffer else ''
        self.pending=None;self.buffer=''
        if self.index is None:
            found=re.search(r'm_hPlayerPawn:\s*(\d+)',text)
            if found:self.index=int(found.group(1))
            self.dirty=True;return
        values={}
        for key in ['m_predictableBaseTick','m_predictableBaseTickInterpAmoun','m_predictableBaseAngle','m_predictableBaseAngleVel']:
            matches=re.findall(key+r':\s*([^\r\n\x00]+)',text)
            if not matches:self.dirty=True;self.fresh=False;return
            try:values[key]=[float(x) for x in matches[-1].split()]
            except ValueError:self.dirty=True;self.fresh=False;return
        if [len(v) for v in values.values()]!=[1,1,3,3]:
            self.dirty=True;self.fresh=False;return
        tick=values['m_predictableBaseTick'][0];fraction=values['m_predictableBaseTickInterpAmoun'][0]
        # Local client prediction and server SetEyeAngles apply on different
        # ticks. Two simulation ticks were measured against actual bullet rays.
        stamp=(tick+fraction-2)/64 if tick>0 else 0
        state=[stamp,*values['m_predictableBaseAngle'],*values['m_predictableBaseAngleVel']]
        if not all(math.isfinite(x) for x in state) or not 0<=fraction<=1:
            self.dirty=True;self.fresh=False;return
        self.queued=state

    def tick(self):
        # Main calls tick only after fresh local-map authorization.
        if self.queued is not None:
            state=self.queued;self.queued=None
            self.console.send('akpunch '+' '.join(f'{x:.9f}' for x in state))
            self.snapshots+=1;self.last_snapshot={'baseTime':state[0],'angle':state[1:4],'velocity':state[4:]};self.fresh=True
        now=time.monotonic();state=self.console.last_state or {}
        weapon=state.get('weapon');shots=state.get('stats',{}).get('shots')
        if weapon!=self.last_weapon:
            self.index=None;self.dirty=True;self.last_weapon=weapon;self.fresh=False
        if shots!=self.last_shots:self.dirty=True;self.last_shots=shots
        if self.pending and now-self.started>.3:self.pending=None;self.dirty=True;self.fresh=False
        if weapon!='weapon_elite' or not state.get('active') or self.pending or not self.dirty or now-self.last_request<.025:return
        self.pending=os.urandom(8).hex();self.buffer='';self.started=now;self.last_request=now;self.dirty=False
        command='cl_dumpentity '+str(self.index) if self.index is not None else 'cl_dumpentity 1'
        self.console.send('echo BEGIN-'+self.pending+';'+command+';echo END-'+self.pending)
