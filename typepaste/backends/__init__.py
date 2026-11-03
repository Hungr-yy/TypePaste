"""Host discovery and validated backend selection; imports stay platform-local."""
from dataclasses import dataclass
import os
import platform
import shutil

from .base import UnavailableBackend

HOST_OS_OPTIONS = ('Auto (recommended)', 'Windows 11', 'macOS', 'Manjaro Linux', 'Ubuntu')


@dataclass(frozen=True)
class Host:
    system: str
    label: str
    session: str = ''
    display: str = ''
    desktop: str = ''


def identify_host_os(system_name, distro_id='', distro_like=''):
    if system_name == 'Windows':
        return 'Windows 11'  # Profile; actual build is checked by the Windows adapter.
    if system_name == 'Darwin':
        return 'macOS'
    if system_name == 'Linux':
        distros = {distro_id.lower(), *distro_like.lower().split()}
        if 'manjaro' in distros:
            return 'Manjaro Linux'
        if 'ubuntu' in distros:
            return 'Ubuntu'
        return 'Linux (other)'
    return f'Other ({system_name})'


def detect_host():
    system = platform.system()
    distro = {}
    if system == 'Linux':
        try:
            distro = platform.freedesktop_os_release()
        except OSError:
            pass
    # WAYLAND_DISPLAY takes precedence even for XWayland processes with DISPLAY.
    session = ('wayland' if os.environ.get('WAYLAND_DISPLAY') else
               os.environ.get('XDG_SESSION_TYPE', '').lower())
    return Host(system, identify_host_os(system, distro.get('ID', ''), distro.get('ID_LIKE', '')),
                session, os.environ.get('DISPLAY', ''), os.environ.get('XDG_CURRENT_DESKTOP', ''))


def choose_backend(selected=HOST_OS_OPTIONS[0], host=None):
    host = host or detect_host()
    if selected not in HOST_OS_OPTIONS:
        return UnavailableBackend('Unknown host profile. Choose Auto.')
    if selected != HOST_OS_OPTIONS[0] and selected != host.label:
        return UnavailableBackend(f'{selected} selected; this host is {host.label}. Choose Auto.')
    try:
        if host.system == 'Linux':
            if host.session == 'wayland':
                if 'kde' not in host.desktop.lower().split(':'):
                    return UnavailableBackend('Wayland currently needs KDE Plasma 6 for safe focus checks. Other desktops can use an X11 session.')
                from .linux_wayland import WaylandBackend
                return WaylandBackend()
            if not host.display:
                return UnavailableBackend('No X11 DISPLAY. Log into an X11 desktop session.')
            executable = shutil.which('xdotool')
            if not executable:
                return UnavailableBackend('Install xdotool to enable the Linux X11 backend.')
            from .linux_x11 import LinuxX11Backend
            return LinuxX11Backend(executable)
        if host.system == 'Windows':
            from .windows import WindowsBackend
            return WindowsBackend()
        if host.system == 'Darwin':
            from .macos import MacOSBackend
            return MacOSBackend()
    except Exception:
        # Native import/loader errors must not prevent the UI from opening.
        return UnavailableBackend(f'{host.label} backend could not load. Check installation requirements.')
    return UnavailableBackend(f'Unsupported host: {host.label}.')
