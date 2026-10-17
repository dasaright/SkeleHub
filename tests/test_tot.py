import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from core import DEFAULT, snapshot, read_status, write_control
from worker import Worker, read_ini
from tot import OpenToT, BAG, COOKIE, CAKE
from test_python_worker import FakeGame, Clock


class ToTGame(FakeGame):
    def __init__(self):
        super().__init__()
        self.items, self.stored, self.nextid = [], [], 100
        self.bank_full = False
        self.drops = [6049, 6367, COOKIE, 28431, 28432]
        self.target['distance'] = 100
        self.lost_reply = False

    def add(self, model, qty, storage=False):
        target = self.stored if storage else self.items
        while qty:
            old = next((i for i in target if i['model'] == model and i['qty'] < 250), None)
            if old:
                n = min(qty, 250-old['qty'])
                old['qty'] += n
            else:
                n = min(qty, 250)
                target.append(dict(id=self.nextid, model=model, qty=n))
                self.nextid += 1
            qty -= n

    def total(self, model, storage=False):
        return sum(i['qty'] for i in (self.stored if storage else self.items) if i['model'] == model)

    def take(self, model, qty):
        for item in list(self.items):
            if item['model'] == model:
                n = min(qty, item['qty'])
                item['qty'] -= n
                qty -= n
                if not item['qty']:
                    self.items.remove(item)
            if qty == 0:
                break

    def call(self, name, *args):
        self.calls.append((name, *args))
        if name == 'tot_inventory':
            def encode(items, bag):
                return ','.join(f"{i['id']}:{i['model']}:{i['qty']}:{bag}:{n+1}" for n, i in enumerate(items))
            return f'items={encode(self.items, 1)}\tstored={encode(self.stored, 8)}\tfree={20-len(self.items)}'
        if name == 'travel':
            self.s.update(map=args[0], region=args[1], district=args[2] or 1, language=args[3], instance=0)
        if name == 'npc_name':
            return '43'
        if name == 'tot_exchange':
            if self.total(COOKIE) < 50:
                return '0'
            self.take(COOKIE, 50)
            self.add(CAKE, 1)
        elif name.startswith('tot_'):
            target = self.stored if name == 'tot_withdraw' else self.items
            item = next(i for i in target if i['id'] == args[0])
            if name == 'tot_open':
                assert item['model'] == BAG
                self.take(BAG, 1)
                self.add(self.drops.pop(0), 1)
            elif name == 'tot_delete':
                assert item['qty'] == 250 and item['model'] in (6049, 6369, 15837)
                self.items.remove(item)
            elif name == 'tot_bank':
                assert item['qty'] == 250
                if self.bank_full:
                    return '0'
                self.items.remove(item)
                self.add(item['model'], item['qty'], True)
            elif name == 'tot_withdraw':
                self.stored.remove(item)
                self.add(item['model'], item['qty'])
            if self.lost_reply:
                self.lost_reply = False
                raise RuntimeError('Simulated lost acknowledgement')
        return '1'


class ToTTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        config = copy.deepcopy(DEFAULT)
        config['accounts'] = [dict(id='one', character='Alpha Farm Char', team='Team 1', leader=True)]
        snapshot(config, 'Team 1', self.root)
        self.game, self.clock = ToTGame(), Clock()
        self.w = Worker(self.root, 'one', self.game, clock=self.clock)
        self.w.mode, self.w.phase, self.w.build_verified = 'pause', 'Paused', True
        self.w.s = dict(self.game.s)
        write_control(self.w.command_path, mode='pause')

    def run_job(self, limit=250):
        for _ in range(limit):
            self.clock.advance(1.1)
            self.w.s = dict(self.game.s)
            self.w.tot.tick()
            if not self.w.tot.active or self.w.tot.state.get('hold'):
                return
        self.fail('ToT workflow did not finish')

    def test_complete_job_uses_storage_bags_only_full_stack_actions_and_all_cookies(self):
        self.game.add(BAG, 3)
        self.game.add(BAG, 2, True)
        self.game.add(COOKIE, 49)
        self.game.add(COOKIE, 252, True)
        self.game.add(6049, 249)
        self.game.add(6367, 249)
        self.game.add(6368, 250)
        self.game.add(99999, 250)
        self.w.tot.request('one')
        self.run_job()
        self.assertFalse(self.w.tot.active)
        self.assertFalse(self.w.tot.state.get('hold'))
        self.assertEqual(self.game.total(BAG) + self.game.total(BAG, True), 0)
        self.assertEqual(self.game.total(6049), 0)
        self.assertEqual(self.game.total(6367, True), 250)
        self.assertEqual(self.game.total(6368, True), 250)
        self.assertEqual(self.game.total(28431), 1)
        self.assertEqual(self.game.total(28432), 1)
        self.assertEqual(self.game.total(99999), 250)
        self.assertEqual(self.game.total(CAKE), 6)
        self.assertEqual(self.game.total(COOKIE), 2)
        self.assertEqual(self.game.total(COOKIE, True), 0)
        self.assertEqual(self.game.s['map'], 138)
        self.assertEqual(self.w.phase, 'Prepare')
        self.assertEqual(read_ini(self.w.command_path)['Control']['Mode'], 'run')
        self.assertIn(('travel', 248, 0, 0, 0), self.game.calls)
        self.assertIn(('npc_name', 'Kazuma'), self.game.calls)

    def test_bank_full_keeps_full_stack_and_does_not_delete_partial_items(self):
        self.game.bank_full = True
        self.game.add(6367, 250)
        self.game.add(6049, 249)
        self.game.add(6369, 249)
        self.game.add(15837, 249)
        self.w.tot.request('one')
        self.run_job()
        self.assertEqual(self.game.total(6367), 250)
        self.assertTrue(all(self.game.total(m) == 249 for m in (6049, 6369, 15837)))
        self.assertFalse(any(c[0] == 'tot_delete' for c in self.game.calls))

    def test_only_paused_accounts_can_start_and_duplicate_clicks_do_not_reset_job(self):
        self.w.mode = 'run'
        self.w.tot.request('wrong')
        self.assertFalse(self.w.tot.active)
        self.w.mode = 'pause'
        self.w.tot.request('new')
        self.w.tot.stage('cookies')
        self.w.tot.request('again')
        self.assertEqual(self.w.tot.state['stage'], 'cookies')
        self.w.tot.request('again')
        self.assertEqual(self.w.tot.state['stage'], 'cookies')

    def test_lost_bridge_reply_resumes_receipt_without_duplicate_delete(self):
        self.game.s.update(map=248, region=0)
        self.game.add(6049, 250)
        self.w.tot.request('one')
        self.w.tot.stage('open')
        self.game.lost_reply = True
        with self.assertRaises(RuntimeError):
            self.w.s = dict(self.game.s)
            self.w.tot.tick()
        self.w.tot = OpenToT(self.w)
        self.run_job()
        self.assertEqual(sum(c[0] == 'tot_delete' for c in self.game.calls), 1)

    def test_unconfirmed_transaction_holds_without_retry(self):
        self.game.s.update(map=248, region=0)
        self.game.add(6049, 250)
        self.w.tot.request('one')
        self.w.tot.stage('open')
        self.w.s = dict(self.game.s)
        with patch.object(self.game, 'call', side_effect=lambda name, *args: ToTGame.call(self.game, name, *args) if name != 'tot_delete' else '1'):
            self.w.tot.tick()
            with patch('tot.time.time', return_value=10**12):
                self.clock.advance(1)
                self.w.tot.tick()
        self.assertTrue(self.w.tot.state['hold'])
        self.assertEqual(self.game.total(6049), 250)
