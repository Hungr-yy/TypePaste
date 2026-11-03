"""Only geometry, typing speed and host profile may be persisted."""
import json
import os
from pathlib import Path
import sys
import tempfile


def preference_path():
    if sys.platform == 'win32':
        root = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData' / 'Local')))
    elif sys.platform == 'darwin':
        root = Path.home() / 'Library' / 'Application Support'
    else:
        root = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config')))
    return root / 'stepfwd-typepaste' / 'preferences.json'


def load_prefs(path=None):
    try:
        data = json.loads((path or preference_path()).read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_prefs(values, path=None):
    path = path or preference_path()
    data = {key: values[key] for key in ('geometry', 'delay_ms', 'host_os') if key in values}
    temporary = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(data, stream, indent=2)
        temporary.replace(path)
        return True
    except (OSError, ValueError, TypeError):
        return False
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
