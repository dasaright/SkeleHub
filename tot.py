"""Paused-account ToT opening, exact-stack handling and Kazuma exchange."""
import json
import time
from core import atomic_text, write_control
from game_bridge import fields

GTB, TOA, BAG, COOKIE, CAKE = 248, 138, 28434, 28433, 36681
KEEP = {6367, 6368, 28431, 28432, COOKIE}
DELETE = {6049, 6369, 15837}


def stacks(value):
    result = []
    for item in str(value or '').split(','):
        if not item:
            continue
        values = list(map(int, item.split(':')))
        if len(values) != 5:
            raise ValueError('Invalid inventory snapshot')
        result.append(dict(zip(('id', 'model', 'qty', 'bag', 'slot'), values)))
    return result


def quantity(items, model):
    return sum(i['qty'] for i in items if i['model'] == model)


class OpenToT:
    def __init__(self, worker):
        self.w = worker
        self.path = worker.session / (worker.id + '.tot.json')
        self.state = json.loads(self.path.read_text()) if self.path.exists() else {}
        self.action_at = -1000
        self.stage_at = worker.clock()
        self.storage_ready = False
        self.storage_at = -1000
        self.rejected = ''

    @property
    def active(self):
        return bool(self.state.get('active'))

    def save(self, **changes):
        self.state.update(changes)
        atomic_text(self.path, json.dumps(self.state))

    def stage(self, name):
        self.save(stage=name)
        self.stage_at = self.w.clock()
        self.action_at = -1000

    def request(self, token):
        if not token or token == self.state.get('seen'):
            return
        if self.active:
            self.save(seen=token)  # Never restart or duplicate a pending transaction.
            if self.state.get('hold'):
                self.save(hold='', blocked=[] if not self.state.get('pending') else self.state.get('blocked', []))
            return
        if self.w.mode != 'pause' or self.w.phase != 'Paused' or self.w.s.get('instance') != 0 or self.w.economy.currency_pending:
            self.save(seen=token)
            self.rejected = 'Pause this account in an outpost before Open ToT'
            return
        self.state = dict(seen=token, active=True, stage='leave', blocked=[], pending=None)
        self.save()
        self.stage_at = self.w.clock()

    def due(self, interval=1):
        if self.w.clock() - self.action_at < interval:
            return False
        self.action_at = self.w.clock()
        return True

    def hold(self, message):
        self.save(hold=message)
        self.w.change('ToTHold', 'Open ToT: ' + message)
        return True

    def snapshot(self):
        data = fields(self.w.game.call('tot_inventory'))
        self.storage_ready = int(data.get('storage_ready', 1)) == 1
        return stacks(data.get('items')), stacks(data.get('stored')), int(data.get('free', 0))

    def pending(self, operation, item, items, stored, next_stage=None):
        # Persist before dispatch, so a lost bridge response never blindly repeats it.
        self.save(pending=dict(op=operation, id=item['id'] if item else 0,
                               model=item['model'] if item else COOKIE,
                               before=quantity(items, item['model'] if item else COOKIE),
                               stored=quantity(stored, item['model'] if item else COOKIE),
                               cake=quantity(items, CAKE), started=time.time(), next=next_stage))

    def receipt(self, items, stored):
        p = self.state['pending']
        current = quantity(items, p['model'])
        ok = {'open': current == p['before'] - 1,
              'delete': current == p['before'] - 250,
              'bank': current == p['before'] - 250 and quantity(stored, p['model']) == p['stored'] + 250,
              'withdraw': current > p['before'] and quantity(stored, p['model']) < p['stored'],
              'exchange': current == p['before'] - 50 and quantity(items, CAKE) == p['cake'] + 1}[p['op']]
        if ok:
            next_stage = p.get('next')
            self.save(pending=None)
            if next_stage:
                self.stage(next_stage)
            return True
        if time.time() - p['started'] > 10:
            self.hold('Transaction did not confirm; stopped without repeating. Check inventory and logs.')
        return False

    def mutate(self, command, op, item, items, stored, next_stage=None):
        self.pending(op, item, items, stored, next_stage)
        result = self.w.game.call(command, item['id']) if item else self.w.game.call(command)
        if result == '0':  # Native guard rejected before sending anything.
            self.save(pending=None)
            return False
        return True

    def cleanup(self, items, stored):
        blocked = set(self.state.get('blocked', []))
        for item in items:
            if item['qty'] != 250:
                continue
            if item['model'] in DELETE:
                self.mutate('tot_delete', 'delete', item, items, stored)
                return True
            if item['model'] in KEEP and item['id'] not in blocked:
                if not self.mutate('tot_bank', 'bank', item, items, stored):
                    blocked.add(item['id'])
                    self.save(blocked=list(blocked))
                return True
        return False

    def tick(self):
        if not self.active:
            return False
        w = self.w
        if self.state.get('hold'):
            w.state = 'Open ToT: ' + self.state['hold']
            return True
        if w.s.get('instance') != 0:
            return True
        if not w.build_verified:
            w.initialize()
            return True
        if w.phase not in ('OpenToT', 'ToTHold'):
            w.change('OpenToT', 'Opening ToT bags at Great Temple of Balthazar')
        stage = self.state['stage']
        w.state = 'Open ToT — ' + stage.replace('_', ' ')
        if stage == 'leave':
            if self.due(2):
                w.game.call('leave')
            if len(str(w.s.get('roster', '')).split(',')) <= 1 and not w.s.get('heroes') and not w.s.get('henchmen'):
                self.stage('travel')
            elif w.clock() - self.stage_at > 20:
                self.hold('Could not leave party')
            return True
        if stage in ('travel', 'home'):
            target = GTB if stage == 'travel' else TOA
            region = 0 if target == GTB else w.destination['region']
            district = 0 if target == GTB else w.destination['district']
            if w.s.get('map') == target and (district == 0 or w.s.get('district') == district) and w.s.get('region') == region and w.s.get('language') == w.destination['language']:
                self.stage('kazuma' if target == GTB else 'done')
            elif self.due(5):
                w.game.call('travel', target, region, district, w.destination['language'])
            if w.clock() - self.stage_at > 90:
                self.hold('Travel timed out; verify outpost access')
            return True
        if stage == 'done':
            self.save(active=False)
            write_control(w.command_path, mode='run')
            w.mode = 'run'
            w.change('Prepare', 'Open ToT complete; returned to ToA and awaiting party reform')
            return True
        # Confirm in-flight receipts before any further inventory action, even after restart.
        if w.s.get('map') != GTB:
            if self.state.get('pending'):
                return self.hold('Left Great Temple during an unconfirmed transaction; check inventory')
            self.stage('travel')
            return True
        if stage == 'kazuma':
            npc = int(w.game.call('npc_name', 'Kazuma'))
            if npc and w.game.agent(npc).get('distance', 99999) <= 200:
                w.game.call('npc', npc)
                w.game.call('storage')
                self.stage('open')
            elif npc and self.due(2):
                w.game.call('npc', npc)
            if w.clock() - self.stage_at > 90:
                self.hold('Kazuma could not be reached')
            return True
        if not self.due(.5):
            return True
        items, stored, free = self.snapshot()
        if not self.storage_ready:
            w.state = 'Open ToT — waiting for Xunlai storage inventory'
            if w.clock() - self.storage_at > 3:
                w.game.call('storage')
                self.storage_at = w.clock()
            if w.clock() - self.stage_at > 15:
                self.hold('Xunlai storage inventory is unavailable; no items were assumed missing')
            return True
        if self.state.get('pending'):
            self.receipt(items, stored)
            return True
        if stage == 'open':
            if self.cleanup(items, stored):
                return True
            bag = next((i for i in items if i['model'] == BAG), None)
            if bag:
                if free <= 0 and bag['qty'] != 1:
                    return self.hold('Inventory is full; bank-full keep stacks were retained. Free one slot and click Open ToT again.')
                if not self.mutate('tot_open', 'open', bag, items, stored):
                    return self.hold('Bag action rejected; check inventory')
            else:
                bag = next((i for i in stored if i['model'] == BAG), None)
                if bag:
                    if not self.mutate('tot_withdraw', 'withdraw', bag, items, stored):
                        return self.hold('No room to withdraw ToT bags; free inventory space')
                else:
                    self.stage('cookies')
        elif stage == 'cookies':
            cookie = next((i for i in stored if i['model'] == COOKIE), None)
            if cookie and self.mutate('tot_withdraw', 'withdraw', cookie, items, stored):
                return True
            if quantity(items, COOKIE) >= 50:
                cake_room = free > 0 or any(i['model'] == CAKE and i['qty'] < 250 for i in items) or quantity(items, COOKIE) == 50
                if not cake_room:
                    return self.hold('No room for Delicious Cake; keep items were retained. Free one slot and click Open ToT again.')
                self.stage('exchange')
            elif cookie:
                return self.hold('Inventory is full; cannot withdraw remaining Pumpkin Cookies')
            else:
                self.stage('home')
        elif stage == 'exchange':
            npc = int(w.game.call('npc_name', 'Kazuma'))
            if not npc or w.game.agent(npc).get('distance', 99999) > 200:
                if npc:
                    w.game.call('npc', npc)
                if w.clock() - self.stage_at > 90:
                    self.hold('Could not return to Kazuma for cookie exchange')
            else:
                w.game.call('npc', npc)
                self.stage('exchange_ready')
        elif stage == 'exchange_ready':
            if not self.mutate('tot_exchange', 'exchange', None, items, stored, 'cookies'):
                return self.hold('Kazuma cake exchange is not available; cookies retained. Check NPC dialog.')
        return True

    def telemetry(self):
        return dict(ToTActive=int(self.active), ToTStage=self.state.get('stage', ''), ToTHold=self.state.get('hold', ''))
