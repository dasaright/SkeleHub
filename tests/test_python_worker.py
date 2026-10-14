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
            if args[0] == 2:
                self.s['cooldowns'] = '0,10000,0,0,0,0,0,0'
                self.target['distance'] = 150
            if args[0] == 3:
                values = self.s['cooldowns'].split(',')
                values[2] = '10000'
                self.s['cooldowns'] = ','.join(values)
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
        self.config['teams']['Team 1']['funding_rotation'] = False
        self.config['accounts'] = [dict(id='one', character='Alpha Farm Char', team='Team 1', leader=True)]
        snapshot(self.config, 'Team 1', self.path)
        # These tests isolate combat/assembly; funding selection has dedicated coverage.
        import json
        economy_path = self.path / 'economy.json'
        shared = json.loads(economy_path.read_text())
        shared['leader_selected'] = True
        economy_path.write_text(json.dumps(shared))
        self.game, self.clock = FakeGame(), Clock()
        self.worker = Worker(self.path, 'one', self.game, clock=self.clock)

    def phase(self, phase):
        self.worker.change(phase, 'test')
        self.worker.s = dict(self.game.s)
        if phase == 'Prepare':
            self.clock.advance(2.5)

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
        self.assertEqual(self.worker.phase, 'Initialize')
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

    def test_new_template_skips_empty_eighth_slot(self):
        self.assertEqual(SKILLS[7], 0)
        self.assertNotIn(8, SEQUENCE)

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

    def test_seven_skill_sequence_keeps_attacking_and_repeats_damage(self):
        self.game.s.update(map=72, instance=1)
        self.phase('Fight')
        self.worker.combat_started = True
        self.worker.step = len(SEQUENCE)
        self.worker.target = 42
        self.worker.tick()
        self.assertIn(('attack', 42), self.game.calls)
        self.assertEqual(self.worker.step, SEQUENCE.index(4))

    def test_uw_readiness_names_failed_peer_and_returns_after_grace(self):
        from core import write_ini
        self.worker.members.append({'id': 'two', 'character': 'Failed Leader'})
        self.game.s.update(map=72, instance=1)
        self.phase('Fight')
        write_ini(self.path / 'two.status.ini', {'Worker': {'PID': 123, 'Map': 72, 'Cycle': 0, 'Phase': 'Error'}})
        with patch('worker.process_alive', return_value=True):
            self.worker.tick()
            self.assertIn('Failed Leader: needs attention', self.worker.state)
            self.clock.advance(10)
            self.worker.tick()
        self.assertEqual(self.worker.phase, 'Done')
        self.assertEqual(self.worker.kills, 0)

    def test_loaded_uw_overrides_stale_town_phases(self):
        for phase in ('Travel', 'Prepare', 'Party', 'Ready', 'Move', 'Entry'):
            self.game.s.update(map=72, instance=1)
            self.phase(phase)
            self.worker.tick()
            self.assertEqual(self.worker.phase, 'Fight', phase)
            self.assertFalse(any(c[0] == 'travel' for c in self.game.calls))

    def test_followers_resynchronize_cycle_while_waiting_in_uw(self):
        from core import write_ini
        self.worker.is_leader = False
        self.worker.leader_id = 'two'
        self.worker.entry_leader_id = 'two'
        self.worker.members.append({'id': 'two', 'character': 'Leader'})
        self.worker.cycle = 0
        write_ini(self.path / 'two.status.ini', {'Worker': {'PID': 123, 'Map': 72, 'Cycle': 3, 'Phase': 'Fight'}})
        with patch('worker.process_alive', return_value=True):
            self.assertTrue(self.worker.all_loaded())
        self.assertEqual(self.worker.cycle, 3)

    def test_return_to_town_does_not_reload_or_revalidate_initialized_template(self):
        self.worker.build_attempts = 1
        self.worker.build_loaded = True
        self.worker.build_verified = True
        self.game.s.update(map=72, instance=1)
        self.phase('Return')
        self.game.s.update(map=138, instance=0, skills='0,0,0,0,0,0,0,0', primary=0)
        self.worker.tick()
        self.assertEqual(self.worker.phase, 'Prepare')
        self.clock.advance(3)
        self.worker.tick()
        self.assertEqual(self.worker.phase, 'Party')
        self.assertEqual(self.worker.build_attempts, 1)
        self.assertFalse(any(c[0] == 'build' for c in self.game.calls))

    def test_initialization_loads_template_before_first_town_travel(self):
        from farm_build import BUILD
        self.game.s['map'] = 55
        self.phase('Initialize')
        self.worker.tick()
        self.assertIn(('build', BUILD), self.game.calls)
        self.assertEqual(self.worker.phase, 'Initialize')
        self.clock.advance(3)
        self.worker.tick()
        self.assertTrue(self.worker.build_verified)
        self.assertEqual(self.worker.phase, 'Travel')
        self.assertFalse(any(c[0] == 'travel' for c in self.game.calls))

    def test_smoke_powder_defense_immediately_follows_confirmed_charge(self):
        self.game.s.update(map=72, instance=1)
        self.game.target['hp'] = .4
        self.phase('Fight')
        self.worker.combat_started = True
        for _ in range(11):
            self.worker.tick()
            self.clock.advance(1)
        casts = [c[1] for c in self.game.calls if c[0] == 'cast']
        self.assertEqual(casts[:7], [1, 2, 3, 7, 4, 5, 6])
        self.assertTrue(self.worker.charge_confirmed)

    def test_leader_and_follower_have_identical_cast_and_attack_loops(self):
        traces = []
        for leader in (True, False):
            self.worker.is_leader = leader
            self.game.calls.clear()
            self.game.s['cooldowns'] = '0,0,0,0,0,0,0,0'
            self.game.s.update(map=72, instance=1)
            self.game.target['hp'] = .4
            self.worker.s = dict(self.game.s)
            self.worker.start_fight()
            self.worker.all_loaded = lambda: True
            for _ in range(10):
                self.worker.tick()
                self.clock.advance(1)
            traces.append([c for c in self.game.calls if c[0] in ('cast', 'attack', 'target')])
        self.assertEqual(traces[0], traces[1])
        self.assertEqual([c[1] for c in traces[0] if c[0] == 'cast'][:7], SEQUENCE)

    def test_combat_deadline_starts_after_team_readiness_for_both_roles(self):
        for leader in (True, False):
            self.worker.is_leader = leader
            self.game.s.update(map=72, instance=1)
            self.worker.s = dict(self.game.s)
            self.worker.start_fight()
            self.worker.all_loaded = lambda: True
            self.clock.advance(55)
            self.worker.tick()
            self.clock.advance(6)
            self.worker.tick()
            self.assertEqual(self.worker.phase, 'Fight')

    def test_canonical_template_decodes_to_verified_professions_attributes_and_slots(self):
        from farm_build import BUILD
        alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'
        bits = ''.join(f'{alphabet.index(c):06b}'[::-1] for c in BUILD)
        def take(n):
            nonlocal bits
            value = int(bits[:n][::-1], 2)
            bits = bits[n:]
            return value
        take(4)
        take(4)
        width = take(2) * 2 + 4
        self.assertEqual((take(width), take(width)), (7, 3))
        count, width = take(4), take(4) + 4
        self.assertEqual(dict((take(width), take(4)) for _ in range(count)), {14: 12, 31: 12})
        width = take(4) + 8
        self.assertEqual([take(width) for _ in range(8)], SKILLS)

    def test_charge_requires_own_request_and_recharge_before_signet(self):
        self.phase('Fight')
        self.worker.target = 42
        self.worker.step = 1
        self.worker.cast_next(self.game.target)
        self.assertFalse(self.worker.charge_confirmed)
        self.assertEqual(self.worker.step, 1)
        self.clock.advance(1)
        self.worker.s = dict(self.game.s)
        self.worker.cast_next(self.game.target)
        self.assertTrue(self.worker.charge_confirmed)
        self.assertEqual(self.worker.step, 2)
        self.assertNotIn(('cast', 4, 42), self.game.calls)

    def test_preexisting_charge_cooldown_never_counts_as_use(self):
        self.game.s['cooldowns'] = '0,1000,0,0,0,0,0,0'
        self.phase('Fight')
        self.worker.step = 1
        self.worker.cast_next(self.game.target)
        self.assertFalse(self.worker.charge_confirmed)
        self.assertFalse(any(c[0] == 'cast' for c in self.game.calls))
        self.assertEqual(self.worker.step, 1)

    def test_unaccepted_charge_retries_without_casting_signet(self):
        self.phase('Fight')
        self.worker.step = 1
        self.worker.target = 42
        for _ in range(4):
            self.worker.s['cooldowns'] = '0,0,0,0,0,0,0,0'
            self.worker.cast_next(self.game.target)
            self.clock.advance(4)
        self.assertEqual(self.worker.phase, 'Done')
        self.assertEqual(self.game.calls.count(('cast', 2, 42)), 3)
        self.assertNotIn(('cast', 4, 42), self.game.calls)

    def test_charge_recharge_without_arrival_blocks_signet(self):
        self.phase('Fight')
        self.worker.step = 1
        self.worker.cast_next(self.game.target)
        self.worker.s = dict(self.game.s)
        self.game.target['distance'] = 900
        self.clock.advance(6)
        self.worker.cast_next(self.game.target)
        self.assertFalse(self.worker.charge_confirmed)
        self.assertEqual(self.worker.phase, 'Done')

    def test_signet_guard_returns_to_charge_if_not_confirmed(self):
        self.phase('Fight')
        self.worker.step = 3
        self.worker.cast_next(self.game.target)
        self.assertEqual(self.worker.step, 1)
        self.assertFalse(any(c[0] == 'cast' for c in self.game.calls))

    def retained_party(self):
        from core import write_ini
        self.worker.members.append({'id': 'two', 'character': 'Beta'})
        self.game.s.update(leader=22, roster='22:1,11:1')
        write_ini(self.path / 'two.status.ini', {'Worker': dict(PID=123, Phase='Ready', Mode='run',
                  Map=138, Region=-2, Language=0, District=1, Login=22, Party=3)})

    def test_complete_party_retains_order_and_current_in_game_leader(self):
        self.retained_party()
        self.phase('Party')
        with patch('worker.process_alive', return_value=True):
            self.worker.tick()
        self.assertEqual(self.worker.phase, 'Ready')
        self.assertEqual(self.worker.entry_leader_id, 'two')
        self.assertNotIn(('leave',), self.game.calls)
        self.assertFalse(any(c[0] in ('invite', 'accept') for c in self.game.calls))

    def test_current_party_leader_can_enter_without_configured_leader_role(self):
        self.retained_party()
        self.worker.is_leader = False
        self.worker.leader_id = 'two'
        self.game.s['leader'] = 11
        self.phase('Party')
        with patch('worker.process_alive', return_value=True):
            self.worker.tick()
        self.assertEqual(self.worker.phase, 'Move')
        self.assertEqual(self.worker.entry_leader_id, self.worker.id)
        self.assertNotIn(('leave',), self.game.calls)

    def test_loaded_visible_party_does_not_deadlock_on_different_run_counters(self):
        from core import write_ini
        self.worker.members.append({'id': 'two', 'character': 'Beta'})
        self.game.s.update(map=72, instance=1, roster='11:1,22:1', visible='11,22')
        self.phase('Fight')
        self.worker.cycle = 4
        write_ini(self.path / 'two.status.ini', {'Worker': dict(PID=123, Map=72, Instance=1,
                  Phase='Fight', Cycle=9, Login=22, Mode='run')})
        with patch('worker.process_alive', return_value=True):
            self.assertTrue(self.worker.all_loaded())
        self.assertEqual(self.worker.cycle, 9)

    def test_other_uw_copy_or_invisible_party_member_is_not_marked_loaded(self):
        from core import write_ini
        self.worker.members.append({'id': 'two', 'character': 'Beta'})
        self.game.s.update(map=72, instance=1, roster='11:1,22:1', visible='11')
        self.phase('Fight')
        write_ini(self.path / 'two.status.ini', {'Worker': dict(PID=123, Map=72, Instance=1,
                  Phase='Fight', Cycle=0, Login=22, Mode='run')})
        with patch('worker.process_alive', return_value=True):
            self.assertFalse(self.worker.all_loaded())
        self.assertIn('not visible in this UW party', self.worker.state)

    def test_game_leader_flag_overrides_roster_order(self):
        from core import write_ini
        self.worker.members.append({'id': 'two', 'character': 'Beta'})
        self.game.s.update(is_party_leader=0, leader=11, roster='11:1,22:1')
        self.phase('Party')
        write_ini(self.path / 'two.status.ini', {'Worker': dict(PID=123, Phase='Ready', Mode='run',
                  Login=22, Map=138, IsPartyLeader=1)})
        with patch('worker.process_alive', return_value=True):
            self.assertEqual(self.worker.current_entry_leader(), 'two')

    def test_smoke_cooldown_is_not_skipped_before_signet(self):
        self.phase('Fight')
        self.worker.charge_confirmed = True
        self.worker.step = SEQUENCE.index(3)
        self.worker.s['cooldowns'] = '0,0,1000,0,0,0,0,0'
        self.worker.cast_next(self.game.target)
        self.assertEqual(self.worker.step, SEQUENCE.index(3))
        self.assertFalse(any(c[0] == 'cast' for c in self.game.calls))
        self.assertFalse(self.worker.smoke_confirmed)

    def test_signet_waits_for_smoke_confirmation(self):
        self.phase('Fight')
        self.worker.charge_confirmed = True
        self.worker.step = SEQUENCE.index(4)
        self.worker.cast_next(self.game.target)
        self.assertEqual(self.worker.step, SEQUENCE.index(3))
        self.worker.cast_next(self.game.target)
        self.clock.advance(1)
        self.worker.s = dict(self.game.s)
        self.worker.cast_next(self.game.target)
        self.assertTrue(self.worker.smoke_confirmed)
        self.assertEqual(self.worker.step, SEQUENCE.index(3) + 1)

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

    def test_configured_leader_does_not_leave_for_party_order_change(self):
        self.game.s['leader'] = 999
        self.phase('Party')
        self.worker.tick()
        self.assertNotIn(('leave',), self.game.calls)


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
