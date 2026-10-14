import copy
from pathlib import Path
import tempfile
import unittest
from core import DEFAULT, snapshot, write_control, read_status
from worker import Worker, SKILLS


class Clock:
    value = 100.0
    def __call__(self):
        return self.value
    def advance(self, seconds):
        self.value += seconds


class FakeGame:
    def __init__(self):
        self.calls = []
        self.s = dict(map=138, instance=0, ingame=1, alive=1, login=11, leader=11,
                      roster='11:1', heroes=0, henchmen=0, party=3, region=-2, district=1,
                      language=0, x=-4100, y=19829, rendering=0, dead=0, casting=0,
                      skills=','.join(map(str, SKILLS)), cooldowns='0,0,0,0,0,0,0,0')
        self.inv = dict(captured=0, mobstoppers=0, free=0, gold=1000, storage_gold=0)
        self.target = dict(exists=1, dead=0, hp=.7, model=2392, distance=200)
    def call(self, name, *args):
        self.calls.append((name, *args))
        if name == 'nearest':
            return '42'
        if name == 'cast':
            return '0.3'
        return '1'
    def snapshot(self):
        return dict(self.s)
    def inventory(self):
        self.calls.append(('inventory',))
        return dict(self.inv)
    def agent(self, target):
        return dict(self.target)
    def close(self):
        pass


class PythonWorkerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)
        self.config = copy.deepcopy(DEFAULT)
        self.config['accounts'] = [dict(id='one', character='Alpha Farm Char', team='Team 1', leader=True)]
        snapshot(self.config, 'Team 1', self.path)
        self.game, self.clock = FakeGame(), Clock()
        self.worker = Worker(self.path, 'one', self.game, clock=self.clock)

    def phase(self, phase):
        self.worker.change(phase, 'test')
        self.worker.s = dict(self.game.s)

    def test_combat_test_skips_mobstopper_and_free_slot_gates(self):
        self.phase('Prepare')
        self.worker.tick()
        self.clock.advance(3)
        self.worker.tick()
        self.assertEqual(self.worker.phase, 'Party')
        self.assertNotIn(('inventory',), self.game.calls)

    def test_farm_mode_retains_supply_checks(self):
        self.worker.test_mode = False
        self.phase('Prepare')
        self.worker.tick()
        self.assertEqual(self.worker.phase, 'Error')
        self.assertIn('Mobstopper', self.worker.state)

    def test_kill_waits_two_seconds_then_resigns_without_capture(self):
        self.game.s.update(map=72, instance=1)
        self.game.target['dead'] = 1
        self.phase('Fight')
        self.worker.tick()
        self.assertEqual(self.worker.phase, 'Done')
        self.assertEqual(self.worker.kills, 1)
        self.assertEqual(self.worker.captures, 0)
        self.clock.advance(1.999)
        self.worker.tick()
        self.assertNotIn(('resign',), self.game.calls)
        self.clock.advance(.001)
        self.worker.tick()
        self.assertEqual(self.worker.phase, 'Return')
        self.worker.tick()
        self.assertIn(('resign',), self.game.calls)
        self.assertFalse(any(call[0] == 'capture' for call in self.game.calls))

    def test_every_account_repeats_return_even_when_not_game_leader(self):
        self.game.s.update(map=72, instance=1, leader=999)
        self.worker.is_leader = False
        self.phase('Return')
        self.clock.advance(2)
        self.worker.tick()
        first = self.game.calls.count(('return',))
        self.clock.advance(2.1)
        self.worker.tick()
        self.assertEqual(first, 1)
        self.assertEqual(self.game.calls.count(('return',)), 2)

    def test_waits_for_actual_toa_outpost_before_next_prepare(self):
        self.game.s.update(map=72, instance=1)
        self.phase('Return')
        self.worker.tick()
        self.assertEqual(self.worker.phase, 'Return')
        self.game.s.update(map=138, instance=2)
        self.worker.tick()
        self.assertEqual(self.worker.phase, 'Return')
        self.game.s['instance'] = 0
        self.worker.tick()
        self.assertEqual(self.worker.phase, 'Prepare')

    def test_configured_leader_regroups_if_in_game_leadership_changed(self):
        self.game.s['leader'] = 999
        self.phase('Party')
        self.worker.tick()
        self.assertIn(('leave',), self.game.calls)
        self.game.s['leader'] = 11
        self.clock.advance(3)
        self.worker.tick()
        self.assertEqual(self.worker.phase, 'Move')

    def test_test_mode_always_kneels_before_entry_dialog(self):
        self.phase('Entry')
        self.worker.all_ready = lambda: True
        self.worker.tick()
        self.assertIn(('kneel',), self.game.calls)
        self.assertFalse(any(c[0] == 'dialog' for c in self.game.calls))

    def test_lost_target_does_not_count_as_kill(self):
        self.game.s.update(map=72, instance=1)
        self.game.target['exists'] = 0
        self.phase('Fight')
        self.worker.tick()
        self.assertEqual(self.worker.kills, 0)
        self.assertEqual(self.worker.phase, 'Fight')

    def test_farm_capture_still_requires_inventory_increase(self):
        self.worker.test_mode = False
        self.game.s.update(map=72, instance=1)
        self.game.inv['captured'] = 1
        self.phase('Fight')
        self.worker.tick()
        self.assertEqual(self.worker.captures, 1)
        self.assertEqual(self.worker.kills, 0)

    def test_rendering_command_preserves_pause_and_restores_live_state(self):
        write_control(self.worker.command_path, mode='pause')
        write_control(self.worker.command_path, rendering=True)
        self.phase('Party')
        self.worker.tick()
        self.assertEqual(self.worker.phase, 'Paused')
        self.assertIn(('render', 1), self.game.calls)
        write_control(self.worker.command_path, rendering=False)
        self.game.s['rendering'] = 1
        self.worker.tick()
        self.assertIn(('render', 0), self.game.calls)
        self.worker.publish()
        self.assertEqual(read_status(self.worker.status_path)['mode'], 'pause')


if __name__ == '__main__':
    unittest.main()
