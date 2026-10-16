"""Preserve the shipped dual-pistol feed while deferring writes to the guarded loop."""
import unittest
from fivehub_native_punch import NativePunchFeed


class Console:
    def __init__(self):
        self.sent=[]
        self.last_state={'active':True,'weapon':'weapon_elite','stats':{'shots':0}}
    def send(self,command):self.sent.append(command)


class FeedTests(unittest.TestCase):
    def setUp(self):
        self.console=Console();self.feed=NativePunchFeed(self.console)
        self.feed.index=1411;self.feed.last_weapon='weapon_elite'
        self.feed.last_shots=0;self.feed.dirty=False
    def capture(self,body,prefix=''):
        self.feed.pending='fresh'
        self.feed.accept(prefix+'BEGIN-fresh\n'+body+'\nEND-fresh')
    def state(self,velocity='-24 2 0'):
        return ('m_predictableBaseTick: 6400\nm_predictableBaseTickInterpAmoun: 0.5\n'
                'm_predictableBaseAngle: -1 0.1 0\nm_predictableBaseAngleVel: '+velocity)
    def test_snapshot_is_published_only_by_guarded_tick(self):
        self.capture(self.state(),prefix=self.state('500 500 500')+'\n')
        self.assertEqual(self.console.sent,[])
        self.feed.tick()
        values=list(map(float,self.console.sent[-1].split()[1:]))
        self.assertAlmostEqual(values[0],(6400.5-2)/64)
        self.assertEqual(values[4:],[-24,2,0])
        self.assertEqual(self.feed.snapshots,1)
    def test_missing_or_nonfinite_reply_does_not_publish(self):
        self.feed.pending='fresh';self.feed.accept(self.state()+' END-fresh')
        self.assertIsNone(self.feed.queued)
        self.capture(self.state('nan 2 0'))
        self.assertIsNone(self.feed.queued)
    def test_automatic_weapons_and_inactive_mode_do_not_dump(self):
        self.console.last_state['weapon']='weapon_ak47';self.feed.tick()
        self.console.last_state.update(weapon='weapon_elite',active=False);self.feed.tick()
        self.assertEqual(self.console.sent,[])
    def test_shot_event_requests_one_fresh_dump(self):
        self.feed.tick();self.assertEqual(self.console.sent,[])
        self.feed.accept('[AK-IMPACT] {"weapon":"weapon_elite"}')
        self.feed.tick();self.feed.tick()
        self.assertEqual(len(self.console.sent),1)
        self.assertIn('cl_dumpentity 1411',self.console.sent[0])


if __name__=='__main__':unittest.main(verbosity=2)
