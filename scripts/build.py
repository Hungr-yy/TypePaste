#!/usr/bin/env python3
"""Build on the target OS. Linux uses a portable source + local installer bundle."""
import argparse
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from typepaste import __version__


def build():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skip-tests', action='store_true', help='Only for CI after its separate test job has passed')
    args = parser.parse_args()
    if not args.skip_tests:
        subprocess.run([sys.executable, '-m', 'unittest', '-v', 'test_core.py', 'test_native.py'], cwd=ROOT, check=True)
    output = ROOT / 'dist'
    output.mkdir(exist_ok=True)
    system = platform.system()
    machine = platform.machine().lower()
    name = f'TypePaste-{__version__}-{system.lower()}-{machine}'
    if system == 'Linux':
        archive = output / f'{name}.tar.gz'
        files = [ROOT / file for file in ('stepfwd_sidecar.py', 'install.sh', 'README.md', 'CODEX_HANDOFF.md')]
        files += sorted((ROOT / 'typepaste').rglob('*.py'))
        with tarfile.open(archive, 'w:gz') as bundle:
            for path in files:
                bundle.add(path, arcname=str(Path(name) / path.relative_to(ROOT)))
    elif system in ('Windows', 'Darwin'):
        command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--windowed',
                   '--name', 'TypePaste', '--distpath', str(output), '--workpath', str(ROOT / 'build'),
                   '--specpath', str(ROOT / 'build')]
        if system == 'Windows':
            command += ['--onefile']
        else:
            command += ['--onedir', '--osx-bundle-identifier', 'org.typepaste.sidecar',
                        '--hidden-import', 'ApplicationServices', '--hidden-import', 'Quartz',
                        '--hidden-import', 'AppKit', '--hidden-import', 'CoreFoundation']
        command.append(str(ROOT / 'stepfwd_sidecar.py'))
        subprocess.run(command, cwd=ROOT, check=True)
        archive = output / f'{name}.zip'
        if system == 'Darwin':
            # ditto preserves the .app's symlinks and executable modes.
            subprocess.run(['ditto', '-c', '-k', '--sequesterRsrc', '--keepParent',
                            str(output / 'TypePaste.app'), str(archive)], check=True)
        else:
            with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as bundle:
                bundle.write(output / 'TypePaste.exe', 'TypePaste.exe')
                bundle.write(ROOT / 'README.md', 'README.md')
    else:
        parser.error(f'Unsupported build host: {system}')
    print(f'Built: {archive}')


if __name__ == '__main__':
    build()
