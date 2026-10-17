"""Qt Skelefarm Hub, using EncounterHub's charcoal/teal stylesheet and row controls."""
import copy
import ctypes
import json
import os
from pathlib import Path
import sys
import subprocess
import uuid
from concurrent.futures import ThreadPoolExecutor
from PySide6.QtCore import Qt, QTimer, QSignalBlocker
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QCheckBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QFileDialog, QMessageBox, QDialog, QFormLayout, QLineEdit,
    QComboBox, QDialogButtonBox, QInputDialog, QScrollArea)
import controller as engine
from core import DEFAULT, atomic_text, write_control, read_status
from qt_style import STYLE
from version import VERSION

COLUMNS = ('select', 'character', 'team', 'role', 'status', 'render', 'pause', 'resume', 'stop', 'currency', 'tot', 'runs', 'fails', 'kills', 'captured', 'plat', 'storage_plat', 'skeletons', 'funding', 'dat')
CAPTIONS = ('Select', 'Character', 'Team', 'Role', 'Bot Status', 'Disable Rendering', 'Pause', 'Resume', 'Stop', 'Handle Currency', 'Open ToT', 'Runs', 'Fails', 'Kills', 'Captured', 'Carried Plat', 'Storage Plat', 'Skeletons', 'Funding', 'GW Dat')


class Dialogs:
    @staticmethod
    def showinfo(title, text):
        QMessageBox.information(None, title, text)
    @staticmethod
    def showerror(title, text):
        QMessageBox.critical(None, title, text)


class Files:
    @staticmethod
    def askopenfilename(title='Choose file', filetypes=None, **kwargs):
        filters = ';;'.join(f'{name} ({pattern})' for name, pattern in (filetypes or [('All files', '*.*')]))
        return QFileDialog.getOpenFileName(None, title, '', filters)[0]


class RootAdapter:
    def __init__(self, window):
        self.window = window
    def after(self, delay, callback):
        QTimer.singleShot(delay, self.window, callback)
    def destroy(self):
        self.window.force_close = True
        self.window.close()


class Notice:
    def __init__(self, label):
        self.label = label
    def set(self, text):
        self.label.setText(text)


class TableAdapter:
    """Keep the tested account/session controller independent from GUI toolkit."""
    def __init__(self, desktop):
        self.desktop = desktop
    def selection(self):
        return tuple(a['id'] for a in self.desktop.config['accounts'] if a['id'] in self.desktop.checked)
    def get_children(self):
        return tuple(self.desktop.rows)
    def insert(self, parent, where, iid, values):
        self.desktop.add_row(iid)
        self.item(iid, values=values)
    def delete(self, iid):
        self.desktop.widgets.pop(iid, None)
        self.desktop.grid.removeRow(self.desktop.rows.pop(iid))
        self.desktop.reindex()
    def item(self, iid, values=None):
        if values is None:
            return {}
        row = self.desktop.rows[iid]
        mapping = dict(zip(('character', 'team', 'role', 'dat', 'status', 'runs', 'fails', 'captured', 'rate', 'map'), values))
        account = next(a for a in self.desktop.config['accounts'] if a['id'] == iid)
        session = self.desktop.sessions.get(account['team'], {})
        status = read_status(Path(session.get('dir', '.')) / (iid + '.status.ini'))
        mapping['kills'] = status.get('kills', '0')
        mapping['plat'] = f"{int(status.get('gold', 0)) / 1000:g}"
        mapping['storage_plat'] = f"{int(status.get('storagegold', 0)) / 1000:g}"
        mapping['skeletons'] = status.get('skeletonsavailable', 0)
        mapping['funding'] = status.get('fundingstate', '')
        mapping['role'] = ''
        if engine.alive(session.get('pids', {}).get(iid)) and status.get('leaderselected', '1') == '1' and status.get('economyleader'):

            mapping['role'] = 'Leader' if iid == status['economyleader'] else 'Follower'
        for key, value in mapping.items():
            if key not in COLUMNS:
                continue
            if key == 'team':
                self.desktop.sync_team_selector(iid)
                continue
            index = COLUMNS.index(key)
            item = self.desktop.grid.item(row, index)
            if item is None:
                item = QTableWidgetItem()
                self.desktop.grid.setItem(row, index, item)
            item.setText(str(value))
        checkbox = self.desktop.widgets[iid]['render']
        with QSignalBlocker(checkbox):
            checkbox.setChecked(bool(int(status.get('renderingdisabled', int(account.get('rendering', True))))))


class BulkAccountDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Add Accounts')
        self.resize(680, 600)
        layout = QVBoxLayout(self)
        count_row = QHBoxLayout()
        count_row.addWidget(QLabel('Number of accounts'))
        self.count = QComboBox()
        self.count.addItems([str(n) for n in range(1, 11)])
        self.count.setObjectName('account_count')
        count_row.addWidget(self.count)
        layout.addLayout(count_row)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        form = QFormLayout(content)
        self.fields, self.field_rows = [], []
        for n in range(1, 11):
            fields, rows = {}, []
            for key, caption in [('character', 'Character Name'), ('gw_exe', 'Guild Wars Executable'), ('email', 'Email'), ('password', 'Account Password')]:
                editor = QLineEdit()
                editor.setObjectName(f'{key}_{n}')
                if key == 'password':
                    editor.setEchoMode(QLineEdit.EchoMode.Password)
                fields[key] = editor
                widget = editor
                if key == 'gw_exe':
                    widget = QWidget()
                    line = QHBoxLayout(widget)
                    line.setContentsMargins(0, 0, 0, 0)
                    line.addWidget(editor)
                    browse = QPushButton('Browse…')
                    def choose(checked=False, target=editor):
                        path = QFileDialog.getOpenFileName(self, 'Guild Wars Executable', '', 'Guild Wars (Gw.exe);;Executables (*.exe)')[0]
                        if path:
                            target.setText(path)
                    browse.clicked.connect(choose)
                    line.addWidget(browse)
                label = QLabel(f'{caption} Account {n}')
                form.addRow(label, widget)
                rows.append((label, widget))
            self.fields.append(fields)
            self.field_rows.append(rows)
        scroll.setWidget(content)
        layout.addWidget(scroll)
        layout.addWidget(QLabel('Gw.dat is checked beside each executable. Teams hold up to 8; extra accounts use another team.'))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.count.currentIndexChanged.connect(self.update_count)
        self.update_count()

    def update_count(self):
        count = int(self.count.currentText())
        for i, rows in enumerate(self.field_rows):
            for label, editor in rows:
                label.setVisible(i < count)
                editor.setVisible(i < count)

    def records(self):
        return [{key: editor.text() if key == 'password' else editor.text().strip() for key, editor in fields.items()}
                for fields in self.fields[:int(self.count.currentText())]]


class Desktop(QMainWindow):
    # The same account/controller reuse pattern as EncounterHub's Qt desktop.
    import_characters = engine.Hub.import_characters
    background = engine.Hub.background
    check_updates = engine.Hub.check_updates
    update_now = engine.Hub.update_now
    stop_all_workers = engine.Hub.stop_all_workers
    recovery_tick = engine.Hub.recovery_tick
    persist_sessions = engine.Hub.persist_sessions
    selected_teams = engine.Hub.selected_teams
    active = engine.Hub.active
    persist = engine.Hub.persist
    add = engine.Hub.add
    edit = engine.Hub.edit
    account_dialog = engine.Hub.account_dialog
    save_accounts = engine.Hub.save_accounts
    save_draft = engine.Hub.save_draft
    remove = engine.Hub.remove
    team_settings = engine.Hub.team_settings
    paths = engine.Hub.paths
    launch = engine.Hub.launch
    launch_next = engine.Hub.launch_next
    command = engine.Hub.command
    logs = engine.Hub.logs
    refresh = engine.Hub.refresh

    def __init__(self):
        super().__init__()
        engine.messagebox, engine.filedialog = Dialogs, Files
        self.config = copy.deepcopy(DEFAULT)
        self.sessions, self.children, self.launch_queue = {}, [], []
        self.busy = self.update_busy = self.force_close = False
        self.update_release = None
        self.pool = ThreadPoolExecutor(max_workers=1)
        try:
            if engine.CONFIG.exists():
                self.config = json.loads(engine.CONFIG.read_text())
            if engine.SESSIONS.exists():
                self.sessions = json.loads(engine.SESSIONS.read_text())
        except (OSError, ValueError) as exc:
            Dialogs.showerror('Settings', str(exc))
        engine.migrate_settings(self.config)
        self.save_draft()
        # Apply the user's requested temporary scenario once; later manual mode choices persist.
        if self.config.get('scenario_revision') != 1:
            for settings in self.config['teams'].values():
                settings.update(test_mode=True, assemble_only=False)
            self.config['scenario_revision'] = 1
            self.save_draft()
        self.checked = set(self.config.get('selected', []))
        self.rows, self.widgets = {}, {}
        self.root = RootAdapter(self)
        self.setWindowTitle(f'Skelefarm Hub {VERSION}')
        assets = Path(getattr(sys, '_MEIPASS', engine.ROOT)) / 'assets'
        self.setWindowIcon(QIcon(str(assets / 'skele-taco.ico')))
        self.resize(1450, 680)
        self.setMinimumSize(950, 480)
        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(12)
        top = QHBoxLayout()
        outer.addLayout(top)
        logo = QLabel()
        logo.setObjectName('skele_logo')
        logo.setPixmap(QPixmap(str(assets / 'skele-taco.png')).scaled(56, 56, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        top.addWidget(logo)
        title = QLabel('Skelefarm Hub')
        title.setStyleSheet('font-size:24px;font-weight:600;color:#52d4ba;')
        top.addWidget(title)
        top.addWidget(QLabel(f'v{VERSION}  •  Python SkeleBot'))
        top.addStretch()
        updates = QVBoxLayout()
        top.addLayout(updates)
        self.check_button = QPushButton('Check for Updates')
        self.check_button.clicked.connect(self.check_updates)
        updates.addWidget(self.check_button)
        self.update_button = QPushButton('Update Now')
        self.update_button.setProperty('primary', True)
        self.update_button.setEnabled(False)
        self.update_button.clicked.connect(self.update_now)
        updates.addWidget(self.update_button)
        toolbar = QHBoxLayout()
        outer.addLayout(toolbar)
        for label, callback in [('Import characters.ini', self.import_characters), ('Add Account', self.add),
                                ('Edit Account', self.edit), ('Remove', self.remove),
                                ('Team Settings', self.team_settings), ('AutoIT Path', self.paths),
                                ('Select All', lambda: self.select_all(True)), ('Clear Selection', lambda: self.select_all(False)),
                                ('Fit Columns', self.fit_columns)]:
            button = QPushButton(label)
            button.clicked.connect(callback)
            toolbar.addWidget(button)
        toolbar.addStretch()
        self.grid = QTableWidget(0, len(COLUMNS))
        self.grid.setHorizontalHeaderLabels(CAPTIONS)
        self.grid.setAlternatingRowColors(True)
        self.grid.setShowGrid(False)
        self.grid.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.grid.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.grid.verticalHeader().setVisible(False)
        self.grid.verticalHeader().setDefaultSectionSize(46)
        header = self.grid.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setMinimumSectionSize(60)
        widths = self.config.get('column_widths', {})
        defaults = (65, 200, 110, 80, 260, 145, 80, 80, 80, 140, 100, 65, 65, 65, 80, 100, 100, 85, 140, 240)
        self.loading_widths = True
        for i, key in enumerate(COLUMNS):
            header.resizeSection(i, int(widths.get(key, defaults[i])))
        self.loading_widths = False
        header.sectionResized.connect(self.width_changed)
        outer.addWidget(self.grid, 1)
        self.table = TableAdapter(self)
        footer = QHBoxLayout()
        outer.addLayout(footer)
        for label, callback in [('Launch All', self.launch_all), ('Launch Selected', self.launch), ('Pause Teams', lambda: self.command('pause')),
                                ('Resume Teams', lambda: self.command('run')), ('Stop Teams', lambda: self.command('stop')),
                                ('Handle Currency Selected', self.handle_currency_selected), ('Open ToT', self.open_tot_all), ('Open Logs', self.logs)]:
            button = QPushButton(label)
            if label == 'Launch Selected':
                button.setProperty('primary', True)
            button.clicked.connect(callback)
            footer.addWidget(button)
        footer.addStretch()
        label = QLabel('Combat test: no Mobstopper required. Kill skeleton → wait 2 seconds → resign → all accounts return to ToA → repeat.')
        label.setWordWrap(True)
        outer.addWidget(label)
        self.notice = Notice(label)
        previous_update = engine.DATA / 'last-update.json'
        if previous_update.is_file():
            try:
                report = json.loads(previous_update.read_text(encoding='utf-8-sig'))
                self.notice.set(report['message'] + (f" Log: {report['log']}" if not report.get('success') else ''))
                previous_update.unlink()
            except (ValueError, OSError, KeyError):
                pass
        self.refresh()
        from portable import cleanup_updates, archive_legacy
        def tidy():
            cleanup_updates(engine.DATA)
            archive_legacy(engine.DATA)
        QTimer.singleShot(10000, self, lambda: self.pool.submit(tidy) if not self.force_close else None)

    def bulk_account_dialog(self):
        dialog = BulkAccountDialog(self)
        return dialog.records() if dialog.exec() == QDialog.DialogCode.Accepted else None

    def reindex(self):
        self.rows = {self.grid.item(row, 1).data(Qt.ItemDataRole.UserRole): row for row in range(self.grid.rowCount())}

    def add_row(self, account_id):
        row = self.grid.rowCount()
        self.grid.insertRow(row)
        self.rows[account_id] = row
        self.widgets[account_id] = {}
        character = QTableWidgetItem()
        character.setData(Qt.ItemDataRole.UserRole, account_id)
        self.grid.setItem(row, 1, character)
        for key in ('select', 'render'):
            checkbox = QCheckBox()
            account = next(a for a in self.config['accounts'] if a['id'] == account_id)
            checkbox.setChecked(account_id in self.checked if key == 'select' else account.get('rendering', True))
            if key == 'select':
                checkbox.toggled.connect(lambda enabled, aid=account_id: self.set_selected(aid, enabled))
            else:
                checkbox.toggled.connect(lambda enabled, aid=account_id: self.set_rendering(aid, enabled))
            holder = QWidget()
            layout = QHBoxLayout(holder)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(checkbox)
            self.grid.setCellWidget(row, COLUMNS.index(key), holder)
            self.widgets[account_id][key] = checkbox
        combo = QComboBox()
        self.widgets[account_id]['team'] = combo
        self.grid.setCellWidget(row, COLUMNS.index('team'), combo)
        self.sync_team_selector(account_id)
        combo.activated.connect(lambda index, aid=account_id: self.choose_team(aid))
        for key in ('pause', 'resume', 'stop', 'currency', 'tot'):
            button = QPushButton('Handle Currency' if key == 'currency' else 'Open ToT' if key == 'tot' else key.title())
            if key == 'currency':
                button.setToolTip('Test the Eye of the North ectoplasm handler using the existing 800–900 platinum valuation rules. Runs after returning to an outpost.')
            button.clicked.connect(lambda checked=False, action=key, aid=account_id: self.row_action(aid, action))
            self.grid.setCellWidget(row, COLUMNS.index(key), button)

    def sync_team_selector(self, account_id):
        account = next(a for a in self.config['accounts'] if a['id'] == account_id)
        combo = self.widgets[account_id]['team']
        choices = list(self.config['teams']) + ['Create Team', 'Delete Team']
        with QSignalBlocker(combo):
            if [combo.itemText(i) for i in range(combo.count())] != choices:
                combo.clear()
                combo.addItems(choices)
            combo.setCurrentText(account['team'])

    def choose_team(self, account_id):
        account = next(a for a in self.config['accounts'] if a['id'] == account_id)
        choice = self.widgets[account_id]['team'].currentText()
        before = copy.deepcopy(self.config)
        try:
            if self.busy or self.active(account['team']):
                raise ValueError('Stop the team before changing its membership.')
            if choice == 'Create Team':
                name, ok = QInputDialog.getText(self, 'Create Team', 'Team name')
                if not ok:
                    return
                name = name.strip()
                if not name or name in self.config['teams'] or name in ('Create Team', 'Delete Team') or any(c in name for c in '\r\n'):
                    raise ValueError('Use a unique, nonempty team name.')
                self.config['teams'][name] = copy.deepcopy(DEFAULT['teams']['Team 1'])
                account['team'] = name
            elif choice == 'Delete Team':
                team = account['team']
                if team == 'Team 1':
                    raise ValueError('Must have at least one team')
                if self.active('Team 1'):
                    raise ValueError('Stop Team 1 before moving accounts into it.')
                for member in self.config['accounts']:
                    if member['team'] == team:
                        member['team'] = 'Team 1'
                del self.config['teams'][team]
                self.sessions.pop(team, None)
            else:
                if self.active(choice):
                    raise ValueError('Stop the destination team before moving accounts into it.')
                account['team'] = choice
            self.persist()
        except (ValueError, OSError) as exc:
            self.config = before
            Dialogs.showerror('Team', str(exc))
        finally:
            for aid in self.widgets:
                self.sync_team_selector(aid)

    def launch_all(self):
        previous = self.checked
        self.checked = {a['id'] for a in self.config['accounts']}
        try:
            self.launch()
        finally:
            self.checked = previous

    def set_selected(self, account_id, enabled):
        self.checked.add(account_id) if enabled else self.checked.discard(account_id)
        self.config['selected'] = sorted(self.checked)
        self.save_draft()

    def select_all(self, enabled):
        for account in self.config['accounts']:
            aid = account['id']
            self.set_selected(aid, enabled)
            if aid in self.widgets:
                with QSignalBlocker(self.widgets[aid]['select']):
                    self.widgets[aid]['select'].setChecked(enabled)

    def row_action(self, account_id, action):
        selected = self.checked
        self.checked = {account_id}
        try:
            if action == 'currency':
                self.request_currency({account_id})
            elif action == 'tot':
                self.request_tot({account_id})
            elif action == 'stop':
                account = next(a for a in self.config['accounts'] if a['id'] == account_id)
                session = self.sessions.get(account['team'])
                if session and account_id in session.get('pids', {}):
                    write_control(Path(session['dir']) / (account_id + '.command.ini'), mode='stop', close_game=True)
                self.notice.set('Stopping account: closing its Guild Wars client and worker.')
            elif action == 'launch':
                self.launch()
            else:
                self.command({'resume': 'run', 'pause': 'pause', 'stop': 'stop'}[action])
        finally:
            self.checked = selected

    def open_tot_all(self):
        self.request_tot({a['id'] for a in self.config['accounts']})

    def request_tot(self, account_ids):
        if self.update_busy or self.busy:
            self.notice.set('Finish launching/updating before Open ToT.')
            return
        targets = []
        for account in self.config['accounts']:
            if account['id'] not in account_ids:
                continue
            session = self.sessions.get(account['team'], {})
            pid = session.get('pids', {}).get(account['id'])
            if not pid or not engine.alive(pid):
                continue
            status = read_status(Path(session['dir']) / (account['id'] + '.status.ini'))
            if int(status.get('launchpid', status.get('pid', 0))) != pid:
                self.notice.set('Waiting for a current worker status; retry Open ToT shortly.')
                return
            if status.get('totactive') == '1':
                targets.append((session, account))
                continue
            if status.get('phase') != 'Paused' or status.get('mode') != 'pause' or int(status.get('instance', -1)) != 0 or status.get('currencyactive') == '1':
                self.notice.set('Pause all targeted accounts in an outpost before Open ToT. No requests were sent.')
                return
            targets.append((session, account))
        for session, account in targets:
            write_control(Path(session['dir']) / (account['id'] + '.command.ini'), tot_request=uuid.uuid4().hex)
        self.notice.set(f'Open ToT requested for {len(targets)} account(s): Great Temple → Kazuma → bags → cakes → ToA and resume.' if targets else 'Launch and pause accounts in an outpost before Open ToT.')

    def handle_currency_selected(self):
        self.request_currency(self.checked)

    def request_currency(self, account_ids):
        if self.update_busy:
            self.notice.set('Finish the update operation before requesting currency tests.')
            return
        queued = 0
        for account in self.config['accounts']:
            if account['id'] not in account_ids:
                continue
            session = self.sessions.get(account['team'], {})
            pid = session.get('pids', {}).get(account['id'])
            if not pid or not engine.alive(pid):
                continue
            if read_status(Path(session['dir']) / (account['id'] + '.status.ini')).get('totactive') == '1':
                continue
            write_control(Path(session['dir']) / (account['id'] + '.command.ini'), currency_request=uuid.uuid4().hex)
            queued += 1
        self.notice.set(f'Handle Currency queued for {queued} account(s); waits for an outpost, visits Eye of the North, applies existing buying rules, then returns to ToA.'
                        if queued else 'Launch the selected accounts first, then press Handle Currency.')

    def set_rendering(self, account_id, disabled):
        account = next(a for a in self.config['accounts'] if a['id'] == account_id)
        account['rendering'] = disabled
        self.save_draft()
        session = self.sessions.get(account['team'])
        if session and account_id in session.get('pids', {}):
            write_control(Path(session['dir']) / (account_id + '.command.ini'), rendering=disabled)
        self.notice.set('Rendering preference saved; active account updates immediately. Disabling also hides its GW window.')

    def width_changed(self, index, old, width):
        if self.loading_widths:
            return
        self.config['column_widths'] = {key: self.grid.columnWidth(i) for i, key in enumerate(COLUMNS)}
        self.save_draft()

    def fit_columns(self):
        self.loading_widths = True
        try:
            self.grid.resizeColumnsToContents()
            for i, key in enumerate(COLUMNS):
                self.grid.setColumnWidth(i, max(70, min(300, self.grid.columnWidth(i))))
            self.grid.setColumnWidth(COLUMNS.index('status'), 260)
            self.grid.setColumnWidth(COLUMNS.index('character'), 200)
        finally:
            self.loading_widths = False
        self.width_changed(0, 0, 0)

    def dialog(self, title, fields):
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        layout.addLayout(form)
        controls = {}
        for key, caption, value, choices in fields:
            if choices and choices != '__file__':
                widget = QComboBox()
                widget.addItems(choices)
                widget.setCurrentText(str(value))
            else:
                widget = QLineEdit(str(value))
                if key == 'password':
                    widget.setEchoMode(QLineEdit.EchoMode.Password)
            controls[key] = widget
            if choices == '__file__':
                row = QWidget()
                line = QHBoxLayout(row)
                line.setContentsMargins(0, 0, 0, 0)
                line.addWidget(widget)
                browse = QPushButton('Browse…')
                def choose(checked=False, name=key, target=widget):
                    suffix = '*.dat' if name == 'dat_path' else '*.ini' if name == 'characters_ini' else '*.exe'
                    path = QFileDialog.getOpenFileName(dialog, caption, '', f'Files ({suffix});;All files (*.*)')[0]
                    if path:
                        target.setText(path)
                        if name == 'dat_path' and 'gw_exe' in controls:
                            executable = Path(path).with_name('Gw.exe')
                            if executable.is_file():
                                controls['gw_exe'].setText(str(executable))
                browse.clicked.connect(choose)
                line.addWidget(browse)
                form.addRow(caption, row)
            else:
                form.addRow(caption, widget)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return {key: (widget.currentText() if isinstance(widget, QComboBox) else widget.text()) if key == 'password' else (widget.currentText() if isinstance(widget, QComboBox) else widget.text()).strip() for key, widget in controls.items()}

    def closeEvent(self, event):
        if not self.force_close and (self.busy or self.update_busy):
            self.notice.set('Wait for the launch/update operation to finish before closing.')
            event.ignore()
            return
        self.stop_all_workers()
        self.pool.shutdown(wait=False)
        event.accept()  # Worker cleanup restores rendering; game clients stay open.


def main():
    if os.name == 'nt':
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('SkelefarmHub.Desktop')
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(str(Path(getattr(sys, '_MEIPASS', engine.ROOT)) / 'assets' / 'skele-taco.ico')))
    app.setStyleSheet(STYLE)
    if os.name != 'nt':
        QMessageBox.critical(None, 'Windows required', 'Skelefarm Hub requires Windows.')
        return
    if not ctypes.windll.shell32.IsUserAnAdmin():
        args = [] if getattr(sys, 'frozen', False) else [str(Path(__file__).with_name('hub.pyw'))]
        result = ctypes.windll.shell32.ShellExecuteW(None, 'runas', sys.executable, subprocess.list2cmdline(args), str(engine.ROOT), 1)
        if result <= 32:
            QMessageBox.critical(None, 'Administrator access', 'Start the hub as administrator to attach to Guild Wars.')
        return
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.restype = ctypes.c_void_p
    mutex = kernel.CreateMutexW(None, False, 'Local\\SkelefarmHubController')
    if ctypes.get_last_error() == 183:
        QMessageBox.information(None, 'Skelefarm Hub', 'The hub is already running.')
        return
    window = Desktop()
    window.show()
    app.exec()
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel.CloseHandle(mutex)
