"""Team funding rotation and opt-in seasonal turn-ins; all currency is integer gold."""
from __future__ import annotations
import json
from pathlib import Path
import time
from core import atomic_text, read_status
from game_bridge import fields

TOA, LA, EMBARK = 138, 55, 857
LA_MAPS = {55, 808}
TARGET_CARRIED, EMPTY_CARRIED = 20_000, 5_000
TURNIN_DIALOGS = (0x846303, 0x846301, 0x846307)


def skeleton_gold(captured):
    return max(0, int(captured)) // 3 * 1000


def total_value(inv):
    return int(inv.get('gold', 0)) + int(inv.get('storage_gold', 0)) + skeleton_gold(inv.get('captured', 0))


def withdrawal_to_target(inv, target=TARGET_CARRIED):
    return max(0, min(target - int(inv.get('gold', 0)), int(inv.get('storage_gold', 0)), 100_000 - int(inv.get('gold', 0))))


def empty_on_plat(inv):
    return int(inv.get('gold', 0)) < EMPTY_CARRIED and int(inv.get('storage_gold', 0)) == 0


def purchase_decision(inv, quote):
    """Buy individually using a fresh quote, retaining >=800p when attainable."""
    quote = int(quote)
    if quote <= 0 or quote > 100_000:
        return 'quote'
    if total_value(inv) <= 900_000:
        return 'band'
    if skeleton_gold(inv.get('captured', 0)) <= 900_000 and total_value(inv) - quote < 800_000:
        return 'band'
    if int(inv.get('gold', 0)) + int(inv.get('storage_gold', 0)) < quote:
        return 'turnin'
    return 'buy' if int(inv.get('gold', 0)) >= quote else 'withdraw'


class Economy:
    def __init__(self, worker):
        self.w = worker
        self.enabled = worker.team.getboolean('FundingRotation', fallback=True)
        self.turnin_enabled = worker.team.getboolean('TurnInEnabled', fallback=False)
        self.path = worker.session / 'economy.json'
        self.local_path = worker.session / (worker.id + '.economy.json')
        self.inv = {}
        self.last_poll = -1000
        self.shared = self.read_shared()
        self.applied_epoch = -1
        self.pending_withdraw = None
        self.hold = None
        self.progress = self.read_json(self.local_path, {})
        self.currency_path = worker.session / (worker.id + '.currency.json')
        self.currency = self.read_json(self.currency_path, {})
        self.stage_since = worker.clock()
        self.action_at = -1000

    @property
    def currency_pending(self):
        return bool(self.currency.get('active'))

    def request_currency(self, token):
        if token == self.currency.get('seen'):
            return
        if self.currency_pending:
            self.currency['seen'] = token  # coalesce repeated clicks, never reset an in-flight buy
        else:
            self.currency = dict(seen=token, generation=token, stage='leave', district=1, active=True)
        atomic_text(self.currency_path, json.dumps(self.currency))

    def handle_currency(self):
        seasonal_progress, seasonal_path = self.progress, self.local_path
        self.progress, self.local_path = self.currency, self.currency_path
        try:
            return self.turnin(manual=True)
        finally:
            self.currency = self.progress
            self.progress, self.local_path = seasonal_progress, seasonal_path

    @staticmethod
    def read_json(path, fallback):
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except FileNotFoundError:
            return fallback

    def read_shared(self):
        return self.read_json(self.path, dict(mode='farm', leader=self.w.leader_id, empty=[], epoch=0, generation=0))

    def save_shared(self, **changes):
        self.shared.update(changes)
        atomic_text(self.path, json.dumps(self.shared, indent=2))
        self.w.log('Economy: ' + json.dumps(self.shared))

    def stage(self, name, **values):
        if name == 'bank' and self.progress.get('stage') != 'bank':
            values.setdefault('storage_opened', False)
        self.progress.update(stage=name, **values)
        atomic_text(self.local_path, json.dumps(self.progress, indent=2))
        self.stage_since = self.w.clock()
        self.action_at = -1000

    def due(self, seconds=2):
        if self.w.clock() - self.action_at < seconds:
            return False
        self.action_at = self.w.clock()
        return True

    def block(self, message):
        self.hold = message
        self.w.change('EconomyHold', message)

    def telemetry(self):
        return dict(Gold=self.inv.get('gold', 0), StorageGold=self.inv.get('storage_gold', 0),
                    SkeletonsAvailable=self.inv.get('captured', 0), TotalValue=total_value(self.inv),
                    EmptyPlat=int(bool(self.inv) and empty_on_plat(self.inv)),
                    FundsKnown=int(bool(self.inv)),
                    FundingState='Empty on Plat' if self.inv and empty_on_plat(self.inv) else 'Funded',
                    EconomyMode=self.shared.get('mode', 'farm'), EconomyLeader=self.shared.get('leader', ''),
                    EconomyStage=self.progress.get('stage', ''),
                    EconomyDone=self.progress.get('done_generation', -1),
                    CurrencyActive=int(self.currency_pending), CurrencyStage=self.currency.get('stage', ''),
                    CurrencyRequestSeen=self.currency.get('seen', ''))

    def refresh_inventory(self, force=False):
        if force or self.w.clock() - self.last_poll >= 1:
            self.inv = self.w.game.inventory()
            self.last_poll = self.w.clock()

    def tick(self):
        w = self.w
        if (not self.enabled or w.assemble_only) and not self.currency_pending:
            return False
        if w.s.get('instance') != 0:
            return False
        self.refresh_inventory()
        self.shared = self.read_shared()
        w.leader_id = self.shared['leader']
        w.is_leader = w.id == w.leader_id
        mode = self.shared['mode']
        if self.currency_pending and w.build_verified and (mode != 'turnin' or not self.turnin_enabled):
            if self.currency.get('stage') == 'leave':
                self.hold = None
                self.stage_since = w.clock()
                self.action_at = -1000
            if self.hold:
                w.state = self.hold
                return True
            return self.handle_currency()
        if not self.enabled or w.assemble_only:
            return False
        if self.hold:
            w.state = self.hold
            return True
        if mode == 'hold':
            w.state = self.shared.get('reason', 'Economy needs attention')
            if w.phase != 'EconomyHold':
                w.change('EconomyHold', w.state)
            return True
        if mode == 'farm' and w.phase in ('TurnIn', 'AwaitTurnIn'):
            w.change('Prepare', 'Turn-ins complete; resuming farm assembly')
            return True
        if mode == 'turnin':
            if not self.turnin_enabled:
                if w.phase != 'AwaitTurnIn':
                    w.change('AwaitTurnIn', 'All accounts Empty on Plat — Turn In Mobs is disabled pending NPC testing')
                return True
            return self.turnin()
        if mode == 'rotate':
            epoch = self.shared['epoch']
            if self.applied_epoch != epoch:
                w.game.call('leave')
                self.applied_epoch = epoch
                w.change('Party', 'Rotating payer; assembling under funded leader')
                return True
            if w.id == w.leader_id and w.exact_party() and w.current_entry_leader() == w.id:
                self.save_shared(mode='farm')
            return False
        if w.s.get('map') != TOA or w.phase not in ('Party', 'Ready', 'Move', 'Entry'):
            return False
        if w.current_entry_leader() != w.id:
            return False
        # Do not fund/rotate during a partial map transition or split party.
        if not w.exact_party():
            return False
        if self.pending_withdraw:
            before, started = self.pending_withdraw
            if self.inv.get('gold', 0) > before:
                self.pending_withdraw = None
            elif w.clock() - started > 10:
                self.block('Xunlai withdrawal did not confirm; check storage access and gold')
                return True
            else:
                w.state = 'Confirming Xunlai withdrawal toward 20 platinum'
                return True
        amount = withdrawal_to_target(self.inv)
        if amount:
            w.game.call('storage')
            w.game.call('gold', amount)
            self.pending_withdraw = (self.inv.get('gold', 0), w.clock())
            w.state = f'Withdrawing {amount / 1000:g} platinum toward 20 carried'
            return True
        if not empty_on_plat(self.inv):
            return False
        empty = list(dict.fromkeys(self.shared.get('empty', []) + [w.id]))
        candidates = []
        for member in w.members:
            if member['id'] in empty:
                continue
            peer = w.peer(member['id'])
            if not peer or not int(peer.get('fundsknown', 0)):
                w.state = 'Empty on Plat — waiting for follower funding balances'
                return True
            if int(peer['emptyplat']):
                empty.append(member['id'])
            else:
                candidates.append(member['id'])
        if candidates:
            self.save_shared(mode='rotate', leader=candidates[0], empty=empty, epoch=self.shared['epoch'] + 1)
            w.change('Party', 'Empty on Plat — handing leader role to a funded follower')
        else:
            self.save_shared(mode='turnin', empty=empty, generation=self.shared['generation'] + 1)
            w.change('AwaitTurnIn', 'All accounts Empty on Plat — preparing independent turn-ins')
        return True

    def travel(self, map_id, allowed=None, district=None):
        allowed = allowed or {map_id}
        district = district or int(self.progress.get('district', 1))
        if self.w.s.get('map') in allowed and self.w.s.get('instance') == 0 and self.w.s.get('district') == district and self.w.s.get('region') == self.w.destination['region'] and self.w.s.get('language') == self.w.destination['language']:
            return True
        if self.due(5):
            self.w.game.call('travel', map_id, self.w.destination['region'], district, self.w.destination['language'])
        if self.w.clock() - self.stage_since > 90:
            self.block('Economy travel timed out; verify outpost access and district')
        return False

    def turnin(self, manual=False):
        w = self.w
        generation = self.progress.get('generation') if manual else self.shared['generation']
        if self.progress.get('generation') != generation:
            self.progress = dict(generation=generation, district=1)
            self.stage('leave')
        phase = 'Currency' if manual else 'TurnIn'
        if w.phase != phase and not self.hold:
            w.change(phase, 'Handle Currency — independent Embark test' if manual else 'Turn In Mobs — independent account workflow')
        stage = self.progress['stage']
        w.state = ('Handle Currency — ' if manual else 'Turn In Mobs — ') + stage
        if stage == 'leave':
            w.game.call('leave')
            self.stage('separate')
        elif stage == 'separate':
            roster = [p for p in str(w.s.get('roster', '')).split(',') if p]
            if len(roster) <= 1 and not w.s.get('heroes') and not w.s.get('henchmen'):
                self.stage('embark' if manual else 'assess')
            elif self.due():
                w.game.call('leave')
            if w.clock() - self.stage_since > 20:
                self.block('Could not leave party for independent turn-in travel')
        elif stage == 'assess':
            if self.inv.get('tot', 0):
                self.stage('bank')
            elif self.inv.get('storage_gold', 0) > 800_000 and total_value(self.inv) > 900_000:
                self.stage('embark')
            elif self.inv.get('captured', 0) <= 2:
                self.stage('home')
            elif self.inv.get('gold', 0) >= 99_000:
                self.stage('deposit')
            elif not self.inv.get('free', 0):
                self.block('Turn-in needs inventory space for reward bags')
            else:
                self.stage('la')
        elif stage == 'la':
            if self.travel(LA, LA_MAPS):
                self.stage('npc')
        elif stage == 'npc':
            npc = int(w.game.call('npc_near', 5267, 9070, 400))
            if npc and w.game.agent(npc).get('distance', 99999) <= 200:
                w.game.call('npc', npc)
                self.stage('dialog', dialog_index=0, before_captured=self.inv.get('captured', 0), before_tot=self.inv.get('tot', 0))
            elif self.due():
                w.game.call('move', 5267, 9070)
            if w.clock() - self.stage_since > 60:
                self.block('Seasonal quest NPC not found near reference location; turn-ins await live NPC testing')
        elif stage == 'dialog':
            if self.due(.5):
                index = self.progress['dialog_index']
                w.game.call('dialog', TURNIN_DIALOGS[index])
                if index == len(TURNIN_DIALOGS) - 1:
                    self.stage('reward')
                else:
                    self.stage('dialog', dialog_index=index + 1)
        elif stage == 'reward':
            consumed = self.progress['before_captured'] - self.inv.get('captured', 0)
            if consumed >= 3 and self.inv.get('tot', 0) > self.progress['before_tot']:
                self.stage('bank')
            elif w.clock() - self.stage_since > 15:
                self.block('Quest reward did not confirm skeleton consumption and ToT bags; no blind repeat')
        elif stage == 'bank':
            if self.inv.get('tot', 0) == 0:
                self.stage('deposit')
            elif not self.progress.get('storage_opened'):
                w.game.call('storage')
                self.stage('bank', storage_opened=True)
            elif self.due():
                if w.game.call('bank', 28434) == '0':
                    self.block('Xunlai has no room for Trick-or-Treat bags')
            if w.clock() - self.stage_since > 60:
                self.block('Banking ToT bags timed out')
        elif stage == 'deposit':
            amount = min(self.inv.get('gold', 0), max(0, 1_000_000 - self.inv.get('storage_gold', 0)))
            if amount and self.due():
                w.game.call('storage')
                w.game.call('deposit', amount)
                self.stage('deposit_wait', before_gold=self.inv['gold'])
            else:
                self.stage('district')
        elif stage == 'deposit_wait':
            if self.inv.get('gold', 0) < self.progress['before_gold']:
                self.stage('district')
            elif w.clock() - self.stage_since > 10:
                self.block('Gold deposit did not confirm')
        elif stage == 'district':
            self.stage('assess', district=2 if self.progress.get('district', 1) == 1 else 1)
        elif stage == 'embark':
            if self.travel(EMBARK):
                self.stage('trader')
        elif stage == 'trader':
            npc = int(w.game.call('npc_name', 'Duuja'))
            if npc:
                if w.game.agent(npc).get('distance', 99999) <= 200:
                    w.game.call('npc', npc)
                    self.stage('quote')
                elif self.due():
                    w.game.call('npc', npc)
            if w.clock() - self.stage_since > 90:
                self.block('Duuja could not be reached at Embark Beach; trader path needs live validation')
        elif stage == 'quote':
            quote = int(w.game.call('ecto_quote'))
            decision = purchase_decision(self.inv, quote)
            if decision == 'quote':
                self.block('No valid ectoplasm quote or price exceeds inventory gold limit')
            elif decision in ('band', 'turnin'):
                outcome = ('Below buying threshold; no purchase needed' if total_value(self.inv) < 800_000
                           else 'Currency value is in the target band' if decision == 'band'
                           else 'Cannot afford another quote; skeletons retained')
                w.log(f'Currency handling: {outcome}; quote={quote}, total value={total_value(self.inv)} gold')
                self.stage('home' if manual or self.inv.get('captured', 0) <= 2 else 'la', outcome=outcome)
            elif decision == 'withdraw':
                amount = withdrawal_to_target(self.inv, 100_000)
                w.game.call('storage')
                w.game.call('gold', amount)
                self.stage('buy_withdraw', before_gold=self.inv.get('gold', 0))
            elif self.inv.get('free', 0) == 0 and self.inv.get('ecto_stack_room', 0) == 0:
                self.block('No room for ectoplasm; inventory remains unchanged')
            elif w.game.call('ecto_buy', quote) == '1':
                self.stage('buy_wait', before_ecto=self.inv.get('ecto', 0), before_gold=self.inv.get('gold', 0))
            else:
                self.block('Ectoplasm quote changed; purchase was not confirmed')
        elif stage == 'buy_withdraw':
            if self.inv.get('gold', 0) > self.progress['before_gold']:
                self.stage('trader')
            elif w.clock() - self.stage_since > 10:
                self.block('Ectoplasm funding withdrawal did not confirm')
        elif stage == 'buy_wait':
            if self.inv.get('ecto', 0) > self.progress['before_ecto'] and self.inv.get('gold', 0) < self.progress['before_gold']:
                self.stage('quote')
            elif w.clock() - self.stage_since > 10:
                self.block('Ectoplasm transaction did not confirm; no repeat purchase')
        elif stage == 'home':
            if self.travel(TOA, district=w.destination['district']):
                self.stage('done', done_generation=generation)
        elif stage == 'done' and manual:
            self.progress['active'] = False
            atomic_text(self.local_path, json.dumps(self.progress))
            w.change('Paused' if w.mode == 'pause' else 'Prepare', 'Handle Currency complete; back in ToA — ' + self.progress.get('outcome', 'purchases confirmed'))
        elif stage == 'done':
            w.state = 'Turn-ins complete; waiting in ToA for team'
            if w.id == self.shared['leader']:
                peers = [w.peer(m['id']) for m in w.members if m['id'] != w.id]
                if all(p and int(p.get('economydone', -1)) == generation and int(p.get('map', 0)) == TOA
                       and all(int(p.get(k, -999)) == v for k, v in w.destination.items()) for p in peers):
                    candidates = []
                    if self.inv.get('gold', 0) + self.inv.get('storage_gold', 0) >= EMPTY_CARRIED:
                        candidates.append(w.id)
                    for member in w.members:
                        if member['id'] == w.id:
                            continue
                        peer = w.peer(member['id'])
                        if peer and int(peer.get('gold', 0)) + int(peer.get('storagegold', 0)) >= EMPTY_CARRIED:
                            candidates.append(member['id'])
                    if candidates:
                        self.save_shared(mode='farm', leader=candidates[0], empty=[], epoch=self.shared['epoch'] + 1)
                    else:
                        self.save_shared(mode='hold', reason='Turn-ins complete, but no account has 5 platinum to resume leading')
                        self.block(self.shared['reason'])
        if not manual and self.shared['mode'] == 'farm':
            w.change('Prepare', 'Turn-ins complete; resuming farm assembly')
        return True
