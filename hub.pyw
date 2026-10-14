"""Skelefarm Hub: Windows desktop controller, Python 3.11+ / Tk."""
import copy
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
import urllib.error
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import uuid
from accounts import read_characters, merge_accounts, validate_install
from version import VERSION, worker_name
from updater import check_release, stage_release, apply_and_restart
from core import DEFAULT, atomic_text, write_ini, read_status, save_config, snapshot, validate

ROOT = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
DATA = Path(os.environ.get('LOCALAPPDATA', str(ROOT))) / 'SkelefarmHub'
DATA.mkdir(parents=True, exist_ok=True)
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
        self.refresh()

    def import_characters(self):
        if self.busy or any(self.active(t) for t in self.sessions):
            return messagebox.showinfo('Active accounts', 'Stop workers before importing accounts.')
        path = filedialog.askopenfilename(title='Select your local characters.ini', filetypes=[('Character files', '*.ini'), ('All files', '*.*')])
        if not path:
            return
        old = copy.deepcopy(self.config)
        try:
            records = read_characters(path)
            merge_accounts(self.config, records)
            self.save_draft()
            self.notice.set(f'Imported {len(records)} characters. Set teams/leaders and verify each GW executable and Dat path. Credentials remain in the original local file.')
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
        self.check_button.configure(state='disabled')
        self.update_button.configure(state='disabled')
        self.notice.set('Checking GitHub releases…')
        def done(release, error):
            self.update_busy = False
            self.check_button.configure(state='normal')
            if error:
                self.update_release = None
                if isinstance(error, urllib.error.HTTPError) and error.code == 404:
                    self.notice.set('No published release is available yet.')
                else:
                    self.notice.set(f'Could not check for updates: {error}')
                return
            self.update_release = release
            if release:
                self.update_button.configure(state='normal')
                self.notice.set(f"Version {release['version']} is available. Update Now restarts only the hub; active workers stay running.")
            else:
                self.notice.set(f'You are up to date ({VERSION}).')
        self.background(check_release, done)

    def update_now(self):
        if not self.update_release or self.update_busy:
            return
        if self.busy:
            return messagebox.showinfo('Launching', 'Wait for the launch queue to finish before updating.')
        self.update_busy = True
        self.update_button.configure(state='disabled')
        self.check_button.configure(state='disabled')
        self.notice.set('Downloading and checking the update…')
        release = dict(self.update_release)
        def done(staging, error):
            if error:
                self.update_busy = False
                self.check_button.configure(state='normal')
                self.update_button.configure(state='normal')
                self.notice.set(f'Update failed; the hub and workers are still running: {error}')
                return
            try:
                self.persist_sessions()
                apply_and_restart(staging, ROOT, os.getpid())
            except Exception as exc:
                self.update_busy = False
                self.check_button.configure(state='normal')
                self.update_button.configure(state='normal')
                self.notice.set(f'Could not start update: {exc}')
                return
            self.root.destroy()
        self.background(lambda: stage_release(release, DATA), done)

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
        a = account or {'id': uuid.uuid4().hex[:12], 'character': '', 'team': 'Team 1', 'leader': False, 'profile': '', 'rendering': False}
        if self.active(a['team']) or self.busy:
            return messagebox.showinfo('Active team', 'Stop this team before editing its configuration.')
        result = self.dialog('Account', [
            ('character', 'Exact character name', a['character'], None),
            ('team', 'Team (new name creates a team)', a['team'], None),
            ('role', 'Role', 'Leader' if a['leader'] else 'Follower', ['Leader', 'Follower']),
            ('launch_mode', 'Launch mode', a.get('launch_mode', 'Attach'), ['Direct', 'Attach', 'Profile']),
            ('characters_ini', 'Local characters.ini', a.get('characters_ini', ''), '__file__'),
            ('gw_exe', 'Guild Wars executable', a.get('gw_exe', ''), '__file__'),
            ('dat_path', 'Gw.dat (same folder as executable)', a.get('dat_path', ''), '__file__'),
            ('crypto_seed', 'Original encryption script name', a.get('crypto_seed', 'Encounter_ReBuilt.au3'), None),
            ('profile', 'GW Launcher profile (Profile mode only)', a.get('profile', ''), None),
            ('rendering', 'Disable rendering', 'Yes' if a.get('rendering') else 'No', ['No', 'Yes']),
        ])
        if not result:
            return
        if not result['team'] or self.active(result['team']):
            return messagebox.showerror('Team', 'Use a nonempty team that is stopped.')
        before = copy.deepcopy(self.config)
        updated = dict(a, character=result['character'], team=result['team'], leader=result['role'] == 'Leader', profile=result['profile'], rendering=result['rendering'] == 'Yes', **{k: result[k] for k in ('launch_mode', 'characters_ini', 'gw_exe', 'dat_path', 'crypto_seed')})
        self.config['accounts'] = [x for x in self.config['accounts'] if x['id'] != a['id']] + [updated]
        self.config['teams'].setdefault(result['team'], copy.deepcopy(DEFAULT['teams']['Team 1']))
        # Permit incomplete teams while editing; full validation occurs at launch.
        try:
            self.save_draft()
        except Exception as exc:
            self.config = before
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
                               ('mode', 'Run mode', 'Assembly only' if s['assemble_only'] else 'Farm', ['Assembly only', 'Farm'])])
        if not r:
            return
        old = dict(s)
        try:
            s.update(region=int(r['region']), language=int(r['language']), district=int(r['district']), assemble_only=r['mode'] == 'Assembly only')
            self.save_draft()
        except (ValueError, KeyError) as exc:
            self.config['teams'][team] = old
            messagebox.showerror('Settings', str(exc))

    def paths(self):
        r = self.dialog('Program paths', [('autoit', 'AutoIt3.exe (32 bit)', self.config['autoit'], None),
                                           ('launcher', 'GW Launcher executable (optional)', self.config['launcher'], None)])
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
            self.notice.set('Teams started. Watch each account state; assembly-only will stop before paying for entry.')
            return
        team, directory, a = self.launch_queue.pop(0)
        try:
            flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
            if a.get('launch_mode') == 'Profile' and a.get('profile'):
                self.children.append(subprocess.Popen([self.config['launcher'], '-launch', a['profile']], cwd=str(Path(self.config['launcher']).parent), creationflags=flags))
            worker = [str(ROOT / worker_name())] if (ROOT / worker_name()).exists() else [self.config['autoit'], str(ROOT / 'Skelefarm.au3')]
            proc = subprocess.Popen(worker + ['--session', str(directory), '--account', a['id']], cwd=str(ROOT), creationflags=flags)
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
                    write_ini(Path(session['dir']) / (account_id + '.command.ini'), {'Control': {'Mode': mode}})
        self.notice.set({'pause': 'Pause requested: finish the current farm, return, then wait.', 'run': 'Resume requested for selected teams.', 'stop': 'Stop requested: workers restore rendering and exit. Game clients stay open.'}[mode])

    def logs(self):
        if os.name == 'nt':
            os.startfile(str(DATA / 'sessions' if (DATA / 'sessions').exists() else DATA))

    def refresh(self):
        existing = set(self.table.get_children())
        for a in self.config['accounts']:
            session = self.sessions.get(a['team'], {})
            status = read_status(Path(session.get('dir', '.')) / (a['id'] + '.status.ini'))
            pid = session.get('pids', {}).get(a['id'])
            running = alive(pid)
            state = status.get('state', 'Starting / no heartbeat' if running else 'Stopped')
            if running and status and int(status.get('pid', 0)) != pid:
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

    def close(self):
        if self.busy or self.update_busy:
            return messagebox.showinfo('Working', 'Wait for the launch or update operation to finish before closing.')
        # Workers are independent and reconnect through sessions.json on next launch.
        self.root.destroy()


if __name__ == '__main__':
    app = tk.Tk()
    if os.name != 'nt':
        messagebox.showerror('Windows required', 'Skelefarm Hub requires Windows and Guild Wars.')
        app.destroy()
    else:
        # Elevate the controller once, so worker PIDs remain stable (no UAC relaunch).
        if not ctypes.windll.shell32.IsUserAnAdmin():
            exe = sys.executable
            args = [] if getattr(sys, 'frozen', False) else [str(Path(__file__).resolve())]
            result = ctypes.windll.shell32.ShellExecuteW(None, 'runas', exe, subprocess.list2cmdline(args), str(ROOT), 1)
            if result <= 32:
                messagebox.showerror('Administrator access', 'Administrator access is needed to attach to Guild Wars. Start the hub as administrator.')
            app.destroy()
            sys.exit(0)
        # Prevent concurrent hubs from issuing conflicting commands.
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateMutexW.restype = ctypes.c_void_p
        mutex = kernel.CreateMutexW(None, False, 'Local\\SkelefarmHubController')
        if ctypes.get_last_error() == 183:
            messagebox.showinfo('Skelefarm Hub', 'The hub is already running.')
            app.destroy()
        else:
            Hub(app)
            app.mainloop()
