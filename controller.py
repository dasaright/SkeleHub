"""Skelefarm Hub: Windows desktop controller, Python 3.11+ / Tk."""
import copy
import configparser
import ctypes
import json
import os
import queue
from pathlib import Path
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
import urllib.error
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import uuid
from accounts import read_characters, merge_accounts, validate_install, migrate_settings, save_character, character_email
from portable import prepare_data, managed_characters
from windows_recovery import dismiss_crash_dialogs
from version import VERSION, worker_name
from updater import check_release, stage_release, apply_and_restart
from core import DEFAULT, atomic_text, write_ini, write_control, read_status, save_config, snapshot, validate

ROOT = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
DATA = prepare_data(ROOT)
CONFIG = DATA / 'settings.json'
SESSIONS = DATA / 'sessions.json'


def alive(pid):
    if os.name != 'nt' or not pid:
        return False
    k = ctypes.WinDLL('kernel32', use_last_error=True)
    k.OpenProcess.restype = ctypes.c_void_p
    k.CloseHandle.argtypes = [ctypes.c_void_p]
    k.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
    handle = k.OpenProcess(0x1000, False, int(pid))
    if not handle:
        return False
    code = ctypes.c_ulong()
    ok = k.GetExitCodeProcess(handle, ctypes.byref(code))
    k.CloseHandle(handle)
    return bool(ok and code.value == 259)


def button_enabled(button, enabled):
    """Support the Qt desktop and the archived Tk controller without toolkit leaks."""
    if hasattr(button, 'setEnabled'):
        button.setEnabled(enabled)
    else:
        button.configure(state='normal' if enabled else 'disabled')


class Hub:
    def __init__(self, root):
        self.root = root
        self.config = copy.deepcopy(DEFAULT)
        self.sessions = {}
        self.children = []
        self.launch_queue = []
        self.busy = False
        self.update_release = None
        self.update_busy = False
        self.pool = ThreadPoolExecutor(max_workers=1)
        try:
            if CONFIG.exists():
                self.config = json.loads(CONFIG.read_text())
            if SESSIONS.exists():
                self.sessions = json.loads(SESSIONS.read_text())
        except (ValueError, OSError, KeyError) as exc:
            messagebox.showerror('Settings', str(exc))
        root.title(f'Skelefarm Hub {VERSION}')
        root.geometry('1120x580')
        root.minsize(850, 450)
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('Treeview', rowheight=29)
        tools = ttk.Frame(root, padding=10)
        tools.pack(fill='x')
        for text, fn in [('Import characters.ini', self.import_characters), ('Add account', self.add), ('Edit account', self.edit),
                         ('Remove', self.remove), ('Team settings', self.team_settings),
                         ('Paths', self.paths), ('Open logs', self.logs)]:
            ttk.Button(tools, text=text, command=fn).pack(side='left', padx=3)
        ttk.Label(root, text='Select the accounts to launch. Include exactly one leader for each selected team.', padding=(12, 0)).pack(anchor='w')
        updates = ttk.Frame(root, padding=(12, 4))
        updates.pack(fill='x')
        ttk.Label(updates, text=f'Version {VERSION}  •  github.com/dasaright/SkeleHub').pack(side='left')
        update_buttons = ttk.Frame(updates)
        update_buttons.pack(side='right')
        self.check_button = ttk.Button(update_buttons, text='Check for Update', command=self.check_updates)
        self.check_button.pack(fill='x')
        self.update_button = ttk.Button(update_buttons, text='Update Now', command=self.update_now, state='disabled')
        self.update_button.pack(fill='x', pady=(3, 0))
        frame = ttk.Frame(root, padding=10)
        frame.pack(fill='both', expand=True)
        cols = ('character', 'team', 'role', 'dat', 'state', 'runs', 'fails', 'captured', 'rate', 'map')
        self.table = ttk.Treeview(frame, columns=cols, show='headings', selectmode='extended')
        for col, width in zip(cols, (190, 90, 70, 220, 240, 55, 55, 65, 65, 75)):
            self.table.heading(col, text=col.title())
            self.table.column(col, width=width, minwidth=45, stretch=col in ('character', 'state'))
        scroll = ttk.Scrollbar(frame, orient='vertical', command=self.table.yview)
        xscroll = ttk.Scrollbar(frame, orient='horizontal', command=self.table.xview)
        self.table.configure(yscrollcommand=scroll.set, xscrollcommand=xscroll.set)
        self.table.grid(row=0, column=0, sticky='nsew')
        scroll.grid(row=0, column=1, sticky='ns')
        xscroll.grid(row=1, column=0, sticky='ew')
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        self.table.bind('<Double-1>', lambda e: self.edit())
        actions = ttk.Frame(root, padding=10)
        actions.pack(fill='x')
        for text, fn in [('Launch selected accounts', self.launch),
                         ('Pause teams', lambda: self.command('pause')),
                         ('Resume teams', lambda: self.command('run')),
                         ('Stop teams', lambda: self.command('stop'))]:
            ttk.Button(actions, text=text, command=fn).pack(side='left', padx=3)
        self.notice = tk.StringVar(value='Add characters, assign a leader per team, then launch. Assembly-only is enabled by default.')
        ttk.Label(root, textvariable=self.notice, padding=10, wraplength=1050).pack(fill='x')
        root.protocol('WM_DELETE_WINDOW', self.close)
        previous_update = DATA / 'last-update.json'
        if previous_update.is_file():
            try:
                report = json.loads(previous_update.read_text(encoding='utf-8-sig'))
                self.notice.set(report['message'] + (f" Log: {report['log']}" if not report.get('success') else ''))
                previous_update.unlink()
            except (ValueError, OSError, KeyError):
                pass
        self.refresh()

    def import_characters(self):
        if self.busy or any(self.active(t) for t in self.sessions):
            return messagebox.showinfo('Active accounts', 'Stop workers before importing accounts.')
        path = filedialog.askopenfilename(title='Select your local characters.ini', filetypes=[('Character files', '*.ini'), ('All files', '*.*')])
        if not path:
            return
        old = copy.deepcopy(self.config)
        try:
            path = str(managed_characters(path, DATA))
            records = read_characters(path)
            merge_accounts(self.config, records)
            self.config['characters_ini'] = str(Path(path).resolve())
            self.save_draft()
            self.notice.set(f'Imported {len(records)} characters. Assign teams in the main window and verify each GW executable. Credentials remain in the original local file.')
        except (ValueError, OSError, KeyError) as exc:
            self.config = old
            messagebox.showerror('Import', str(exc))

    def background(self, task, done):
        future = self.pool.submit(task)
        def poll():
            if not future.done():
                self.root.after(200, poll)
                return
            try:
                result = future.result()
            except Exception as exc:
                done(None, exc)
            else:
                done(result, None)
        self.root.after(200, poll)

    def check_updates(self):
        if self.update_busy:
            return
        self.update_busy = True
        button_enabled(self.check_button, False)
        button_enabled(self.update_button, False)
        self.notice.set('Checking GitHub releases…')
        def done(release, error):
            self.update_busy = False
            button_enabled(self.check_button, True)
            if error:
                self.update_release = None
                if isinstance(error, urllib.error.HTTPError) and error.code == 404:
                    self.notice.set('No published release is available yet.')
                else:
                    self.notice.set(f'Could not check for updates: {error}')
                return
            self.update_release = release
            if release:
                button_enabled(self.update_button, True)
                self.notice.set(f"Version {release['version']} is available. Update Now stops workers and restarts the hub; game clients stay open.")
            else:
                self.notice.set(f'You are up to date ({VERSION}).')
        self.background(check_release, done)

    def update_now(self):
        if not self.update_release or self.update_busy:
            return
        if self.busy:
            return messagebox.showinfo('Launching', 'Wait for the launch queue to finish before updating.')
        self.update_busy = True
        button_enabled(self.update_button, False)
        button_enabled(self.check_button, False)
        self.notice.set('Preparing update download…')
        release = dict(self.update_release)
        updates = queue.SimpleQueue()
        def show_progress():
            latest = None
            while not updates.empty():
                latest = updates.get_nowait()
            if latest is not None and self.update_busy:
                self.notice.set(latest)
            if self.update_busy:
                self.root.after(100, show_progress)
        self.root.after(100, show_progress)
        def failed(message):
            self.update_busy = False
            button_enabled(self.check_button, True)
            button_enabled(self.update_button, True)
            self.notice.set(message)
        def helper_ready(result, error):
            if error:
                failed(f'Could not start update; hub remains open: {error}')
                return
            self.notice.set(f"Installing v{release['version']} — stopping workers and restarting the hub…")
            self.root.after(200, self.root.destroy)
        def done(staging, error):
            if error:
                failed(f'Update failed; hub remains open: {error}')
                return
            # Drain queued download text before starting the next phase.
            while not updates.empty():
                updates.get_nowait()
            self.notice.set('Starting update helper; waiting for startup confirmation…')
            try:
                self.persist_sessions()
            except Exception as exc:
                failed(f'Could not prepare update: {exc}')
                return
            # The helper handshake can take eight seconds. Keep the GUI responsive.
            self.background(lambda: apply_and_restart(staging, ROOT, os.getpid()), helper_ready)
        self.background(lambda: stage_release(release, DATA, progress=updates.put), done)

    def persist_sessions(self):
        atomic_text(SESSIONS, json.dumps(self.sessions, indent=2))

    def selected_teams(self):
        selected = set(self.table.selection())
        return {a['team'] for a in self.config['accounts'] if a['id'] in selected}

    def active(self, team):
        session = self.sessions.get(team)
        if not session:
            return False
        return any(read_status(Path(session['dir']) / (account_id + '.status.ini')).get('phase') != 'Stopped'
                   and alive(pid) for account_id, pid in session.get('pids', {}).items())

    def persist(self):
        self.save_draft()
        self.persist_sessions()

    def dialog(self, title, fields):
        win = tk.Toplevel(self.root)
        win.title(title)
        win.transient(self.root)
        win.grab_set()
        variables = {}
        for i, (key, label, value, choices) in enumerate(fields):
            ttk.Label(win, text=label).grid(row=i, column=0, sticky='w', padx=12, pady=6)
            var = tk.StringVar(value=str(value))
            variables[key] = var
            is_file = choices == '__file__'
            widget = ttk.Combobox(win, textvariable=var, values=choices, state='readonly', width=48) if choices and not is_file else ttk.Entry(win, textvariable=var, width=51)
            widget.grid(row=i, column=1, padx=12, pady=6)
            if is_file:
                def browse(v=var, k=key):
                    patterns = '*.dat' if k == 'dat_path' else '*.ini' if k == 'characters_ini' else '*.exe'
                    path = filedialog.askopenfilename(parent=win, filetypes=[('Select file', patterns), ('All files', '*.*')])
                    if path:
                        v.set(path)
                        if k == 'dat_path' and Path(path).name.lower() == 'gw.dat' and 'gw_exe' in variables:
                            exe = Path(path).with_name('Gw.exe')
                            if exe.is_file():
                                variables['gw_exe'].set(str(exe))
                ttk.Button(win, text='Browse…', command=browse).grid(row=i, column=2, padx=(0, 12))
        answer = []
        def done():
            answer.append({k: v.get().strip() for k, v in variables.items()})
            win.destroy()
        ttk.Button(win, text='Save', command=done).grid(row=len(fields), column=1, sticky='e', padx=12, pady=12)
        win.bind('<Return>', lambda e: done())
        self.root.wait_window(win)
        return answer[0] if answer else None

    def add(self):
        self.account_dialog(None)

    def edit(self):
        if self.table.selection():
            self.account_dialog(next(a for a in self.config['accounts'] if a['id'] == self.table.selection()[0]))

    def account_dialog(self, account):
        if account is None:
            if self.busy or any(self.active(team) for team in self.config['teams']):
                return messagebox.showinfo('Active accounts', 'Stop teams before adding accounts.')
            results = self.bulk_account_dialog()
            if results:
                self.save_accounts(results)
            return
        a = account
        if self.active(a['team']) or self.busy:
            return messagebox.showinfo('Active team', 'Stop this team before editing its configuration.')
        ini = a.get('characters_ini') or self.config.get('characters_ini') or str(DATA / 'characters.ini')
        result = self.dialog('Account', [
            ('character', 'Character Name', a['character'], None),
            ('gw_exe', 'Guild Wars Executable', a.get('gw_exe', ''), '__file__'),
            ('email', 'Account Email', character_email(ini, a.get('section', a['character'])), None),
            ('password', 'Account Password (blank keeps saved password)', '', None),
        ])
        if result:
            self.save_accounts([result], account)

    def save_accounts(self, results, account=None):
        before = copy.deepcopy(self.config)
        backups = {}
        try:
            from pathlib import PureWindowsPath
            from accounts import protect_password
            entries = []
            for result in results:
                a = account or dict(id=uuid.uuid4().hex[:12], character='', team='Team 1', leader=False, rendering=True)
                if not account:
                    # GW parties have eight slots. Spill bulk additions into another team.
                    team = next((name for name in self.config['teams'] if sum(x['team'] == name for x in self.config['accounts']) < 8), None)
                    if team is None:
                        n = 2
                        while f'Team {n}' in self.config['teams']:
                            n += 1
                        team = f'Team {n}'
                        self.config['teams'][team] = copy.deepcopy(DEFAULT['teams']['Team 1'])
                    a['team'] = team
                ini = str(managed_characters(a.get('characters_ini') or self.config.get('characters_ini') or DATA / 'characters.ini', DATA))
                dat = str(PureWindowsPath(result['gw_exe']).with_name('Gw.dat'))
                validate_install(result['gw_exe'], dat)
                if not result['email'] or any(c in result['email'] for c in '\r\n'):
                    raise ValueError('Enter an account email for each account.')
                if not account and not result['password']:
                    raise ValueError('Enter a password for each new account.')
                updated = dict(a, character=result['character'], gw_exe=result['gw_exe'], dat_path=dat,
                               characters_ini=ini, section=result['character'], launch_mode='Direct',
                               crypto_seed=a.get('crypto_seed', 'Encounter_ReBuilt.au3'), leader=False,
                               rendering=a.get('rendering', True))
                if account:
                    self.config['accounts'] = [updated if x['id'] == a['id'] else x for x in self.config['accounts']]
                else:
                    self.config['accounts'].append(updated)
                entries.append((ini, result, a))
            # Validate the whole batch before writing credentials or settings.
            candidate = copy.deepcopy(self.config)
            for team in candidate['teams']:
                for i, a in enumerate(x for x in candidate['accounts'] if x['team'] == team):
                    a['leader'] = i == 0
            validate(candidate)
            for ini, result, a in entries:
                target = Path(ini)
                if target not in backups:
                    backups[target] = target.read_bytes() if target.exists() else None
                save_character(ini, result['character'], result['email'], result['gw_exe'], result['password'],
                               old_section=a.get('section', a['character']))
            self.save_draft()
            self.notice.set(f'Saved {len(entries)} account(s). Credentials and settings are in Files beside the bot.')
        except (ValueError, OSError) as exc:
            self.config = before
            for target, contents in backups.items():
                if contents is None:
                    target.unlink(missing_ok=True)
                else:
                    # Restore the original encoding exactly.
                    target.write_bytes(contents)
            messagebox.showerror('Account', str(exc))

    def save_draft(self):
        # Validate account strings and IDs through a temporary leader-normalized copy.
        candidate = copy.deepcopy(self.config)
        for team in candidate['teams']:
            members = [a for a in candidate['accounts'] if a['team'] == team]
            for i, a in enumerate(members):
                a['leader'] = i == 0
        validate(candidate)
        atomic_text(CONFIG, json.dumps(self.config, indent=2))

    def remove(self):
        teams = self.selected_teams()
        if any(self.active(t) for t in teams) or self.busy:
            return messagebox.showinfo('Active team', 'Stop the team before removing accounts.')
        ids = set(self.table.selection())
        self.config['accounts'] = [a for a in self.config['accounts'] if a['id'] not in ids]
        self.save_draft()

    def team_settings(self):
        teams = self.selected_teams()
        if len(teams) != 1:
            return messagebox.showinfo('Select team', 'Select an account from one team.')
        team = next(iter(teams))
        if self.active(team) or self.busy:
            return messagebox.showinfo('Active team', 'Stop this team before changing its settings.')
        s = self.config['teams'][team]
        r = self.dialog(team, [('region', 'Region (-2 International, 0 America, 2 Europe)', s['region'], None),
                               ('language', 'Language ID (0 English)', s['language'], None),
                               ('district', 'District number', s['district'], None),
                               ('mode', 'Run mode', 'Assembly only' if s['assemble_only'] else 'Combat test' if s.get('test_mode', True) else 'Farm', ['Combat test', 'Assembly only', 'Farm']),
                               ('funding', 'Rotate leaders by platinum', 'Yes' if s.get('funding_rotation', True) else 'No', ['Yes', 'No']),
                               ('turnin', 'Enable seasonal turn-ins (not live tested)', 'Yes' if s.get('turnin_enabled', False) else 'No', ['No', 'Yes'])])
        if not r:
            return
        old = dict(s)
        try:
            s.update(region=int(r['region']), language=int(r['language']), district=int(r['district']), assemble_only=r['mode'] == 'Assembly only', test_mode=r['mode'] == 'Combat test', funding_rotation=r['funding'] == 'Yes', turnin_enabled=r['turnin'] == 'Yes')
            self.save_draft()
        except (ValueError, KeyError) as exc:
            self.config['teams'][team] = old
            messagebox.showerror('Settings', str(exc))

    def paths(self):
        r = self.dialog('AutoIT Path', [('autoit', 'AutoIt3.exe (32 bit)', self.config['autoit'], '__file__')])
        if r:
            self.config.update(r)
            self.save_draft()

    def launch(self):
        teams = self.selected_teams()
        if not teams or self.busy or self.update_busy:
            return
        try:
            selected = set(self.table.selection())
            launch_config = copy.deepcopy(self.config)
            launch_config['accounts'] = [a for a in launch_config['accounts'] if a['id'] in selected]
            for team in teams:
                for i, account in enumerate(a for a in launch_config['accounts'] if a['team'] == team):
                    account['leader'] = i == 0
            validate(launch_config)
            if not (ROOT / worker_name()).exists() and not Path(self.config['autoit']).is_file():
                raise ValueError('Set the 32-bit AutoIt3.exe path under Paths, or build the versioned worker executable.')
            for team in teams:
                if self.active(team):
                    raise ValueError(f'{team} is already running. Use Resume, or stop it first.')
                members = [a for a in launch_config['accounts'] if a['team'] == team]
                for a in members:
                    if a.get('launch_mode') == 'Direct':
                        if not Path(a.get('characters_ini', '')).is_file():
                            raise ValueError('Select a local characters.ini for direct account launching.')
                        validate_install(a.get('gw_exe', ''), a.get('dat_path', ''))
                if any(a.get('launch_mode') == 'Profile' and a.get('profile') for a in members) and not Path(self.config['launcher']).is_file():
                    raise ValueError('Set the GW Launcher executable under Paths.')
            # Freeze team membership for this session. No live edits to shared team files.
            for team in sorted(teams):
                directory = DATA / 'sessions' / uuid.uuid4().hex
                members = snapshot(launch_config, team, directory)
                self.sessions[team] = {'dir': str(directory), 'pids': {}}
                self.launch_queue.extend((team, directory, a) for a in members)
            self.persist()
            self.busy = True
            self.launch_next()
        except (ValueError, OSError, KeyError) as exc:
            messagebox.showerror('Launch', str(exc))

    def launch_next(self):
        if not self.launch_queue:
            self.busy = False
            self.notice.set('Selected accounts started. Combat test repeats UW kills and returns; assembly-only does not enter UW.')
            return
        team, directory, a = self.launch_queue.pop(0)
        try:
            flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
            if a.get('launch_mode') == 'Profile' and a.get('profile'):
                self.children.append(subprocess.Popen([self.config['launcher'], '-launch', a['profile']], cwd=str(Path(self.config['launcher']).parent), creationflags=flags))
            worker = [str(ROOT / worker_name())] if (ROOT / worker_name()).exists() else [sys.executable, str(ROOT / 'worker.py')]
            proc = subprocess.Popen(worker + ['--session', str(directory), '--account', a['id'], '--autoit', self.config['autoit'], '--hub-pid', str(os.getpid())], cwd=str(ROOT), creationflags=flags)
            self.children.append(proc)
            self.sessions[team]['pids'][a['id']] = proc.pid
            self.persist()
            self.notice.set(f"Launching {a['character']} — waiting for character login.")
        except OSError as exc:
            self.notice.set(f"Launch failed for {a['character']}: {exc}. Team will wait for missing accounts.")
        # Stagger scans/login requests; UI remains responsive.
        self.root.after(5000, self.launch_next)

    def command(self, mode):
        teams = self.selected_teams()
        if self.busy:
            return messagebox.showinfo('Launching', 'Wait for the launch queue to finish.')
        for team in teams:
            session = self.sessions.get(team)
            if session:
                for account_id in session.get('pids', {}):
                    write_control(Path(session['dir']) / (account_id + '.command.ini'), mode=mode, close_game=(mode == 'stop'))
        self.notice.set({'pause': 'Pause requested: finish the current farm, return, then wait.', 'run': 'Resume requested for selected teams.', 'stop': 'Stop requested: selected teams close their game clients and workers.'}[mode])

    def logs(self):
        if os.name == 'nt':
            os.startfile(str(DATA / 'sessions' if (DATA / 'sessions').exists() else DATA))

    def recovery_tick(self):
        if self.update_busy or getattr(self, 'force_close', False):
            return
        now = time.monotonic()
        if now < getattr(self, '_recovery_next', 0):
            return
        self._recovery_next = now + 3
        if not hasattr(self, '_recovery'):
            self._recovery = {}
        active = []
        for account in self.config['accounts']:
            session = self.sessions.get(account['team'], {})
            if account['id'] not in session.get('pids', {}):
                continue
            directory = Path(session['dir'])
            control = configparser.ConfigParser(interpolation=None)
            control.read(directory / (account['id'] + '.command.ini'), encoding='utf-16')
            status = read_status(directory / (account['id'] + '.status.ini'))
            active.append((account, session, directory, control, status))
        pids = {int(status.get('gamepid', 0)) for _, _, _, _, status in active} - {0}
        dialogs = dismiss_crash_dialogs(pids, [a.get('gw_exe', '') for a, _, _, c, _ in active if c.get('Control', 'Mode', fallback='stop') != 'stop'])
        for account, session, directory, control, status in active:
            aid = account['id']
            key = (str(directory), aid)
            state = self._recovery.setdefault(key, {'attempts': 0, 'since': None, 'pending': False})
            mode = control.get('Control', 'Mode', fallback='stop')
            if mode not in ('run', 'pause') and not control.getboolean('Control', 'Recover', fallback=False):
                state['pending'] = False
                state['since'] = None
                continue
            worker_pid = session['pids'][aid]
            game_pid = int(status.get('gamepid', 0))
            crash = any(d['pid'] == game_pid or (not game_pid and os.path.normcase(d['path']) == os.path.normcase(account.get('gw_exe', ''))) for d in dialogs)
            identity = int(status.get('launchpid', status.get('pid', 0))) == worker_pid
            client_exited = identity and game_pid > 0 and not alive(game_pid)
            failed = crash or client_exited or (identity and status.get('phase') == 'Error') or not alive(worker_pid)
            if state['pending']:
                if not alive(worker_pid) and not self.busy:
                    write_control(directory / (aid + '.command.ini'), mode=state.get('resume_mode', 'run'), close_game=False)
                    self.launch_queue.append((account['team'], directory, account))
                    state.update(pending=False, since=None)
                    self.busy = True
                    self.launch_next()
                elif now - state['since'] > 45:
                    state.update(pending=False, attempts=3)
                    write_control(directory / (aid + '.command.ini'), mode='stop', close_game=True)
                    self.notice.set(f"Recovery stopped for {account['character']}: old worker did not exit. Check logs.")
                continue
            if not failed:
                state['since'] = None
                if identity and status.get('phase') not in ('Error', 'Stopped') and game_pid and alive(game_pid):
                    state.setdefault('healthy_since', now)
                    if now - state['healthy_since'] >= 120:
                        state['attempts'] = 0
                continue
            state.pop('healthy_since', None)
            if state['since'] is None:
                state['since'] = now
            if not crash and now - state['since'] < 8:
                continue
            if state['attempts'] >= 3:
                continue
            state['attempts'] += 1
            state.update(pending=True, since=now, resume_mode=mode if mode in ('run', 'pause') else state.get('resume_mode', 'run'))
            write_control(directory / (aid + '.command.ini'), mode='stop', close_game=True, recover=True)
            self.notice.set(f"Restarting {account['character']} after failure ({state['attempts']}/3); crash reports use Don't Send.")

    def refresh(self):
        try:
            self.recovery_tick()
        except (OSError, ValueError, configparser.Error) as exc:
            if not self.update_busy:
                self.notice.set(f'Recovery check delayed: {type(exc).__name__}; retrying.')
        existing = set(self.table.get_children())
        for a in self.config['accounts']:
            session = self.sessions.get(a['team'], {})
            status = read_status(Path(session.get('dir', '.')) / (a['id'] + '.status.ini'))
            pid = session.get('pids', {}).get(a['id'])
            running = alive(pid)
            state = status.get('state', 'Starting / no heartbeat' if running else 'Stopped')
            if running and status and int(status.get('launchpid', status.get('pid', 0))) != pid:
                state = 'Worker identity mismatch'
            elif not running and pid:
                state = 'Stopped' if state == 'Stopped' else 'Worker exited — check log'
            values = (a['character'], a['team'], 'Leader' if a['leader'] else 'Follower', a.get('dat_path', ''),
                      state, status.get('runs', '0'), status.get('fails', '0'), status.get('captured', '0'),
                      status.get('rate', '0'), status.get('map', '—'))
            if a['id'] in existing:
                self.table.item(a['id'], values=values)
                existing.remove(a['id'])
            else:
                self.table.insert('', 'end', iid=a['id'], values=values)
        for item in existing:
            self.table.delete(item)
        self.children = [p for p in self.children if p.poll() is None]
        self.root.after(1000, self.refresh)

    def stop_all_workers(self):
        for session in self.sessions.values():
            for account_id in session.get('pids', {}):
                write_control(Path(session['dir']) / (account_id + '.command.ini'), mode='stop', close_game=False)

    def close(self):
        if self.busy or self.update_busy:
            return messagebox.showinfo('Working', 'Wait for the launch or update operation to finish before closing.')
        self.stop_all_workers()
        self.root.destroy()

