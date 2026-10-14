import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from core import DEFAULT, snapshot, write_control, read_status
from worker import Worker, SKILLS, SEQUENCE


class Clock:
    value = 100.0
    def __call__(self):
        return self.value
    def advance(self, seconds):
        self.value += seconds


class FakeGame:
    def __init__(self):
        self.calls = []
        self.s = dict(character="Alpha Farm Char", primary=7, secondary=3, smiting=12, shadow=12, map=138, instance=0, ingame=1, alive=1, login=11, leader=11,
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

    def login_script(self, frames):
        original = self.game.call
        frames = iter(frames)
        def call(name, *args):
            if name == 'login':
                self.game.calls.append((name, *args))
                return next(frames)
            return original(name, *args)
        self.game.call = call
        self.worker.login_wait = lambda seconds=.5: (self.clock.advance(seconds) or True)

    def test_character_selection_matches_encounter_sequence(self):
        self.login_script([
            'alive=1\tselection=1\tindex=2\tselected=Wrong Char',
            'alive=1\tselection=1\tindex=0\tselected=Another Char',
            'alive=1\tselection=1\tindex=1\tselected=Alpha Farm Char',
            'alive=1\tingame=1',
        ])
        self.assertTrue(self.worker.select_character())
        self.assertEqual([c for c in self.game.calls if c[0] == 'key'],
                         [('key', 'N'), ('key', 'RIGHT'), ('key', 'ENTER')])
        self.assertEqual(self.worker.phase, 'Travel')
        self.assertIn(('render', 1), self.game.calls)
        self.assertIn(('leave',), self.game.calls)
        self.assertTrue(self.worker.render_disabled)

    def test_missing_character_never_enters_wrong_character(self):
        self.login_script(['alive=1\tselection=1\tindex=0\tselected=Wrong'] + [
            f'alive=1\tselection=1\tindex={i}\tselected=Wrong' for i in (0, 1, 0)])
        self.worker.select_character()
        self.assertEqual(self.worker.phase, 'Error')
        self.assertNotIn(('key', 'ENTER'), self.game.calls)

    def test_wrong_loaded_character_blocks_travel_and_build(self):
        self.game.s['character'] = 'Wrong Character'
        self.login_script(['alive=1\tingame=1'])
        self.worker.select_character()
        self.assertEqual(self.worker.phase, 'Error')
        self.assertFalse(any(c[0] in ('build', 'travel') for c in self.game.calls))

    def test_new_launch_attaches_returned_pid(self):
        original = self.game.call
        self.worker.member['launchdirect'] = '1'
        def call(name, *args):
            if name in ('attach', 'launch', 'attach_pid'):
                self.game.calls.append((name, *args))
                return {'attach': '0', 'launch': '4321', 'attach_pid': '1'}[name]
            return original(name, *args)
        self.game.call = call
        self.worker.login_wait = lambda seconds=3: True
        self.worker.select_character = lambda: True
        self.assertTrue(self.worker.attach())
        self.assertIn(('attach_pid', 4321), self.game.calls)
        self.assertEqual(sum(c[0] == 'attach' for c in self.game.calls), 1)

    def test_template_waits_for_attributes_and_all_skills(self):
        self.game.s.update(secondary=0, smiting=0, shadow=0, skills='0,0,0,0,0,0,0,0')
        self.phase('Prepare')
        self.worker.tick()
        self.clock.advance(3)
        self.worker.tick()
        self.assertEqual(self.worker.phase, 'Prepare')
        self.assertEqual(sum(c[0] == 'build' for c in self.game.calls), 1)
        self.game.s.update(secondary=3, smiting=12, shadow=12, skills=','.join(map(str, SKILLS)))
        self.worker.tick()
        self.assertEqual(self.worker.phase, 'Party')

    def test_wrong_primary_fails_before_loading_template(self):
        self.game.s['primary'] = 1
        self.phase('Prepare')
        self.worker.tick()
        self.assertEqual(self.worker.phase, 'Error')
        self.assertFalse(any(c[0] == 'build' for c in self.game.calls))

    def test_template_verification_has_bounded_retries(self):
        self.game.s['smiting'] = 0
        self.phase('Prepare')
        for _ in range(4):
            self.worker.tick()
            self.clock.advance(16)
        self.assertEqual(self.worker.phase, 'Error')
        self.assertEqual(sum(c[0] == 'build' for c in self.game.calls), 3)

    def test_new_template_skips_empty_first_slot(self):
        self.assertEqual(SKILLS[0], 0)
        self.assertNotIn(1, SEQUENCE)

    def test_hub_exit_stops_worker_even_with_run_command(self):
        self.phase('Party')
        self.worker.hub_pid = 999
        with patch('worker.process_alive', return_value=False):
            self.assertFalse(self.worker.tick())
            self.assertFalse(self.worker.login_wait())

    def test_stop_closes_only_bound_client_through_bridge(self):
        write_control(self.worker.command_path, mode='stop', close_game=True)
        self.worker.run()
        self.assertIn(('close_game',), self.game.calls)
        self.assertEqual(self.worker.phase, 'Stopped')

    def test_hub_close_leaves_game_open(self):
        write_control(self.worker.command_path, mode='stop', close_game=False)
        self.worker.run()
        self.assertNotIn(('close_game',), self.game.calls)
        self.assertEqual(self.worker.phase, 'Stopped')

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
