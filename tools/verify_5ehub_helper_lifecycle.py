"""Exercise the real helper loop without connecting to or changing CS2."""
import importlib
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

bridge = importlib.import_module('5ehub_view_bridge')


class FakeConsole:
    def __init__(self, departure='menu'):
        self.departure = departure
        self.camera_calls = 0
        self.left = False
        self.commands = []
        self.pending = []
        self.last_state = {'screenShake': False}
        self.view_punch_decay = 18
        self.sock = self
        self.closed = False

    def close(self):
        self.closed = True

    def send(self, command):
        self.commands.append((self.left, command))
        match = re.search(r'akbridgeguard ([a-zA-Z0-9_-]+)', command)
        if not match:
            return
        nonce = match[1]
        if self.left and self.departure == 'timeout':
            return
        self.pending += ['Client:  Connected [' + ('203.0.113.1:27015' if self.left and self.departure == 'remote' else 'loopback:1') + ']']
        if not self.left or self.departure in ('other_map', 'remote', 'dedicated', 'stale'):
            self.pending += ['[AK-BRIDGE-GUARD] ' + json.dumps({
                'nonce': 'old-reply' if self.left and self.departure == 'stale' else nonce,
                'map': 'de_dust2' if self.left and self.departure == 'other_map' else '5e_aimhub',
                'dedicated': self.left and self.departure == 'dedicated',
                'protocol': 1,
                'session': 'test-map-instance',
            })]
        self.pending += ['FIVEHUB-GUARD-END-' + nonce]

    def read(self, timeout):
        if self.pending:
            messages, self.pending = self.pending, []
            return messages
        return []

    def camera_sample(self):
        self.commands.append((self.left, 'getpos;getpos_exact'))
        self.camera_calls += 1
        if self.camera_calls == 3:
            self.left = True
        return {'pitch': 1.0, 'yaw': 2.0}, {'pitch': 0.0, 'yaw': 2.0}


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.lock_patch=patch.object(bridge,'acquire_helper_lock',return_value=None)
        self.lock_patch.start();self.addCleanup(self.lock_patch.stop)

    def test_cold_console_without_initial_buffer_is_closed_and_retried(self):
        class ColdConsole(FakeConsole):
            def drain_initial_messages(self):
                raise bridge.TrainingEnded('console_initial_buffer_unverified')
        cold=ColdConsole();ready=FakeConsole()
        with tempfile.TemporaryDirectory() as folder:
            report=Path(folder)/'report.json'
            with patch.object(bridge,'Console',side_effect=[cold,ready]) as connect,\
                 patch.object(bridge,'verify_game_process',return_value=None),\
                 patch.object(sys,'argv',['helper','--seconds','.02','--wait-console','2','--report',str(report)]):
                bridge.main()
            self.assertEqual(connect.call_count,2)
            self.assertTrue(cold.closed)
            self.assertGreater(json.loads(report.read_text())['samples'],0)

    def test_initial_replay_waits_for_own_echo_after_historical_end_marker(self):
        class ReplayConsole:
            def __init__(self):self.buffered_complete=True;self.calls=0;self.marker=None
            def send(self,command):self.marker=command.removeprefix('echo ')
            def read(self,timeout):
                self.calls+=1
                if self.calls==1:return ['End VConsole Buffered Messages','GameServerSteamAPIDeactivated()']
                return [self.marker]
        console=ReplayConsole()
        bridge.Console.drain_initial_messages(console)
        self.assertEqual(console.calls,2)

    def test_bot_kick_and_server_api_event_are_not_local_player_departure(self):
        console=FakeConsole();guard=bridge.TrainingGuard(console);guard.active=True
        guard.observe("[Server] Client 'Bot' disconnected (NETWORK_DISCONNECT_KICKED)")
        guard.observe('[Server] CSource2Server::GameServerSteamAPIDeactivated()')
        self.assertIsNone(guard.reason)
        guard.observe('[Client] Disconnecting from server: NETWORK_DISCONNECT_DISCONNECT_BY_USER')
        self.assertEqual(guard.reason,'training_disconnected')

    def test_buffered_old_departure_is_drained_before_guard_activation(self):
        class BufferedConsole(FakeConsole):
            def __init__(self):
                super().__init__();self.initial=True
            def drain_initial_messages(self):
                self.pending=['GameServerSteamAPIDeactivated()', 'End VConsole Buffered Messages']
                self.read(.01);self.initial=False
            def send(self,command):
                if self.initial:raise AssertionError('Command sent before initial log was drained')
                super().send(command)
        console=BufferedConsole()
        with tempfile.TemporaryDirectory() as folder:
            report=Path(folder)/'report.json'
            with patch.object(bridge,'Console',return_value=console),patch.object(bridge,'verify_game_process',return_value=None),\
                 patch.object(sys,'argv',['helper','--seconds','.02','--report',str(report)]):
                bridge.main()
            self.assertGreater(json.loads(report.read_text())['samples'],0)

    def test_startup_waits_without_writes_across_initialization(self):
        class LoadingConsole(FakeConsole):
            def __init__(self):
                super().__init__();self.queries=0;self.early_writes=[]
            def send(self,command):
                match=re.search(r'akbridgeguard ([a-zA-Z0-9_-]+)',command)
                if match and not self.left:
                    self.queries+=1;nonce=match[1];ready=self.queries>=3
                    self.commands.append((self.left,command))
                    self.pending+=['Client: Connected [loopback:1]','[AK-BRIDGE-GUARD] '+json.dumps({
                        'protocol':1,'nonce':nonce,'map':'5e_aimhub','dedicated':False,
                        'session':'final-map' if ready else 'loading-map','ready':ready,'screenShake':False})]
                    if not ready:self.pending.append('GameServerSteamAPIDeactivated()')
                    return
                if self.queries<3 and command.startswith(('akcamera ','akviewdelta ','view_punch_decay ')):
                    self.early_writes.append(command)
                super().send(command)
        console=LoadingConsole()
        with tempfile.TemporaryDirectory() as folder:
            report=Path(folder)/'report.json'
            with patch.object(bridge,'Console',return_value=console),patch.object(bridge,'verify_game_process',return_value=None),\
                 patch.object(sys,'argv',['helper','--seconds','.06','--wait-console','2','--report',str(report)]):
                bridge.main()
            data=json.loads(report.read_text())
        self.assertEqual(console.early_writes,[])
        self.assertGreater(data['samples'],0,'Helper did not resume after initialization')
        self.assertEqual(data['lifecycle']['session'],'final-map')

    def test_unchanged_button_repairs_engine_drift(self):
        console=FakeConsole()
        console.last_state={'screenShake':False}
        console.view_punch_decay=18
        bridge.sync_screen_shake(console,False)
        self.assertTrue(any(command.startswith('view_punch_decay 10000') for _,command in console.commands),
                        'Unchanged OFF button did not repair actual engine value')

    def test_matching_engine_value_does_not_repeat_write(self):
        console=FakeConsole()
        console.last_state={'screenShake':False}
        console.view_punch_decay=10000
        bridge.sync_screen_shake(console,False)
        self.assertFalse(console.commands)

    def exercise(self, departure):
        console = FakeConsole(departure)
        with tempfile.TemporaryDirectory() as folder:
            report = Path(folder) / 'report.json'
            with patch.object(bridge, 'Console', return_value=console), \
                 patch.object(bridge, 'verify_game_process', return_value=None, create=True), \
                 patch.object(sys, 'argv', ['helper', '--seconds', '.07', '--report', str(report)]):
                bridge.main()
            data = json.loads(report.read_text(encoding='utf-8'))
        return console, data

    def test_return_to_menu_stops_writes_even_with_console_connected(self):
        console, _ = self.exercise('menu')
        self.assertTrue(console.closed)
        unsafe = [cmd for left, cmd in console.commands if left and (
            cmd.startswith('akviewdelta ') or cmd.startswith('view_punch_decay ') or cmd.startswith('akcamera '))]
        self.assertEqual(unsafe, [], 'Helper kept modifying the game after leaving training')

    def test_other_map_remote_dedicated_timeout_and_stale_reply_stop(self):
        for departure in ('other_map', 'remote', 'dedicated', 'timeout', 'stale'):
            with self.subTest(departure=departure):
                console, data = self.exercise(departure)
                self.assertTrue(console.closed)
                self.assertIn('exitReason', data)
                self.assertNotEqual(data['exitReason'], 'time_limit')


if __name__ == '__main__':
    unittest.main(verbosity=2)
