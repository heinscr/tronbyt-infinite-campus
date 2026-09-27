"""Load local installer settings without external dependencies."""
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
REQUIRED = (
    'IC_CAMPUS_URL', 'IC_APP_NAME', 'IC_TIMEZONE', 'IC_USERNAME', 'IC_PASSWORD',
    'TRONBYT_SERVER_URL', 'TRONBYT_DEVICE_ID', 'TRONBYT_USERNAME',
    'TRONBYT_PASSWORD', 'TRONBYT_API_KEY',
)


def load_config(path=None):
    path = Path(path) if path else ROOT / '.env'
    if not path.exists():
        raise ValueError('Copy .env.example to .env and fill in your settings first.')
    config = {}
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        key, separator, value = line.partition('=')
        if not separator:
            raise ValueError('Invalid .env line; expected KEY=value.')
        value = value.strip()
        if value[:1] in ("'", '"'):
            if len(value) < 2 or value[-1] != value[0]:
                raise ValueError('Unclosed quote in .env.')
            value = value[1:-1]
        config[key.strip()] = value
    for key in REQUIRED:
        if not config.get(key):
            raise ValueError(f'Set {key} in .env first.')
    for key, schemes in [('IC_CAMPUS_URL', ('https',)), ('TRONBYT_SERVER_URL', ('http', 'https'))]:
        parsed = urlsplit(config[key])
        if (parsed.scheme not in schemes or not parsed.hostname or parsed.username
                or parsed.password or parsed.query or parsed.fragment):
            raise ValueError(f'{key} must be a base URL without credentials, query, or fragment.')
    config['IC_CAMPUS_URL'] = config['IC_CAMPUS_URL'].rstrip('/') + '/'
    return config
