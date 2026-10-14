"""Portable hub data and explicit migration from older user-profile installs."""
import hashlib
import json
import os
from pathlib import Path
import shutil
from core import atomic_text


def managed_characters(source, data):
    source, data = Path(source), Path(data)
    try:
        source.resolve().relative_to(data.resolve())
        return source
    except ValueError:
        pass
    target = data / ('characters-' + hashlib.sha256(str(source.resolve()).encode()).hexdigest()[:12] + '.ini')
    if source.is_file() and not target.exists():
        shutil.copy2(source, target)
    return target


def prepare_data(root, legacy=None):
    root = Path(root)
    data = root / 'Files'
    data.mkdir(parents=True, exist_ok=True)
    marker = data / 'portable-migration.json'
    legacy = Path(legacy) if legacy else Path(os.environ.get('LOCALAPPDATA', root)) / 'SkelefarmHub'
    if marker.exists():
        return data
    if legacy.is_dir() and legacy.resolve() != data.resolve():
        # A failed/interrupted migration is restartable. Never overwrite newer portable data.
        for source in legacy.rglob('*'):
            rel = source.relative_to(legacy)
            if any(part.startswith('update-') for part in rel.parts) or source.is_symlink():
                continue
            target = data / rel
            if source.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            elif not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
    settings = data / 'settings.json'
    if settings.exists():
        config = json.loads(settings.read_text())
        for record in [config] + config.get('accounts', []):
            source = record.get('characters_ini')
            if source:
                record['characters_ini'] = str(managed_characters(source, data))
        atomic_text(settings, json.dumps(config, indent=2))
    sessions = data / 'sessions.json'
    if sessions.exists():
        registry = json.loads(sessions.read_text())
        for session in registry.values():
            try:
                rel = Path(session['dir']).resolve().relative_to(legacy.resolve())
                session['dir'] = str(data / rel)
            except ValueError:
                pass
        atomic_text(sessions, json.dumps(registry, indent=2))
    atomic_text(marker, json.dumps({'migrated': True, 'previous_data': str(legacy)}))
    return data


def cleanup_updates(data):
    """Remove completed installer payloads, retaining a small update log."""
    data = Path(data)
    for stage in data.glob('update-*'):
        if not stage.is_dir() or stage.is_symlink():
            continue
        log = stage / 'update.log'
        try:
            text = log.read_text(encoding='utf-8-sig')
            if 'Update applied; hub restarted.' not in text:
                continue
            logs = data / 'logs'
            logs.mkdir(exist_ok=True)
            shutil.copy2(log, logs / (stage.name + '.log'))
            shutil.rmtree(stage)
        except (OSError, UnicodeError):
            continue


def archive_legacy(data):
    """Keep the migration backup portable after the old updater has finished."""
    data = Path(data)
    try:
        marker = data / 'portable-migration.json'
        state = json.loads(marker.read_text())
        legacy = Path(state['previous_data'])
        if legacy.name != 'SkelefarmHub' or legacy.resolve() == data.resolve() or not legacy.is_dir():
            return
        # Do not interfere with any old worker still finishing shutdown.
        from worker import process_alive
        registry = legacy / 'sessions.json'
        if registry.is_file():
            sessions = json.loads(registry.read_text())
            if any(process_alive(pid) for session in sessions.values() for pid in session.get('pids', {}).values()):
                return
        target = data / 'migration-backup'
        if target.exists():
            return
        shutil.move(str(legacy), str(target))
        cleanup_updates(target)
        state['archived_to'] = str(target)
        atomic_text(marker, json.dumps(state))
    except (OSError, ValueError, KeyError):
        return
