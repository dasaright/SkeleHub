"""Python SkeleBot state machine. GwAu3 is used only through game_bridge.py."""
from __future__ import annotations
import argparse
import configparser
import ctypes
from datetime import datetime
import math
import os
from pathlib import Path
import sys
import time
import traceback
from core import write_ini, read_status, write_control
from game_bridge import GameBridge, fields

TOA, UW = 138, 72
from farm_build import BUILD, SKILLS, SEQUENCE
from version import VERSION


def process_alive(pid):
    if not pid:
        return False
    if os.name != 'nt':
        try:
            os.kill(int(pid), 0)
            return True
        except OSError:
            return False
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.OpenProcess(0x1000, False, int(pid))
    if not handle:
        return False
    code = ctypes.c_ulong()
    result = kernel.GetExitCodeProcess(handle, ctypes.byref(code))
    kernel.CloseHandle(handle)
    return bool(result and code.value == 259)


def read_ini(path):
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(path, encoding='utf-16')
    return parser


class Worker:
    def __init__(self, session, account_id, game, clock=time.monotonic, hub_pid=None):
        self.hub_pid = hub_pid
        self.session = Path(session)
        self.id = account_id
        self.game, self.clock = game, clock
        self.config = read_ini(self.session / 'team.ini')
        self.team = self.config['Team']
        self.members = [dict(self.config[f'Member{i}']) for i in range(1, int(self.team['Count']) + 1)]
        self.member = next(a for a in self.members if a['id'] == account_id)
        self.character = self.member['character']
        self.leader_id = self.team['Leader']
        self.is_leader = self.id == self.leader_id
        self.test_mode = self.team.getboolean('TestMode', fallback=True)
        self.assemble_only = self.team.getboolean('AssembleOnly', fallback=False)
        self.destination = {key.lower(): int(self.team[key]) for key in ('Region', 'Language', 'District')}
        self.command_path = self.session / (self.id + '.command.ini')
        self.status_path = self.session / (self.id + '.status.ini')
        self.log_path = self.session / (self.id + '.log')
        self.started = self.phase_started = self.clock()
        self.phase, self.state = 'Attach', 'Starting Python SkeleBot'
        self.mode = 'run'
        self.s = {}
        self.runs = self.fails = self.captures = self.kills = self.cycle = 0
        self.last_action = -1000
        self.build_loaded = False
        self.build_time = 0
        self.build_attempts = 0
        self.prepare_ready_at = 0
        self.combat_started_at = None
        self.entry_leader_id = self.leader_id
        self.charge_confirmed = False
        self.charge_requested_at = None
        self.charge_attempts = 0
        self.target = 0
        self.step = 0
        self.cast_until = 0
        self.before = 0
        self.kneel_sent = False
        self.return_sent = False
        self.render_disabled = bool(int(self.member.get('disablerendering', '0')))
        self.unavailable_since = None
        self.waypoint = None
        self.kill_verified = False
        self.combat_started = False
        self.peer_error_since = None

    def log(self, text):
        if self.log_path.exists() and self.log_path.stat().st_size > 5 * 1024 * 1024:
            self.log_path.replace(self.log_path.with_suffix('.log.1'))
        with self.log_path.open('a', encoding='utf-8') as output:
            output.write(f'{datetime.now():%Y/%m/%d %H:%M:%S} | {self.phase} | {text}\n')

    def change(self, phase, message):
        if phase == 'Prepare' and self.phase != 'Prepare':
            self.build_attempts = 0
            self.build_loaded = False
            self.build_time = 0
            self.prepare_ready_at = self.clock() + 2.5
        self.phase, self.state = phase, message
        self.phase_started = self.clock()
        self.last_action = -1000
        self.log(message)
        self.publish()

    def error(self, message):
        self.change('Error', 'Attention: ' + message)

    def elapsed(self):
        return self.clock() - self.phase_started

    def due(self, seconds):
        if self.clock() - self.last_action < seconds:
            return False
        self.last_action = self.clock()
        return True

    def publish(self):
        fields = {'Stamp': f'{datetime.now():%Y/%m/%d %H:%M:%S}', 'PID': os.getpid(),
                  'LaunchPID': os.getppid() if getattr(sys, 'frozen', False) else os.getpid(),
                  'WorkerVersion': VERSION, 'BuildTemplate': BUILD, 'BuildSkills': ','.join(map(str, SKILLS)),
                  'BuildAttempts': self.build_attempts, 'EntryLeader': self.entry_leader_id,
                  'ChargeConfirmed': int(self.charge_confirmed), 'ChargeAttempts': self.charge_attempts,
                  'Character': self.character, 'Phase': self.phase, 'State': self.state, 'Mode': self.mode,
                  'Cycle': self.cycle, 'TestMode': int(self.test_mode), 'Kills': self.kills,
                  'KillVerified': int(self.kill_verified), 'Target': self.target,
                  'Runs': self.runs, 'Fails': self.fails, 'Captured': self.captures,
                  'RenderingDisabled': int(self.render_disabled),
                  'Rate': round(self.captures * 3600 / max(1, self.clock() - self.started), 1)}
        for source, destination in [('map', 'Map'), ('region', 'Region'), ('language', 'Language'),
                                    ('district', 'District'), ('party', 'Party'), ('login', 'Login'),
                                    ('game_pid', 'GamePID')]:
            fields[destination] = self.s.get(source, 0)
        write_ini(self.status_path, {'Worker': fields})

    def peer(self, account_id):
        status = read_status(self.session / (account_id + '.status.ini'))
        if not status or not process_alive(status.get('pid')) or status.get('phase') in ('Error', 'Stopped', 'Paused'):
            return None
        return status

    def peers(self):
        return [(member['id'], self.peer(member['id'])) for member in self.members if member['id'] != self.id]

    def location_matches(self):
        return self.s.get('map') == TOA and self.s.get('instance') == 0 and all(self.s.get(k) == v for k, v in self.destination.items())

    def exact_party(self):
        roster = self.s.get('roster', '')
        present = {int(part.split(':')[0]) for part in str(roster).split(',') if part and part.endswith(':1')}
        if len(present) != len(self.members) or self.s.get('heroes') or self.s.get('henchmen'):
            return False
        expected = {int(self.s.get('login', 0))}
        for account_id, peer in self.peers():
            if not peer or peer.get('mode') != 'run' or int(peer.get('map', 0)) != TOA:
                return False
            if any(int(peer.get(k, -999)) != v for k, v in self.destination.items()):
                return False
            login = int(peer.get('login', 0))
            expected.add(login)
        return 0 not in expected and expected == present

    def current_entry_leader(self):
        if self.s.get('leader') == self.s.get('login'):
            return self.id
        for account_id, peer in self.peers():
            if peer and int(peer.get('login', 0)) == self.s.get('leader'):
                return account_id
        return None

    def all_ready(self):
        return self.exact_party() and all(peer and peer.get('phase') == 'Ready' for _, peer in self.peers())

    def hub_alive(self):
        return self.hub_pid is None or process_alive(self.hub_pid)

    def login_wait(self, seconds=.5):
        """Keep controls and status live while the client logs in or changes maps."""
        self.mode = read_ini(self.command_path).get('Control', 'Mode', fallback='pause')
        self.publish()
        if self.mode == 'stop' or not self.hub_alive():
            return False
        time.sleep(seconds)
        return True

    def select_character(self):
        deadline = self.clock() + 180
        sorted_names = False
        attempts, initial_index = 0, None
        entering = False
        left_at = None
        while self.clock() < deadline:
            login = fields(self.game.call('login'))
            if not login.get('alive'):
                self.error('Guild Wars client exited during character selection')
                return True
            if login.get('ingame'):
                self.s = self.game.snapshot()
                if self.s.get('instance') == 2 or not self.s.get('login') or not self.s.get('primary'):
                    self.state = 'Waiting for character and map data'
                elif str(self.s.get('character', '')).strip().casefold() != self.character.strip().casefold():
                    self.error('Loaded character does not match the selected account; select the configured character and relaunch')
                    return True
                elif self.s.get('instance') != 0:
                    self.error('Start the character in an outpost')
                    return True
                else:
                    if left_at is None:
                        self.game.call('render', 1)
                        self.render_disabled = True
                        write_control(self.command_path, rendering=True)
                        self.game.call('leave')
                        left_at = self.clock()
                    roster = [p for p in str(self.s.get('roster', '')).split(',') if p]
                    if len(roster) > 1 or self.s.get('heroes') or self.s.get('henchmen'):
                        if self.clock() - left_at > 15:
                            self.error('Could not leave the previous party after login')
                            return True
                        self.state = 'Leaving previous party before team assembly'
                        if not self.login_wait():
                            return False
                        continue
                    self.change('Travel', 'Character verified; previous party left; rendering disabled')
                    return True
            elif login.get('selection') and login.get('index', -1) >= 0:
                self.state = 'Selecting configured character'
                if not sorted_names:
                    # Match Encounter ReBuilt: normalize order before searching right.
                    self.game.call('key', 'N')
                    sorted_names = True
                elif str(login.get('selected', '')).strip().casefold() == self.character.strip().casefold():
                    self.state = 'Entering game with configured character'
                    self.game.call('key', 'ENTER')
                    entering = True
                elif entering:
                    self.error('Character selection changed while entering the game')
                    return True
                elif attempts >= 20 or (attempts > 1 and login['index'] == initial_index):
                    self.error('Configured character was not found on this account')
                    return True
                else:
                    if initial_index is None:
                        initial_index = login['index']
                    self.game.call('key', 'RIGHT')
                    attempts += 1
            else:
                self.state = 'Waiting for account login / character screen'
            if not self.login_wait():
                return False
        self.error('Character selection or map loading timed out')
        return True

    def attach(self):
        deadline = self.clock() + 180
        launched_pid = None
        while self.clock() < deadline:
            self.mode = read_ini(self.command_path).get('Control', 'Mode', fallback='pause')
            if self.mode == 'stop' or not self.hub_alive():
                return False
            self.publish()
            command, target = ('attach_pid', launched_pid) if launched_pid else ('attach', self.character)
            if self.game.call(command, target) == '1':
                return self.select_character()
            if launched_pid is None and self.member.get('launchdirect') == '1':
                self.state = 'Launching account from local characters.ini'
                self.publish()
                launched_pid = int(self.game.call('launch', self.member.get('charactersini', ''),
                                        self.member.get('section', self.character), self.member.get('exepath', ''),
                                        self.member.get('cryptoseed', 'Encounter_ReBuilt.au3')))
                if launched_pid <= 0:
                    self.error('Account launch failed; check encryption seed and local game paths')
                    return True
                self.s['game_pid'] = launched_pid
                self.publish()
                deadline = self.clock() + 180
            if not self.login_wait(3):
                return False
        self.error('Character login/attachment timed out')
        return True

    def tick(self):
        control = read_ini(self.command_path)
        self.mode = control.get('Control', 'Mode', fallback='pause')
        if self.mode == 'stop' or not self.hub_alive():
            return False
        if self.phase == 'Error':
            return True
        self.s = self.game.snapshot()
        if not self.s.get('alive', 1):
            self.error('Guild Wars client exited')
            return True
        desired = control.getboolean('Control', 'DisableRendering', fallback=self.render_disabled)
        if bool(self.s.get('rendering', 0)) != desired:
            self.game.call('render', int(desired))
        self.render_disabled = desired
        if not self.s.get('ingame', 1) or self.s.get('instance') == 2:
            if self.unavailable_since is None:
                self.unavailable_since = self.clock()
            if self.clock() - self.unavailable_since > 60:
                self.error('Disconnected or map load timed out')
            return True
        self.unavailable_since = None
        if str(self.s.get('character', '')).strip().casefold() != self.character.strip().casefold():
            self.error('Active character changed; relaunch the selected account')
            return True
        # A party map transition may skip the Ready/Party tick or briefly expose stale
        # district/type data. The fully loaded map takes precedence over town states.
        if self.s.get('map') == UW and self.s.get('instance') == 1 and self.phase in ('Travel', 'Prepare', 'Party', 'Ready', 'Move', 'Entry'):
            self.start_fight()
            return True
        if self.mode == 'pause' and self.s.get('instance') == 0:
            if self.phase != 'Paused':
                self.change('Paused', 'Paused in outpost')
            return True
        if self.phase == 'Paused':
            self.change('Travel', 'Resuming team')
        {'Travel': self.travel, 'Prepare': self.prepare, 'Party': self.party, 'Ready': self.party,
         'Move': self.move, 'Entry': self.entry, 'Fight': self.fight, 'Done': self.done,
         'Return': self.return_to_town}.get(self.phase, lambda: None)()
        return True

    def travel(self):
        if self.location_matches():
            self.change('Prepare', 'Checking build' if self.test_mode else 'Checking build and supplies')
        elif self.elapsed() > 60:
            self.error('Travel to the configured town/district timed out')
        elif self.due(5):
            self.game.call('travel', TOA, self.destination['region'], self.destination['district'], self.destination['language'])

    def prepare(self):
        if not self.location_matches():
            self.change('Travel', 'Regrouping in configured district')
            return
        if self.clock() < self.prepare_ready_at:
            self.state = 'Waiting for town profession and skill data to settle'
            return
        if not self.test_mode:
            inv = self.game.inventory()
            if not inv.get('mobstoppers') or not inv.get('free'):
                self.error('Farm mode requires an Everlasting Mobstopper and a free bag slot')
                return
        primary = int(self.s.get('primary', 0))
        if not primary:
            self.state = 'Waiting for profession data'
            if self.elapsed() > 60:
                self.error('Character profession data did not load')
            return
        if primary != 7:
            self.error('The Skelefarm template requires an Assassin primary profession')
            return
        verified = (int(self.s.get('secondary', 0)) == 3
                    and int(self.s.get('smiting', 0)) == 12 and int(self.s.get('shadow', 0)) == 12
                    and [int(x) for x in str(self.s.get('skills', '')).split(',') if x] == SKILLS)
        if not self.build_loaded or not verified:
            if self.build_attempts and self.clock() - self.build_time < 15:
                self.state = 'Waiting for template professions, attributes and skills'
                return
            if self.build_attempts >= 3:
                self.error('Farm template verification failed; check Monk secondary, attribute points and unlocked skills')
                return
            self.build_attempts += 1
            self.log(f'Template {BUILD}, attempt {self.build_attempts}/3; observed primary={primary}, secondary={self.s.get("secondary")}, smiting={self.s.get("smiting")}, shadow={self.s.get("shadow")}, skills={self.s.get("skills")}')
            self.state = 'Loading current Assassin/Monk farm template'
            self.publish()
            loaded = self.game.call('build', BUILD) == '1'
            self.build_loaded, self.build_time = loaded, self.clock()
            if not loaded:
                self.state = 'Template load pending; checking secondary profession and unlocks'
            return
        if self.clock() - self.build_time < 2.5:
            return
        cooldowns = self.cooldowns()
        if any(cooldowns[i] > 0 for i in (2, 4, 5, 6)):
            self.state = 'Waiting for damage skills to recharge'
            if self.elapsed() > 90:
                self.error('Skills did not recharge')
            return
        self.game.call('kickheroes')
        self.game.call('normal')
        self.change('Party', 'Assembling configured team')

    def party(self):
        if self.s.get('map') == UW and self.s.get('instance') == 1:
            self.start_fight()
            return
        if not self.location_matches():
            self.change('Travel', 'Regrouping in configured district')
            return
        if self.exact_party():
            if self.phase != 'Ready':
                self.change('Ready', 'Team ready')
            self.entry_leader_id = self.current_entry_leader() or self.entry_leader_id
            if self.entry_leader_id == self.id and self.all_ready():
                if self.assemble_only:
                    self.state = 'Assembly verified — assembly-only mode'
                    return
                inv = self.game.inventory()
                if inv.get('gold', 0) < 1000:
                    if inv.get('storage_gold', 0) < 1000 or self.elapsed() > 30:
                        self.error('Leader needs 1,000 carried gold for UW entry')
                    elif self.due(3):
                        self.game.call('gold')
                    return
                pos = (self.s.get('x', 0), self.s.get('y', 0))
                self.waypoint = (-4279, 18221) if math.dist(pos, (-3670, 17575)) < math.dist(pos, (-5150, 17500)) else (-4667, 17917)
                self.change('Move', 'Leader moving to Grenth statue')
            return
        if self.phase == 'Ready':
            self.change('Party', 'Party changed; regrouping')
        if self.elapsed() > 300:
            self.error('Team assembly timed out')
            return
        if not self.due(3):
            return
        if self.s.get('leader') == self.s.get('login'):
            for _, peer in self.peers():
                if peer and int(peer.get('map', 0)) == TOA and all(int(peer.get(k, -999)) == v for k, v in self.destination.items()):
                    login = int(peer.get('login', 0))
                    if login and f'{login}:1' not in str(self.s.get('roster', '')).split(','):
                        self.game.call('invite', login)
        else:
            leader = self.peer(self.leader_id) if not self.is_leader else None
            if leader and int(leader.get('map', 0)) == TOA and all(int(leader.get(k, -999)) == v for k, v in self.destination.items()):
                party = int(leader.get('party', 0))
                if party and self.s.get('party') != party:
                    if ',' in str(self.s.get('roster', '')):
                        self.game.call('leave')
                    else:
                        self.game.call('accept', party)

    def move(self):
        if self.current_entry_leader() != self.id:
            self.change('Party', 'Party leader changed; preserving team and handing off entry')
            return
        if not self.all_ready():
            self.change('Party', 'A team member is no longer ready')
            return
        if self.elapsed() > 45:
            self.error('Movement to Grenth timed out')
            return
        if math.dist((self.s.get('x', 0), self.s.get('y', 0)), self.waypoint) < 200:
            if self.waypoint != (-4100, 19829):
                self.waypoint = (-4100, 19829)
            else:
                self.cycle += 1
                self.kneel_sent = False
                self.change('Entry', 'Leader kneeling and entering UW')
        elif self.due(1):
            self.game.call('move', *self.waypoint)

    def entry(self):
        if self.s.get('map') == UW and self.s.get('instance') == 1:
            self.start_fight()
            return
        if self.current_entry_leader() != self.id:
            self.change('Party', 'Party leader changed; preserving team and handing off entry')
            return
        if self.elapsed() > 45:
            self.error('UW entry timed out; check Grenth/access and carried gold')
            return
        if not self.all_ready():
            self.change('Party', 'Entry cancelled; readiness changed')
            return
        if not self.due(2):
            return
        if not self.kneel_sent:
            self.game.call('kneel')
            self.kneel_sent = True
            return
        npc = int(self.game.call('nearest', 1995, 0))
        if not npc:
            self.game.call('kneel')
            return
        self.game.call('npc', npc)
        time.sleep(.35)
        self.game.call('dialog', 0x85)
        time.sleep(.35)
        self.game.call('dialog', 0x86)

    def start_fight(self):
        actual_leader = self.current_entry_leader()
        if actual_leader:
            self.entry_leader_id = actual_leader
        if self.id != self.entry_leader_id:
            leader = self.peer(self.entry_leader_id)
            if leader:
                self.cycle = int(leader.get('cycle', 0))
        self.target, self.step, self.cast_until = 0, 0, 0
        self.kill_verified = False
        self.charge_confirmed = False
        self.charge_requested_at = None
        self.charge_attempts = 0
        self.combat_started = False
        self.combat_started_at = None
        self.peer_error_since = None
        self.before = self.game.inventory().get('captured', 0) if not self.test_mode else 0
        self.change('Fight', 'Test: waiting for team to load UW' if self.test_mode else 'Finding Skeleton of Dhuum')

    def all_loaded(self):
        if self.id != self.entry_leader_id:
            leader = read_status(self.session / (self.entry_leader_id + '.status.ini'))
            if leader and int(leader.get('map', 0)) == UW and leader.get('phase') in ('Entry', 'Fight', 'Done', 'Return'):
                self.cycle = int(leader.get('cycle', self.cycle))
        waiting = []
        peer_failed = False
        for member in self.members:
            if member['id'] == self.id:
                continue
            peer = read_status(self.session / (member['id'] + '.status.ini'))
            name = member['character']
            if not peer or not process_alive(peer.get('pid')):
                waiting.append(name + ': worker unavailable')
                peer_failed = True
            elif peer.get('phase') in ('Error', 'Stopped'):
                waiting.append(name + ': needs attention')
                peer_failed = True
            elif int(peer.get('map', 0)) != UW:
                waiting.append(name + ': loading UW')
            elif peer.get('phase') not in ('Fight', 'Done', 'Return'):
                waiting.append(name + ': ' + peer.get('phase', 'starting'))
            elif int(peer.get('cycle', -1)) != self.cycle:
                waiting.append(name + ': synchronizing run')
        if waiting:
            self.state = 'Waiting for team — ' + '; '.join(waiting)
            if peer_failed:
                if self.peer_error_since is None:
                    self.peer_error_since = self.clock()
                elif self.clock() - self.peer_error_since >= 10:
                    self.finish(False, 'Team worker unavailable; returning to town')
            else:
                self.peer_error_since = None
            return False
        self.peer_error_since = None
        self.state = 'Team loaded in UW; engaging Skeleton of Dhuum'
        return True

    def finish(self, success, message):
        self.runs += 1
        self.fails += int(not success)
        if success:
            if self.test_mode:
                self.kills += 1
                self.kill_verified = True
            else:
                self.captures += max(0, self.game.inventory().get('captured', 0) - self.before)
        self.change('Done', message)

    def cooldowns(self):
        values = [int(x) for x in str(self.s.get('cooldowns', '0,0,0,0,0,0,0,0')).split(',')]
        return dict(zip(range(1, 9), values))

    def cast_next(self, agent):
        if self.clock() < self.cast_until or self.s.get('casting') or self.step >= len(SEQUENCE):
            return
        slot = SEQUENCE[self.step]
        if slot >= 3 and not self.charge_confirmed:
            self.step = SEQUENCE.index(2)
            return
        if slot == 2:
            cooldown = self.cooldowns().get(2, 0)
            if self.charge_requested_at is not None:
                if cooldown > 0 and agent.get('distance', 99999) <= 300:
                    self.charge_confirmed = True
                    self.step += 1
                    self.state = "Death's Charge confirmed; continuing combat"
                    self.log("Death's Charge confirmed by recharge and target proximity")
                    return
                wait = self.clock() - self.charge_requested_at
                self.state = "Waiting to confirm Death's Charge before Signet of Judgment"
                if wait < (5 if cooldown else 3):
                    return
                if cooldown:
                    self.finish(False, "Death's Charge did not reach skeleton; returning to town")
                    return
                self.charge_requested_at = None
            if cooldown > 0:
                self.state = "Waiting for Death's Charge to recharge; damage sequence blocked"
                return
            if self.charge_attempts >= 3:
                self.finish(False, "Death's Charge failed three attempts; returning to town")
                return
            self.charge_attempts += 1
            self.charge_requested_at = self.clock()
            self.game.call('target', self.target)
            delay = float(self.game.call('cast', 2, self.target))
            self.cast_until = self.clock() + max(.3, delay)
            return
        if (slot == 6 and agent.get('hp', 1) >= .49) or self.cooldowns().get(slot, 0) > 0:
            self.step += 1
            return
        target = self.target if slot in (4, 5, 6) else -2
        delay = float(self.game.call('cast', slot, target))
        self.cast_until = self.clock() + max(.3, delay)
        self.step += 1

    def fight(self):
        if self.s.get('map') != UW:
            self.finish(False, 'Unexpected map change during run')
            return
        combat_elapsed = self.clock() - self.combat_started_at if self.combat_started_at is not None else self.elapsed()
        if combat_elapsed > (60 if self.test_mode else 30):
            self.finish(False, 'Skeleton kill/team load timed out' if self.test_mode else 'Capture timed out')
            return
        if self.test_mode and not self.combat_started:
            if not self.all_loaded():
                return
            self.combat_started = True
            self.combat_started_at = self.clock()
        if not self.test_mode and self.game.inventory().get('captured', 0) > self.before:
            self.game.call('cancel')
            self.finish(True, 'Capture verified in inventory')
            return
        if not self.target:
            self.target = int(self.game.call('nearest', 2392, 2393))
            if not self.target:
                return
            self.publish()
            self.game.call('target', self.target)
            if self.test_mode:
                self.game.call('attack', self.target)
        agent = self.game.agent(self.target)
        if not agent.get('exists'):
            return  # Disappearance alone never counts as a confirmed kill.
        if agent.get('model') not in (2392, 2393):
            self.finish(False, 'Skeleton target identity changed')
            return
        if agent.get('dead'):
            if self.test_mode:
                self.game.call('cancel')
                self.finish(True, 'Skeleton dead; waiting 2 seconds before resigning')
            elif self.elapsed() > 20:
                self.finish(False, 'Skeleton died without verified capture')
            return
        if self.s.get('dead'):
            self.finish(False, 'Character died before skeleton' if self.test_mode else 'Character died before capture')
            return
        if not self.test_mode and agent.get('hp', 1) < .25:
            if self.due(1):
                if self.game.call('capture', self.target) != '1':
                    self.finish(False, 'Mobstopper missing')
            return
        self.state = 'Test: running to and killing Skeleton of Dhuum' if self.test_mode else 'Damaging Skeleton of Dhuum'
        self.cast_next(agent)
        if self.test_mode and self.step >= len(SEQUENCE) and not self.s.get('casting') and self.clock() >= self.cast_until:
            if self.due(1):
                self.game.call('attack', self.target)
            if self.cooldowns().get(4, 0) == 0:
                self.step = 3

    def done(self):
        if self.test_mode:
            if self.elapsed() >= 2:
                self.return_sent = False
                self.change('Return', 'Test: resigning; every account requests return to ToA')
            return
        if self.s.get('map') == TOA:
            self.change('Prepare', 'Checking supplies for next run')
            return
        peers = self.peers()
        all_done = all(peer and peer.get('phase') == 'Done' and int(peer.get('cycle', -1)) == self.cycle for _, peer in peers)
        leader = self.peer(self.leader_id) if not self.is_leader else None
        if (self.is_leader and (all_done or self.elapsed() >= 45)) or (leader and leader.get('phase') == 'Return'):
            self.return_sent = False
            self.change('Return', 'Resigning and returning team')
        elif self.elapsed() > 60:
            self.error('Leader did not return the team')

    def return_to_town(self):
        if self.s.get('map') == TOA and self.s.get('instance') == 0:
            self.change('Prepare', 'ToA confirmed; preparing next entry')
            return
        if self.elapsed() > 45:
            self.error('Return to ToA timed out; manual return required')
            return
        if not self.return_sent:
            self.game.call('resign')
            self.return_sent = True
        interval = 2 if self.test_mode else 3
        if self.elapsed() >= (2 if self.test_mode else 7) and self.due(interval) and (self.test_mode or self.is_leader):
            if self.test_mode:
                self.game.call('resign')
            self.game.call('return')

    def run(self):
        try:
            if not self.attach():
                return
            last_publish = 0
            while self.tick():
                if self.clock() - last_publish >= 1:
                    self.publish()
                    last_publish = self.clock()
                time.sleep(.1)
        except Exception as exc:
            self.log(traceback.format_exc())
            if isinstance(exc, PermissionError):
                self.error('Session file access denied after retries; see worker log for the affected file')
            else:
                self.error(f'Worker failed: {type(exc).__name__}; see worker log for details')
            while self.hub_alive() and read_ini(self.command_path).get('Control', 'Mode', fallback='stop') != 'stop':
                self.publish()
                time.sleep(1)
        finally:
            close_game = read_ini(self.command_path).getboolean('Control', 'CloseGame', fallback=False)
            if close_game:
                try:
                    self.game.call('close_game')
                except (RuntimeError, OSError):
                    pass
            self.game.close()
            self.phase = 'Stopped'
            self.state = 'Stopped — game client closed' if close_game else 'Stopped — game client left open'
            self.publish()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--session', required=True)
    parser.add_argument('--account', required=True)
    parser.add_argument('--hub-pid', type=int)
    parser.add_argument('--autoit', default=r'C:\Program Files (x86)\AutoIt3\AutoIt3.exe')
    args = parser.parse_args()
    if os.name != 'nt':
        raise SystemExit('SkeleBot requires Windows')
    config = read_ini(Path(args.session) / 'team.ini')
    member = next(dict(config[s]) for s in config.sections() if s.startswith('Member') and config[s]['ID'] == args.account)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.restype = ctypes.c_void_p
    mutex = kernel.CreateMutexW(None, False, 'Local\\SkelefarmCharacter_' + member['character'].lower())
    if ctypes.get_last_error() == 183:
        return
    root = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
    game = GameBridge(root, args.autoit, Path(args.session) / (args.account + '.bridge.log'))
    worker = Worker(args.session, args.account, game, hub_pid=args.hub_pid)
    worker.run()
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel.CloseHandle(mutex)


if __name__ == '__main__':
    main()
