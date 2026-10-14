"""Configuration and atomic, per-worker INI transport. No credentials stored."""
from __future__ import annotations
import configparser
import json
import os
from pathlib import Path
import time
import uuid

DEFAULT = {
    'autoit': r'C:\Program Files (x86)\AutoIt3\AutoIt3.exe',
    'launcher': '',
    'accounts': [],
    'teams': {'Team 1': {'region': -2, 'language': 0, 'district': 1,
                          'assemble_only': False, 'test_mode': True}},
}


def atomic_text(path: Path, text: str, encoding='utf-8'):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        temp.write_text(text, encoding=encoding)
        # Windows readers (hub and peers) can briefly hold a file without delete sharing.
        deadline = time.monotonic() + 2
        while True:
            try:
                os.replace(temp, path)
                break
            except PermissionError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(.025)
    finally:
        temp.unlink(missing_ok=True)


def write_ini(path: Path, sections: dict):
    import io
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    parser.read_dict({s: {k: str(v) for k, v in kv.items()} for s, kv in sections.items()})
    buf = io.StringIO()
    parser.write(buf, space_around_delimiters=False)
    atomic_text(path, buf.getvalue(), 'utf-16')  # AutoIt's Unicode INI format


def read_status(path: Path, max_age=10):
    try:
        if time.time() - path.stat().st_mtime > max_age:
            return {}
        parser = configparser.ConfigParser(interpolation=None)
        parser.read_string(path.read_text(encoding='utf-16'))
        return dict(parser['Worker'])
    except (OSError, UnicodeError, configparser.Error, KeyError):
        return {}


def validate(config):
    accounts = config['accounts']
    ids, chars = set(), set()
    for a in accounts:
        if not a['id'].isalnum() or a['id'] in ids:
            raise ValueError('Account IDs must be unique letters/numbers.')
        ids.add(a['id'])
        name = a['character'].strip()
        if not 1 <= len(name) <= 19 or any(c in name for c in '\r\n[]=;"'):
            raise ValueError(f'Invalid character name: {name!r}')
        if name.casefold() in chars:
            raise ValueError('Each character may appear only once.')
        chars.add(name.casefold())
        if a['team'] not in config['teams']:
            raise ValueError(f"Unknown team: {a['team']}")
    for team, settings in config['teams'].items():
        members = [a for a in accounts if a['team'] == team]
        if not members:
            continue
        if not 1 <= len(members) <= 8:
            raise ValueError(f'{team}: use 1–8 accounts.')
        if sum(a['leader'] for a in members) != 1:
            raise ValueError(f'{team}: designate exactly one leader.')
        if not 1 <= int(settings['district']) <= 999:
            raise ValueError('District must be 1–999; district 0 is not deterministic.')
        if int(settings['region']) not in (-2, 0, 1, 2, 3, 4):
            raise ValueError('Invalid district region.')
        if int(settings['language']) < 0:
            raise ValueError('Language must be nonnegative.')


def snapshot(config, team, session_dir: Path):
    validate(config)
    members = [a for a in config['accounts'] if a['team'] == team]
    leader = next(a for a in members if a['leader'])
    settings = config['teams'][team]
    sections = {'Team': {
        'Leader': leader['id'], 'Count': len(members), 'Map': 138,
        'Region': settings['region'], 'Language': settings['language'],
        'District': settings['district'], 'AssembleOnly': int(settings['assemble_only']),
        'TestMode': int(settings.get('test_mode', True)),
        'Build': 'OwNS44PTTQ4ORQmE2kxkYhAA',
        'SkeletonModel1': 2392, 'SkeletonModel2': 2393, 'GrenthModel': 1995,
    }}
    for i, a in enumerate(members, 1):
        sections[f'Member{i}'] = {'ID': a['id'], 'Character': a['character'],
                                  'DisableRendering': int(a.get('rendering', False)),
                                  'LaunchDirect': int(a.get('launch_mode') == 'Direct'),
                                  'CharactersINI': a.get('characters_ini', ''),
                                  'Section': a.get('section', a['character']),
                                  'ExePath': a.get('gw_exe', ''),
                                  'DatPath': a.get('dat_path', ''),
                                  'CryptoSeed': a.get('crypto_seed', 'Encounter_ReBuilt.au3')}
    write_ini(session_dir / 'team.ini', sections)
    for a in members:
        write_control(session_dir / (a['id'] + '.command.ini'), mode='run', rendering=a.get('rendering', False))
    return members


def save_config(path, config):
    validate(config)
    atomic_text(path, json.dumps(config, indent=2))


def write_control(path, mode=None, rendering=None, close_game=None, recover=False):
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    if path.exists():
        parser.read(path, encoding='utf-16')
    values = dict(parser['Control']) if parser.has_section('Control') else {'Mode': 'run'}
    if mode is not None:
        values['Mode'] = mode
        values['Recover'] = int(recover)
    if rendering is not None:
        values['DisableRendering'] = int(rendering)
    if close_game is not None:
        values['CloseGame'] = int(close_game)
    write_ini(path, {'Control': values})
