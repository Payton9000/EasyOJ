"""Notification-area icon for the deployment window, built only on pywin32.

The deployment assistant is normally left running for the whole school day, so
minimising it to the notification area keeps the taskbar clean without stopping
the server. pywin32 is already a project dependency; pystray/Pillow are not, and
adding them would work against the "one script, no extra installs" goal.

Everything here degrades to a no-op when the Win32 APIs are unavailable, so the
GUI still works on a machine without pywin32.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

logger = logging.getLogger(__name__)

try:
    import win32con
    import win32gui

    TRAY_AVAILABLE = True
except ImportError:  # Non-Windows, or pywin32 not installed.
    TRAY_AVAILABLE = False

# Private window messages. WM_USER+20 is the icon callback; +21 asks the Tk thread
# to run a queued callback on the Win32 thread that owns the icon.
_WM_TRAY = 0x0400 + 20
_MENU_OPEN = 1023
_MENU_EXIT = 1024


class TrayIcon:
    """A notification-area icon backed by a hidden message-only window.

    The icon owns its own thread because ``PumpMessages`` blocks; Tk keeps running
    on the main thread untouched.
    """

    def __init__(
        self,
        title: str,
        *,
        on_open: Callable[[], None],
        on_exit: Callable[[], None],
    ) -> None:
        self.title = title[:127] or 'EasyOJ'
        self._on_open = on_open
        self._on_exit = on_exit
        self._hwnd = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._visible = False

    @property
    def available(self) -> bool:
        return TRAY_AVAILABLE

    def start(self) -> bool:
        """Create the hidden window and pump messages on a daemon thread."""
        if not TRAY_AVAILABLE or self._thread is not None:
            return False
        self._thread = threading.Thread(target=self._run, name='EasyOJTray', daemon=True)
        self._thread.start()
        # A short bounded wait: never hang the GUI if window creation fails.
        return self._ready.wait(timeout=3)

    def _run(self) -> None:
        try:
            message_map = {
                _WM_TRAY: self._on_tray_message,
                win32con.WM_COMMAND: self._on_command,
                win32con.WM_DESTROY: self._on_destroy,
            }
            window_class = win32gui.WNDCLASS()
            window_class.hInstance = win32gui.GetModuleHandle(None)
            window_class.lpszClassName = 'EasyOJTrayWindow'
            window_class.lpfnWndProc = message_map
            class_atom = win32gui.RegisterClass(window_class)
            self._hwnd = win32gui.CreateWindow(
                class_atom,
                'EasyOJ',
                win32con.WS_OVERLAPPED | win32con.WS_SYSMENU,
                0,
                0,
                0,
                0,
                0,
                0,
                window_class.hInstance,
                None,
            )
            win32gui.UpdateWindow(self._hwnd)
        except Exception:
            logger.exception('Could not create the tray window')
            self._ready.set()
            return

        self._ready.set()
        try:
            win32gui.PumpMessages()
        except Exception:
            logger.exception('Tray message loop stopped')

    def _icon_handle(self):
        # The stock application icon avoids shipping an .ico and any file lookup.
        return win32gui.LoadIcon(0, win32con.IDI_APPLICATION)

    def show(self, tooltip: str | None = None) -> bool:
        if not TRAY_AVAILABLE or self._hwnd is None:
            return False
        text = (tooltip or self.title)[:127]
        flags = win32gui.NIF_ICON | win32gui.NIF_MESSAGE | win32gui.NIF_TIP
        data = (self._hwnd, 0, flags, _WM_TRAY, self._icon_handle(), text)
        action = win32gui.NIM_MODIFY if self._visible else win32gui.NIM_ADD
        try:
            win32gui.Shell_NotifyIcon(action, data)
            self._visible = True
            return True
        except Exception:
            logger.exception('Could not place the tray icon')
            return False

    def update_tooltip(self, tooltip: str) -> None:
        if self._visible:
            self.show(tooltip)

    def notify(self, title: str, message: str) -> None:
        """Show a balloon; purely informational, so failures are ignored."""
        if not TRAY_AVAILABLE or self._hwnd is None or not self._visible:
            return
        try:
            win32gui.Shell_NotifyIcon(
                win32gui.NIM_MODIFY,
                (
                    self._hwnd,
                    0,
                    win32gui.NIF_INFO,
                    _WM_TRAY,
                    self._icon_handle(),
                    self.title[:127],
                    message[:255],
                    200,
                    title[:63],
                ),
            )
        except Exception:
            logger.debug('Balloon notification failed', exc_info=True)

    def hide(self) -> None:
        if not TRAY_AVAILABLE or self._hwnd is None or not self._visible:
            return
        try:
            win32gui.Shell_NotifyIcon(win32gui.NIM_DELETE, (self._hwnd, 0))
        except Exception:
            logger.debug('Could not remove the tray icon', exc_info=True)
        finally:
            self._visible = False

    def stop(self) -> None:
        self.hide()
        if self._hwnd is not None:
            try:
                win32gui.PostMessage(self._hwnd, win32con.WM_CLOSE, 0, 0)
            except Exception:
                logger.debug('Could not close the tray window', exc_info=True)

    # --- Win32 callbacks -------------------------------------------------

    def _on_tray_message(self, hwnd, msg, wparam, lparam):
        if lparam == win32con.WM_LBUTTONDBLCLK:
            self._safe_call(self._on_open)
        elif lparam == win32con.WM_RBUTTONUP:
            self._show_menu()
        return True

    def _show_menu(self) -> None:
        try:
            menu = win32gui.CreatePopupMenu()
            win32gui.AppendMenu(menu, win32con.MF_STRING, _MENU_OPEN, 'Show EasyOJ deployment')
            win32gui.AppendMenu(menu, win32con.MF_SEPARATOR, 0, '')
            win32gui.AppendMenu(menu, win32con.MF_STRING, _MENU_EXIT, 'Quit assistant')
            position = win32gui.GetCursorPos()
            # Required so the menu closes when the user clicks elsewhere.
            win32gui.SetForegroundWindow(self._hwnd)
            win32gui.TrackPopupMenu(
                menu,
                win32con.TPM_LEFTALIGN | win32con.TPM_RIGHTBUTTON,
                position[0],
                position[1],
                0,
                self._hwnd,
                None,
            )
            win32gui.PostMessage(self._hwnd, win32con.WM_NULL, 0, 0)
        except Exception:
            logger.exception('Could not open the tray menu')

    def _on_command(self, hwnd, msg, wparam, lparam):
        command = win32gui.LOWORD(wparam)
        if command == _MENU_OPEN:
            self._safe_call(self._on_open)
        elif command == _MENU_EXIT:
            self._safe_call(self._on_exit)
        return True

    def _on_destroy(self, hwnd, msg, wparam, lparam):
        self.hide()
        win32gui.PostQuitMessage(0)
        return True

    @staticmethod
    def _safe_call(callback: Callable[[], None]) -> None:
        try:
            callback()
        except Exception:
            logger.exception('Tray callback failed')
