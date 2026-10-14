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
                     rendering=True, profile='', launch_mode='Direct')
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


def migrate_settings(config):
    """Keep imported account identities and order; derive Dat and retire manual roles."""
    from core import DEFAULT
    import copy
    config.setdefault('teams', {})
    config['teams'].setdefault('Team 1', copy.deepcopy(DEFAULT['teams']['Team 1']))
    if config.get('account_setup_revision') != 2:
        for a in config.get('accounts', []):
            a['rendering'] = True
            a['leader'] = False
            if a.get('gw_exe'):
                a['dat_path'] = str(PureWindowsPath(a['gw_exe']).with_name('Gw.dat'))
        config.get('column_widths', {}).pop('launch', None)
        config['account_setup_revision'] = 2
    return config


def protect_password(password):
    """Windows user-bound DPAPI; credentials never enter hub settings."""
    import ctypes
    from ctypes import wintypes
    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.c_void_p)]
    raw = password.encode('utf-8')
    buf = ctypes.create_string_buffer(raw)
    source, target = Blob(len(raw), ctypes.cast(buf, ctypes.c_void_p)), Blob()
    api = ctypes.windll.crypt32.CryptProtectData
    api.argtypes = [ctypes.POINTER(Blob), ctypes.c_wchar_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    api.restype = wintypes.BOOL
    if not api(ctypes.byref(source), 'SkeleHub', None, None, None, 1, ctypes.byref(target)):
        raise OSError('Could not protect account password')
    try:
        return '{DPAPI}' + ctypes.string_at(target.data, target.size).hex()
    finally:
        ctypes.windll.kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        ctypes.windll.kernel32.LocalFree(target.data)


def character_email(path, section):
    try:
        parser = configparser.ConfigParser(interpolation=None)
        raw = Path(path).read_bytes()
        parser.read_string(raw.decode('utf-16' if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig'))
        return parser.get(section, 'Email', fallback='')
    except (OSError, UnicodeError, configparser.Error):
        return ''


def save_character(path, character, email, executable, password='', old_section=None, protector=protect_password):
    from core import atomic_text
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    path = Path(path)
    if path.exists():
        raw = path.read_bytes()
        encoding = 'utf-16' if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig'
        try:
            parser.read_string(raw.decode(encoding))
        except UnicodeError:
            parser.read_string(raw.decode('cp1252'))
    previous = old_section or character
    fields = dict(parser[previous]) if parser.has_section(previous) else {}
    if not password and not fields.get('Pwd'):
        raise ValueError('Enter an account password.')
    fields.update(Email=email, FilePath=executable)
    if password:
        fields['Pwd'] = protector(password)
    if previous != character and parser.has_section(previous):
        parser.remove_section(previous)
    if parser.has_section(character):
        parser.remove_section(character)
    parser[character] = fields
    out = io.StringIO()
    parser.write(out, space_around_delimiters=False)
    atomic_text(path, out.getvalue(), 'utf-16')
