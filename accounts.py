"""Read only nonsecret metadata from Encounter's local characters.ini."""
import configparser
import io
from pathlib import Path, PureWindowsPath
import uuid


def read_characters(path):
    data = Path(path).read_bytes()
    encodings = ['utf-16'] if data.startswith((b'\xff\xfe', b'\xfe\xff')) else ['utf-8-sig', 'cp1252']
    for encoding in encodings:
        try:
            text = data.decode(encoding)
            break
        except UnicodeError:
            continue
    else:
        raise ValueError('Cannot decode characters.ini')
    parser = configparser.ConfigParser(interpolation=None)
    parser.read_file(io.StringIO(text))
    records = []
    for character in parser.sections():
        fields = parser[character]
        # Do not propagate passwords or emails outside this parser.
        exe = fields.get('filepath', '').strip().strip('"')
        if not exe:
            continue
        records.append({'character': character, 'gw_exe': exe,
                        'dat_path': str(PureWindowsPath(exe).with_name('Gw.dat')),
                        'characters_ini': str(Path(path).resolve()),
                        'section': character, 'crypto_seed': 'Encounter_ReBuilt.au3'})
    if not records:
        raise ValueError('No character sections with FilePath were found.')
    return records


def merge_accounts(config, records):
    existing = {a['character'].casefold(): a for a in config['accounts']}
    for record in records:
        a = existing.get(record['character'].casefold())
        if a is None:
            a = dict(id=uuid.uuid4().hex[:12], team='Team 1', leader=not config['accounts'],
                     rendering=False, profile='', launch_mode='Direct')
            config['accounts'].append(a)
            existing[record['character'].casefold()] = a
        a.update(record)
        a['launch_mode'] = 'Direct'


def validate_install(exe, dat, exists=lambda p: Path(p).is_file()):
    e, d = PureWindowsPath(exe), PureWindowsPath(dat)
    if e.name.casefold() != 'gw.exe' or d.name.casefold() != 'gw.dat':
        raise ValueError('Select Gw.exe and Gw.dat for this account.')
    if str(e.parent).casefold() != str(d.parent).casefold():
        raise ValueError('Gw.exe and Gw.dat must be in the same installation folder.')
    if not exists(exe) or not exists(dat):
        raise ValueError('The selected GW executable or Dat file does not exist.')
