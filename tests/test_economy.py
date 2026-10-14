import copy
import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from core import DEFAULT, snapshot, write_ini, read_status
from economy import Economy, skeleton_gold, total_value, withdrawal_to_target, empty_on_plat, purchase_decision
from worker import Worker
from test_python_worker import FakeGame, Clock


class CurrencyPolicyTests(unittest.TestCase):
    def test_groups_of_three_and_remainders(self):
        self.assertEqual([skeleton_gold(i) for i in (0, 1, 2, 3, 5, 6)], [0, 0, 0, 1000, 1000, 2000])
        self.assertEqual(total_value(dict(gold=2500, storage_gold=7000, captured=8)), 11500)

    def test_withdraw_only_missing_amount_and_available_storage(self):
        self.assertEqual(withdrawal_to_target(dict(gold=7000, storage_gold=50000)), 13000)
        self.assertEqual(withdrawal_to_target(dict(gold=19000, storage_gold=500)), 500)
        self.assertEqual(withdrawal_to_target(dict(gold=25000, storage_gold=50000)), 0)
        self.assertFalse(empty_on_plat(dict(gold=5000, storage_gold=0)))
        self.assertTrue(empty_on_plat(dict(gold=4999, storage_gold=0)))
        self.assertFalse(empty_on_plat(dict(gold=0, storage_gold=1)))

    def test_band_and_bulk_skeleton_liquidation(self):
        self.assertEqual(purchase_decision(dict(gold=9000, storage_gold=850000, captured=0), 5000), 'band')
        self.assertEqual(purchase_decision(dict(gold=10000, storage_gold=895000, captured=300), 5000), 'buy')
        self.assertEqual(purchase_decision(dict(gold=0, storage_gold=950000, captured=0), 5000), 'withdraw')
        self.assertEqual(purchase_decision(dict(gold=4000, storage_gold=0, captured=3003), 5000), 'turnin')
        self.assertEqual(purchase_decision(dict(gold=10000, storage_gold=0, captured=3003), 5000), 'buy')
        self.assertEqual(purchase_decision(dict(gold=900000, captured=300), 150000), 'quote')


class EconomyWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        config = copy.deepcopy(DEFAULT)
        config['accounts'] = [dict(id='one', character='Alpha Farm Char', team='Team 1', leader=True),
                              dict(id='two', character='Beta Farm Char', team='Team 1', leader=False)]
        snapshot(config, 'Team 1', self.path)
        self.game, self.clock = FakeGame(), Clock()
        self.worker = Worker(self.path, 'one', self.game, clock=self.clock)
        self.worker.s = dict(self.game.s)
        self.worker.phase = 'Ready'
        self.worker.exact_party = lambda: True
        self.worker.current_entry_leader = lambda: 'one'
        self.e = self.worker.economy
        self.peer(gold=50000, storage=0)

    def peer(self, gold=0, storage=0, **extra):
        data = dict(PID=123, Mode='run', Map=138, Phase='Ready', Login=22, FundsKnown=1,
                    Gold=gold, StorageGold=storage, Region=-2, Language=0, District=1, Instance=0, EmptyPlat=int(gold < 5000 and storage == 0))
        data.update(extra)
        write_ini(self.path / 'two.status.ini', {'Worker': data})

    def shared(self, **changes):
        data = self.e.read_shared()
        data.update(changes)
        self.e.shared = data
        self.e.save_shared()

    def tick(self):
        self.clock.advance(1.1)
        with patch('worker.process_alive', return_value=True):
            return self.e.tick()

    def test_refill_to_twenty_then_keep_leading_without_storage(self):
        self.game.inv.update(gold=7000, storage_gold=30000)
        self.assertTrue(self.tick())
        self.assertIn(('gold', 13000), self.game.calls)
        self.game.inv.update(gold=20000, storage_gold=17000)
        self.assertFalse(self.tick())
        self.game.inv.update(gold=5000, storage_gold=0)
        self.assertFalse(self.tick())
        self.assertEqual(self.e.read_shared()['mode'], 'farm')

    def test_empty_leader_rotates_to_funded_follower(self):
        self.game.inv.update(gold=4000, storage_gold=0)
        self.assertTrue(self.tick())
        state = self.e.read_shared()
        self.assertEqual((state['mode'], state['leader'], state['empty']), ('rotate', 'two', ['one']))
        self.assertEqual(self.worker.state, 'Empty on Plat — handing leader role to a funded follower')
        self.tick()
        self.assertIn(('leave',), self.game.calls)
        self.assertEqual(self.worker.leader_id, 'two')

    def test_unknown_follower_funds_do_not_trigger_all_empty(self):
        self.peer(FundsKnown=0)
        self.game.inv.update(gold=0, storage_gold=0)
        self.tick()
        self.assertEqual(self.e.read_shared()['mode'], 'farm')

    def test_all_empty_waits_for_explicit_turnin_gate(self):
        self.peer(gold=3000)
        self.game.inv.update(gold=4000, storage_gold=0)
        self.tick()
        self.assertEqual(self.e.read_shared()['mode'], 'turnin')
        self.tick()
        self.assertEqual(self.worker.phase, 'AwaitTurnIn')
        self.assertFalse(any(c[0] in ('travel', 'dialog', 'ecto_buy') for c in self.game.calls))

    def start_turnin(self, stage):
        self.e.turnin_enabled = True
        self.shared(mode='turnin', generation=1)
        self.e.progress = dict(generation=1, district=1)
        self.e.stage(stage)
        self.game.inv.update(captured=6, gold=0, storage_gold=0, free=3, tot=0, ecto=0)

    def test_quest_dialogs_wait_for_actual_reward_then_bank(self):
        self.start_turnin('dialog')
        self.e.progress.update(dialog_index=0, before_captured=6, before_tot=0)
        for _ in range(3):
            self.tick()
        self.assertEqual([c[1] for c in self.game.calls if c[0] == 'dialog'], [0x846303, 0x846301, 0x846307])
        self.assertEqual(self.e.progress['stage'], 'reward')
        self.tick()
        self.assertEqual(self.e.progress['stage'], 'reward')
        self.game.inv.update(captured=3, tot=10, gold=1000)
        self.tick()
        self.assertEqual(self.e.progress['stage'], 'bank')
        self.tick()
        self.tick()
        self.assertIn(('bank', 28434), self.game.calls)
        self.game.inv['tot'] = 0
        self.tick()
        self.assertEqual(self.e.progress['stage'], 'deposit')

    def test_bank_failure_holds_without_restarting_or_losing_skeletons(self):
        self.start_turnin('bank')
        self.game.inv['tot'] = 10
        original = self.game.call
        self.game.call = lambda name, *args: '0' if name == 'bank' else original(name, *args)
        self.tick()
        self.tick()
        self.assertEqual(self.worker.phase, 'EconomyHold')
        self.assertEqual(self.game.inv['captured'], 6)

    def test_buy_acknowledgement_requires_ecto_and_gold_change(self):
        self.start_turnin('buy_wait')
        self.e.progress.update(before_ecto=0, before_gold=10000)
        self.game.inv.update(gold=5000, ecto=0)
        self.tick()
        self.assertEqual(self.e.progress['stage'], 'buy_wait')
        self.game.inv['ecto'] = 1
        self.tick()
        self.assertEqual(self.e.progress['stage'], 'quote')

    def test_district_alternates_and_two_skeletons_return_home(self):
        self.start_turnin('district')
        self.tick()
        self.assertEqual(self.e.progress['district'], 2)
        self.game.inv['captured'] = 2
        self.tick()
        self.assertEqual(self.e.progress['stage'], 'home')
        self.tick()
        self.assertEqual(self.e.progress['stage'], 'done')
        self.assertEqual(self.e.progress['done_generation'], 1)

    def test_complete_team_turnin_resets_empty_flags_and_resumes_preparation(self):
        self.start_turnin('done')
        self.e.progress['done_generation'] = 1
        self.game.inv['storage_gold'] = 10000
        self.peer(EconomyDone=1)
        self.tick()
        self.assertEqual(self.e.read_shared()['mode'], 'farm')
        self.assertEqual(self.e.read_shared()['empty'], [])
        self.assertEqual(self.worker.phase, 'Prepare')

    def test_full_simulated_turnin_route_banks_rewards_switches_district_and_rejoins(self):
        self.worker.members = [self.worker.member]
        self.start_turnin('leave')
        self.game.inv['captured'] = 20
        self.game.target['distance'] = 100
        original = self.game.call
        districts = []
        def act(name, *args):
            result = original(name, *args)
            if name == 'leave':
                self.game.s['roster'] = '11:1'
            elif name == 'travel':
                self.game.s.update(map=args[0], region=args[1], district=args[2], language=args[3], instance=0)
                if args[0] == 55:
                    districts.append(args[2])
            elif name == 'npc_near':
                return '42'
            elif name == 'dialog' and args[0] == 0x846307:
                self.game.inv['captured'] -= 3
                self.game.inv['gold'] += 1000
                self.game.inv['tot'] += 10
            elif name == 'bank':
                self.game.inv['tot'] = 0
            elif name == 'deposit':
                self.game.inv['gold'] -= args[0]
                self.game.inv['storage_gold'] += args[0]
            return result
        self.game.call = act
        for _ in range(160):
            self.worker.s = dict(self.game.s)
            self.tick()
            if self.e.read_shared()['mode'] == 'farm':
                break
        self.assertEqual(self.game.inv['captured'], 2)
        self.assertEqual(self.game.inv['tot'], 0)
        self.assertEqual(self.game.inv['storage_gold'], 6000)
        self.assertEqual(districts, [1, 2, 1, 2, 1, 2])
        self.assertEqual(self.game.s['map'], 138)
        self.assertEqual(self.worker.phase, 'Prepare')

    def test_simulated_ecto_trip_uses_quotes_and_stops_inside_band(self):
        self.start_turnin('embark')
        self.game.inv.update(storage_gold=920000, gold=0, captured=0)
        self.game.target['distance'] = 100
        self.worker.members = [self.worker.member]
        original = self.game.call
        def act(name, *args):
            result = original(name, *args)
            if name == 'travel':
                self.game.s.update(map=args[0], region=args[1], district=args[2], language=args[3], instance=0)
            elif name == 'npc_name':
                return '43'
            elif name == 'ecto_quote':
                return '5000'
            elif name == 'gold':
                self.game.inv['storage_gold'] -= args[0]
                self.game.inv['gold'] += args[0]
            elif name == 'ecto_buy':
                self.game.inv['gold'] -= args[0]
                self.game.inv['ecto'] += 1
            return result
        self.game.call = act
        for _ in range(80):
            self.worker.s = dict(self.game.s)
            self.tick()
            if self.e.read_shared()['mode'] == 'farm':
                break
        self.assertEqual(self.game.inv['ecto'], 4)
        self.assertEqual(total_value(self.game.inv), 900000)
        self.assertEqual(self.game.s['map'], 138)
        self.assertEqual(self.worker.phase, 'Prepare')


    def test_turnins_do_not_loop_forever_when_no_account_can_fund_entry(self):
        self.start_turnin('done')
        self.e.progress['done_generation'] = 1
        self.peer(EconomyDone=1)
        self.game.inv.update(gold=0, storage_gold=0, captured=2)
        self.tick()
        self.assertEqual(self.e.read_shared()['mode'], 'hold')
        self.assertEqual(self.worker.phase, 'EconomyHold')


    def test_manual_currency_works_with_rotation_disabled_and_retains_pause(self):
        self.e.enabled = False
        self.worker.build_verified = True
        self.worker.mode = 'pause'
        self.worker.members = [self.worker.member]
        self.e.request_currency('manual-one')
        self.game.inv.update(storage_gold=920000, gold=0, captured=0, free=3, ecto=0)
        self.game.target['distance'] = 100
        original = self.game.call
        def act(name, *args):
            result = original(name, *args)
            if name == 'travel':
                self.game.s.update(map=args[0], region=args[1], district=args[2], language=args[3], instance=0)
            elif name == 'npc_name':
                return '43'
            elif name == 'ecto_quote':
                return '5000'
            elif name == 'gold':
                self.game.inv['storage_gold'] -= args[0]
                self.game.inv['gold'] += args[0]
            elif name == 'ecto_buy':
                self.game.inv['gold'] -= args[0]
                self.game.inv['ecto'] += 1
            return result
        self.game.call = act
        for _ in range(90):
            self.worker.s = dict(self.game.s)
            self.tick()
            if not self.e.currency_pending:
                break
        self.assertFalse(self.e.currency_pending)
        self.assertEqual(self.game.inv['ecto'], 4)
        self.assertEqual(total_value(self.game.inv), 900000)
        self.assertEqual(self.worker.phase, 'Paused')
        self.assertEqual(self.game.s['map'], 138)
        self.assertFalse(any(c[0] == 'dialog' for c in self.game.calls))
        self.e.request_currency('manual-one')
        self.assertFalse(self.e.currency_pending)  # no replay of a consumed command
        self.assertEqual(self.e.read_shared()['mode'], 'farm')

    def test_currency_requests_coalesce_and_do_not_restart_pending_purchase(self):
        self.e.request_currency('one')
        self.e.currency.update(stage='buy_wait', before_gold=10000, before_ecto=0)
        self.e.request_currency('two')
        self.assertEqual(self.e.currency['stage'], 'buy_wait')
        self.assertEqual(self.e.currency['seen'], 'two')
        self.assertEqual(self.e.currency['generation'], 'one')

    def test_currency_request_waits_for_outpost(self):
        self.worker.build_verified = True
        self.e.request_currency('outpost')
        self.worker.s.update(map=72, instance=1)
        self.assertFalse(self.e.tick())
        self.assertFalse(any(c[0] in ('leave', 'travel') for c in self.game.calls))
        self.assertTrue(self.e.currency_pending)
