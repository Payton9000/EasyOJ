import ctypes
import logging
import os
import subprocess
import threading
import time
from functools import lru_cache

logger = logging.getLogger(__name__)

IS_WINDOWS = os.name == 'nt'

try:
    import pywintypes
    import win32api
    import win32con
    import win32event
    import win32file
    import win32job
    import win32pipe
    import win32process
    import win32security

    PYWIN32_AVAILABLE = True
except Exception:
    PYWIN32_AVAILABLE = False

try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

if IS_WINDOWS:
    _kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    _advapi32 = ctypes.WinDLL('advapi32', use_last_error=True)
    _userenv = ctypes.WinDLL('userenv', use_last_error=True)

    _LPWSTR = ctypes.c_wchar_p
    _DWORD = ctypes.c_ulong
    _HANDLE = ctypes.c_void_p
    _PSID = ctypes.c_void_p
    _HRESULT = ctypes.c_long

    class _SECURITY_CAPABILITIES(ctypes.Structure):
        _fields_ = [
            ('AppContainerSid', _PSID),
            ('Capabilities', ctypes.c_void_p),
            ('CapabilityCount', _DWORD),
            ('Reserved', _DWORD),
        ]

    class _STARTUPINFO(ctypes.Structure):
        _fields_ = [
            ('cb', _DWORD),
            ('lpReserved', _LPWSTR),
            ('lpDesktop', _LPWSTR),
            ('lpTitle', _LPWSTR),
            ('dwX', _DWORD),
            ('dwY', _DWORD),
            ('dwXSize', _DWORD),
            ('dwYSize', _DWORD),
            ('dwXCountChars', _DWORD),
            ('dwYCountChars', _DWORD),
            ('dwFillAttribute', _DWORD),
            ('dwFlags', _DWORD),
            ('wShowWindow', ctypes.c_ushort),
            ('cbReserved2', ctypes.c_ushort),
            ('lpReserved2', ctypes.c_void_p),
            ('hStdInput', _HANDLE),
            ('hStdOutput', _HANDLE),
            ('hStdError', _HANDLE),
        ]

    class _STARTUPINFOEX(ctypes.Structure):
        _fields_ = [
            ('StartupInfo', _STARTUPINFO),
            ('lpAttributeList', ctypes.c_void_p),
        ]

    class _PROCESS_INFORMATION(ctypes.Structure):
        _fields_ = [
            ('hProcess', _HANDLE),
            ('hThread', _HANDLE),
            ('dwProcessId', _DWORD),
            ('dwThreadId', _DWORD),
        ]

    _CreateAppContainerProfile = _userenv.CreateAppContainerProfile
    _CreateAppContainerProfile.argtypes = [
        _LPWSTR,
        _LPWSTR,
        _LPWSTR,
        ctypes.c_void_p,
        _DWORD,
        ctypes.POINTER(_PSID),
    ]
    _CreateAppContainerProfile.restype = _HRESULT

    _DeriveAppContainerSidFromAppContainerName = _userenv.DeriveAppContainerSidFromAppContainerName
    _DeriveAppContainerSidFromAppContainerName.argtypes = [
        _LPWSTR,
        ctypes.POINTER(_PSID),
    ]
    _DeriveAppContainerSidFromAppContainerName.restype = _HRESULT

    _ConvertSidToStringSidW = _advapi32.ConvertSidToStringSidW
    _ConvertSidToStringSidW.argtypes = [_PSID, ctypes.POINTER(_LPWSTR)]
    _ConvertSidToStringSidW.restype = ctypes.c_bool

    _ConvertStringSidToSidW = _advapi32.ConvertStringSidToSidW
    _ConvertStringSidToSidW.argtypes = [_LPWSTR, ctypes.POINTER(_PSID)]
    _ConvertStringSidToSidW.restype = ctypes.c_bool

    _FreeSid = _advapi32.FreeSid
    _FreeSid.argtypes = [_PSID]
    _FreeSid.restype = _PSID

    _LocalFree = _kernel32.LocalFree
    _LocalFree.argtypes = [ctypes.c_void_p]
    _LocalFree.restype = ctypes.c_void_p

    _InitializeProcThreadAttributeList = _kernel32.InitializeProcThreadAttributeList
    _InitializeProcThreadAttributeList.argtypes = [
        ctypes.c_void_p,
        _DWORD,
        _DWORD,
        ctypes.POINTER(ctypes.c_size_t),
    ]
    _InitializeProcThreadAttributeList.restype = ctypes.c_bool

    _UpdateProcThreadAttribute = _kernel32.UpdateProcThreadAttribute
    _UpdateProcThreadAttribute.argtypes = [
        ctypes.c_void_p,
        _DWORD,
        ctypes.c_size_t,
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    _UpdateProcThreadAttribute.restype = ctypes.c_bool

    _DeleteProcThreadAttributeList = _kernel32.DeleteProcThreadAttributeList
    _DeleteProcThreadAttributeList.argtypes = [ctypes.c_void_p]
    _DeleteProcThreadAttributeList.restype = None

    _CreateProcessW = _kernel32.CreateProcessW
    _CreateProcessW.argtypes = [
        _LPWSTR,
        _LPWSTR,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_bool,
        _DWORD,
        ctypes.c_void_p,
        _LPWSTR,
        ctypes.c_void_p,
        ctypes.POINTER(_PROCESS_INFORMATION),
    ]
    _CreateProcessW.restype = ctypes.c_bool

ERROR_ALREADY_EXISTS = 183
APP_CONTAINER_EXISTS_HRESULT = 0x80070000 | ERROR_ALREADY_EXISTS
PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES = 0x00020009
EXTENDED_STARTUPINFO_PRESENT = 0x00080000
CREATE_NO_WINDOW = 0x08000000
CREATE_UNICODE_ENVIRONMENT = 0x00000400
PROC_THREAD_ATTRIBUTE_JOB_LIST = 0x0002000D

# stdin is delivered as a file inside the workspace rather than through a pipe.
_STDIN_FILENAME = '__easyoj_stdin__'

# Wait slice while polling for process exit, and the two-stage kill grace periods.
WAIT_SLICE_MS = 50
TERMINATE_GRACE_MS = 5000
TERMINATE_FORCE_MS = 1000
READER_JOIN_TIMEOUT_SECONDS = 5


class SandboxError(RuntimeError):
    pass


def _process_tree_usage(pid):
    """Return aggregate RSS in KiB and process count for a sandbox tree."""
    if not PSUTIL_AVAILABLE:
        return 0, 1
    try:
        root = psutil.Process(pid)
        processes = [root, *root.children(recursive=True)]
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return 0, 0

    seen = set()
    total_kb = 0
    count = 0
    for proc in processes:
        proc_pid = getattr(proc, 'pid', None)
        if proc_pid in seen:
            continue
        seen.add(proc_pid)
        try:
            total_kb += int(proc.memory_info().rss / 1024)
            count += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return total_kb, count


class _MemoryMonitor:
    # A psutil sample walks the whole process tree, which on Windows means
    # enumerating every system process. The Job Object enforces the real memory
    # and process ceilings, so this only needs to report peaks.
    DEFAULT_INTERVAL_SECONDS = 0.05

    def __init__(self, pid, limit_mb, on_limit, max_processes=None, interval=None):
        self.pid = pid
        self.limit_kb = limit_mb * 1024
        self.on_limit = on_limit
        self.max_memory_kb = 0
        self.max_processes = max_processes
        self.max_process_count = 0
        self.killed_due_to_memory = False
        self.killed_due_to_process_limit = False
        self.interval = max(0.001, float(interval or self.DEFAULT_INTERVAL_SECONDS))
        self._thread = None
        self._running = False

    def start(self):
        if not PSUTIL_AVAILABLE:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=1)

    def _run(self):
        while self._running:
            mem_kb, process_count = _process_tree_usage(self.pid)
            if process_count == 0:
                return
            self.max_memory_kb = max(self.max_memory_kb, mem_kb)
            self.max_process_count = max(self.max_process_count, process_count)
            if mem_kb > self.limit_kb:
                self.killed_due_to_memory = True
                self.on_limit()
                return
            if self.max_processes and process_count > self.max_processes:
                self.killed_due_to_process_limit = True
                self.on_limit()
                return
            time.sleep(self.interval)


def _workspace_usage(root, max_bytes, max_files):
    """Return (bytes, files, exceeded) without following user-created links.

    A file disappearing between listing and stat is normal — compilers create and
    remove temporary files constantly — so those errors skip the entry. Treating
    every OSError as a violation produced spurious "workspace limit exceeded"
    failures on perfectly ordinary submissions.
    """
    transient = (FileNotFoundError, NotADirectoryError, PermissionError)
    total_bytes = 0
    total_files = 0
    pending = [os.path.abspath(root)]
    max_bytes = max(1, int(max_bytes))
    max_files = max(1, int(max_files))

    while pending:
        current = pending.pop()
        try:
            entries = os.scandir(current)
        except transient:
            continue
        except OSError:
            return total_bytes, total_files, True

        try:
            for entry in entries:
                try:
                    if entry.is_symlink():
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        pending.append(entry.path)
                        continue
                    if entry.name == _STDIN_FILENAME:
                        # Judge-supplied input, not something the submission wrote.
                        continue
                    total_files += 1
                    if total_files > max_files:
                        return total_bytes, total_files, True
                    # Use a fresh stat call; Windows DirEntry metadata can be
                    # cached while a submission is still writing the file.
                    total_bytes += max(0, os.stat(entry.path, follow_symlinks=False).st_size)
                    if total_bytes > max_bytes:
                        return total_bytes, total_files, True
                except transient:
                    total_files = max(0, total_files - 1)
                    continue
                except OSError:
                    return total_bytes, total_files, True
        finally:
            entries.close()

    return total_bytes, total_files, False


class _WorkspaceMonitor:
    # Each pass is a full recursive walk of the workspace. At a 1 ms interval the
    # monitor saturated a core and, because time_used is wall clock, it inflated
    # the measured runtime of the very program it was watching.
    DEFAULT_INTERVAL_SECONDS = 0.025

    def __init__(self, root, max_bytes, max_files, on_limit, interval=None):
        self.root = os.path.abspath(root)
        self.max_bytes = max(1, int(max_bytes))
        self.max_files = max(1, int(max_files))
        self.on_limit = on_limit
        self.interval = max(0.001, float(interval or self.DEFAULT_INTERVAL_SECONDS))
        self.killed_due_to_limit = False
        self.bytes_used = 0
        self.files_used = 0
        self._thread = None
        self._running = False

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=1)

    def _run(self):
        while self._running:
            size, files, exceeded = _workspace_usage(
                self.root,
                self.max_bytes,
                self.max_files,
            )
            self.bytes_used = max(self.bytes_used, size)
            self.files_used = max(self.files_used, files)
            if exceeded:
                self.killed_due_to_limit = True
                try:
                    self.on_limit()
                except Exception:
                    logger.exception('Workspace limit callback failed')
                return
            time.sleep(self.interval)


@lru_cache(maxsize=1)
def _get_appcontainer_sid_string(profile_name):
    if not IS_WINDOWS:
        raise SandboxError('AppContainer requires Windows')

    sid_ptr = _PSID()
    hr = _CreateAppContainerProfile(
        profile_name,
        profile_name,
        'EasyOJ sandbox profile',
        None,
        0,
        ctypes.byref(sid_ptr),
    )
    if (hr & 0xFFFFFFFF) not in (0, APP_CONTAINER_EXISTS_HRESULT):
        raise SandboxError(f'CreateAppContainerProfile failed: 0x{(hr & 0xFFFFFFFF):08X}')

    if not sid_ptr:
        hr = _DeriveAppContainerSidFromAppContainerName(profile_name, ctypes.byref(sid_ptr))
        if hr != 0:
            raise SandboxError(f'DeriveAppContainerSidFromAppContainerName failed: 0x{hr:08X}')

    sid_str_ptr = _LPWSTR()
    if not _ConvertSidToStringSidW(sid_ptr, ctypes.byref(sid_str_ptr)):
        raise SandboxError('ConvertSidToStringSidW failed')

    sid_str = sid_str_ptr.value
    _LocalFree(sid_str_ptr)
    _FreeSid(sid_ptr)
    return sid_str


def _build_security_capabilities(appcontainer_sid_ptr):
    caps = _SECURITY_CAPABILITIES()
    caps.AppContainerSid = appcontainer_sid_ptr
    caps.CapabilityCount = 0
    caps.Capabilities = None
    caps.Reserved = 0
    return caps


def _create_attribute_list(security_capabilities=None, job=None):
    attribute_count = int(security_capabilities is not None) + int(job is not None)
    if not attribute_count:
        raise SandboxError('No process attributes requested')
    size = ctypes.c_size_t(0)
    _InitializeProcThreadAttributeList(None, attribute_count, 0, ctypes.byref(size))
    attr_buf = ctypes.create_string_buffer(size.value)
    attr_list = ctypes.cast(attr_buf, ctypes.c_void_p)
    if not _InitializeProcThreadAttributeList(attr_list, attribute_count, 0, ctypes.byref(size)):
        raise SandboxError('InitializeProcThreadAttributeList failed')

    keepalive = []
    if security_capabilities is not None and not _UpdateProcThreadAttribute(
        attr_list,
        0,
        PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES,
        ctypes.byref(security_capabilities),
        ctypes.sizeof(security_capabilities),
        None,
        None,
    ):
        _DeleteProcThreadAttributeList(attr_list)
        raise SandboxError('UpdateProcThreadAttribute failed')

    if job is not None:
        try:
            job_value = int(job)
        except (TypeError, ValueError):
            job_value = int(getattr(job, 'handle'))
        job_list = (ctypes.c_void_p * 1)(ctypes.c_void_p(job_value))
        if not _UpdateProcThreadAttribute(
            attr_list,
            0,
            PROC_THREAD_ATTRIBUTE_JOB_LIST,
            ctypes.cast(job_list, ctypes.c_void_p),
            ctypes.sizeof(job_list),
            None,
            None,
        ):
            _DeleteProcThreadAttributeList(attr_list)
            raise SandboxError('UpdateProcThreadAttribute for Job Object failed')
        keepalive.append(job_list)

    return attr_list, attr_buf, keepalive


def _sid_ptr_from_string(sid_str):
    sid_ptr = _PSID()
    if not _ConvertStringSidToSidW(sid_str, ctypes.byref(sid_ptr)):
        raise SandboxError('ConvertStringSidToSidW failed')
    return sid_ptr


def _close_handle(handle):
    try:
        win32api.CloseHandle(handle)
    except Exception:
        pass


def _terminate_sandbox_process(job, process_handle, pid=None):
    """Terminate the job and explicitly close the root process race-free."""
    if job:
        try:
            win32job.TerminateJobObject(job, 1)
            return
        except Exception:
            logger.exception('Failed to terminate sandbox job object')
    if process_handle:
        try:
            win32process.TerminateProcess(process_handle, 1)
        except Exception:
            logger.warning('Direct sandbox process termination failed; retrying by PID')
    if pid:
        termination_handle = None
        try:
            termination_handle = win32api.OpenProcess(win32con.PROCESS_TERMINATE, False, pid)
            win32process.TerminateProcess(termination_handle, 1)
        except Exception:
            logger.exception('Failed to terminate sandbox root process by PID')
        finally:
            if termination_handle:
                _close_handle(termination_handle)


def _job_usage(job):
    """Read peak memory and user CPU time accounted to the job.

    Returns an empty mapping when the query is unsupported so callers fall back to
    the sampling monitor instead of failing.
    """
    usage = {}
    if not job:
        return usage
    try:
        extended = win32job.QueryInformationJobObject(
            job, win32job.JobObjectExtendedLimitInformation
        )
        peak_bytes = int(extended.get('PeakJobMemoryUsed', 0) or 0)
        if peak_bytes:
            usage['peak_memory_kb'] = peak_bytes // 1024
        accounting = extended.get('BasicInfo') or {}
        user_time_100ns = int(accounting.get('TotalUserTime', 0) or 0)
        if user_time_100ns:
            usage['user_time_ms'] = user_time_100ns // 10000
    except Exception:
        logger.debug('Job Object usage query failed', exc_info=True)
    if 'user_time_ms' not in usage:
        try:
            accounting = win32job.QueryInformationJobObject(
                job, win32job.JobObjectBasicAccountingInformation
            )
            usage['user_time_ms'] = int(accounting.get('TotalUserTime', 0) or 0) // 10000
        except Exception:
            logger.debug('Job Object accounting query failed', exc_info=True)
    return usage


def _terminate_and_wait(job, process_handle, pid=None):
    """Kill the sandbox and confirm the root process is gone.

    The job terminate is tried first; if the process is still alive after the grace
    period it is killed directly, which also covers a job that never admitted it.
    """
    _terminate_sandbox_process(job, process_handle, pid)
    if win32event.WaitForSingleObject(process_handle, TERMINATE_GRACE_MS) == win32con.WAIT_TIMEOUT:
        _terminate_sandbox_process(None, process_handle, pid)
        win32event.WaitForSingleObject(process_handle, TERMINATE_FORCE_MS)


def _terminate_process_tree(pid):
    """Best-effort cleanup for a process created before Job Object admission."""
    if not pid or not PSUTIL_AVAILABLE:
        return
    try:
        root = psutil.Process(pid)
        children = root.children(recursive=True)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return
    for proc in reversed(children):
        try:
            proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass


def _get_current_user_sid():
    token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
    return win32security.GetTokenInformation(token, win32security.TokenUser)[0]


def _add_access_ace(path, sid, access_mask, inherit=True):
    flags = 0
    if inherit:
        flags = win32con.OBJECT_INHERIT_ACE | win32con.CONTAINER_INHERIT_ACE
    try:
        sd = win32security.GetNamedSecurityInfo(
            path,
            win32security.SE_FILE_OBJECT,
            win32security.DACL_SECURITY_INFORMATION,
        )
        dacl = sd.GetSecurityDescriptorDacl()
    except Exception:
        dacl = None

    if dacl is None:
        dacl = win32security.ACL()
    else:
        sid_string = win32security.ConvertSidToStringSid(sid)
        for index in range(dacl.GetAceCount()):
            ace_header, ace_mask, ace_sid = dacl.GetAce(index)
            ace_type, ace_flags = ace_header
            if (
                ace_type == win32con.ACCESS_ALLOWED_ACE_TYPE
                and ace_flags == flags
                and ace_mask == access_mask
                and win32security.ConvertSidToStringSid(ace_sid) == sid_string
            ):
                return

    dacl.AddAccessAllowedAceEx(win32con.ACL_REVISION, flags, access_mask, sid)
    win32security.SetNamedSecurityInfo(
        path,
        win32security.SE_FILE_OBJECT,
        win32security.DACL_SECURITY_INFORMATION,
        None,
        None,
        dacl,
        None,
    )


def _apply_restrictive_dacl(path, appcontainer_sid):
    import ntsecuritycon

    user_sid = _get_current_user_sid()
    dacl = win32security.ACL()
    inherit_flags = win32con.OBJECT_INHERIT_ACE | win32con.CONTAINER_INHERIT_ACE
    dacl.AddAccessAllowedAceEx(
        win32con.ACL_REVISION, inherit_flags, ntsecuritycon.FILE_ALL_ACCESS, appcontainer_sid
    )
    dacl.AddAccessAllowedAceEx(
        win32con.ACL_REVISION, inherit_flags, ntsecuritycon.FILE_ALL_ACCESS, user_sid
    )
    try:
        system_sid = win32security.LookupAccountName(None, 'SYSTEM')[0]
        dacl.AddAccessAllowedAceEx(
            win32con.ACL_REVISION,
            inherit_flags,
            ntsecuritycon.FILE_ALL_ACCESS,
            system_sid,
        )
    except Exception:
        pass

    win32security.SetNamedSecurityInfo(
        path,
        win32security.SE_FILE_OBJECT,
        win32security.DACL_SECURITY_INFORMATION | win32security.PROTECTED_DACL_SECURITY_INFORMATION,
        None,
        None,
        dacl,
        None,
    )


# Grants on the base/data/temp roots and on the toolchain directories are process
# lifetime facts, not per-testcase work. Re-applying them on every run cost a
# GetNamedSecurityInfo + ACE scan per path per testcase.
_STATIC_GRANT_CACHE = set()
_STATIC_GRANT_LOCK = threading.Lock()


def _static_grant_pending(kind, path, appcontainer_sid):
    try:
        sid_key = win32security.ConvertSidToStringSid(appcontainer_sid)
    except Exception:
        return True, None
    key = (kind, os.path.normcase(os.path.abspath(path)), sid_key)
    with _STATIC_GRANT_LOCK:
        if key in _STATIC_GRANT_CACHE:
            return False, None
    return True, key


def _remember_static_grant(key):
    if key is None:
        return
    with _STATIC_GRANT_LOCK:
        if len(_STATIC_GRANT_CACHE) > 4096:
            _STATIC_GRANT_CACHE.clear()
        _STATIC_GRANT_CACHE.add(key)


def _ensure_traverse_paths(paths, appcontainer_sid):
    for path in paths:
        if not os.path.isdir(path):
            continue
        pending, key = _static_grant_pending('traverse', path, appcontainer_sid)
        if not pending:
            continue

        import ntsecuritycon

        _add_access_ace(path, appcontainer_sid, ntsecuritycon.FILE_TRAVERSE, inherit=True)
        _remember_static_grant(key)


def _grant_read_execute(path, appcontainer_sid):
    if not os.path.exists(path):
        return
    pending, key = _static_grant_pending('read_execute', path, appcontainer_sid)
    if not pending:
        return

    import ntsecuritycon

    try:
        _add_access_ace(
            path,
            appcontainer_sid,
            ntsecuritycon.FILE_GENERIC_READ | ntsecuritycon.FILE_GENERIC_EXECUTE,
            inherit=True,
        )
        _remember_static_grant(key)
    except Exception as e:
        logger.warning('Could not grant read/execute to %s: %s', path, e)


def _create_job_object(time_limit_ms, memory_limit_mb, max_processes):
    job = win32job.CreateJobObject(None, '')
    info = win32job.QueryInformationJobObject(job, win32job.JobObjectExtendedLimitInformation)
    limits = info['BasicLimitInformation']
    limits['LimitFlags'] = (
        win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE | win32job.JOB_OBJECT_LIMIT_ACTIVE_PROCESS
    )
    limits['ActiveProcessLimit'] = max_processes
    if time_limit_ms:
        limits['PerProcessUserTimeLimit'] = int(time_limit_ms * 10000)
        limits['LimitFlags'] |= win32job.JOB_OBJECT_LIMIT_PROCESS_TIME
    if memory_limit_mb:
        # Fail closed: silently skipping the hard memory ceiling would leave only
        # the sampling monitor between a submission and the host's memory.
        memory_flag = getattr(win32job, 'JOB_OBJECT_LIMIT_PROCESS_MEMORY', 0)
        job_memory_flag = getattr(win32job, 'JOB_OBJECT_LIMIT_JOB_MEMORY', 0)
        if not memory_flag and not job_memory_flag:
            _close_handle(job)
            raise SandboxError(
                'Job Object memory limit flags are unavailable in this pywin32 build'
            )
        if memory_flag:
            info['ProcessMemoryLimit'] = int(memory_limit_mb * 1024 * 1024)
            limits['LimitFlags'] |= memory_flag
        if job_memory_flag:
            info['JobMemoryLimit'] = int(memory_limit_mb * 1024 * 1024)
            limits['LimitFlags'] |= job_memory_flag

    win32job.SetInformationJobObject(job, win32job.JobObjectExtendedLimitInformation, info)
    return job


def _verify_process_in_job(job, process_handle, pid=None):
    """Confirm the sandbox process really landed in the job, or kill it.

    Membership is requested via PROC_THREAD_ATTRIBUTE_JOB_LIST at creation time.
    If that silently failed the process would run with no memory ceiling, no CPU
    ceiling, no process cap and no kill-on-close, and TerminateJobObject would not
    reach it either, so an unverified process must never be allowed to continue.
    """
    if not job or not process_handle:
        return
    checker = getattr(win32job, 'IsProcessInJob', None)
    if not callable(checker):
        return
    try:
        in_job = bool(checker(process_handle, job))
    except Exception as exc:
        _terminate_sandbox_process(job, process_handle, pid)
        _terminate_process_tree(pid)
        raise SandboxError(f'IsProcessInJob check failed: {exc}') from exc
    if not in_job:
        _terminate_sandbox_process(job, process_handle, pid)
        _terminate_process_tree(pid)
        raise SandboxError('sandbox process was not admitted to its Job Object')


def _read_handle(handle, max_bytes, output_container, key):
    chunks = []
    total = 0
    truncated = False
    while True:
        try:
            _, data = win32file.ReadFile(handle, 4096)
        except pywintypes.error as e:
            if getattr(e, 'winerror', None) in (109, 232):
                break
            break
        if not data:
            break
        remaining = max_bytes - total
        if remaining <= 0:
            truncated = True
            # Drain the pipe after truncation so a noisy child cannot block.
            continue
        if len(data) > remaining:
            chunks.append(data[:remaining])
            total += remaining
            truncated = True
            continue
        chunks.append(data)
        total += len(data)
    output_container[key] = (b''.join(chunks), truncated)


def build_sandbox_environment(work_dir, compiler_paths, language, base_environment=None):
    """Return the small environment visible to compiler/runtime processes."""
    source = base_environment if base_environment is not None else os.environ
    env = {}
    for name in ('SystemRoot', 'WINDIR', 'ComSpec', 'PATHEXT'):
        if source.get(name):
            env[name] = source[name]

    env['TEMP'] = os.path.abspath(work_dir)
    env['TMP'] = os.path.abspath(work_dir)
    # AppContainer process creation expects LOCALAPPDATA, but exposing the
    # host user's real profile would give submissions an unnecessary path.
    env['LOCALAPPDATA'] = os.path.join(os.path.abspath(work_dir), 'localappdata')
    path_entries = []
    system_root = env.get('SystemRoot') or env.get('WINDIR')
    if system_root:
        path_entries.append(os.path.join(system_root, 'System32'))
    language_tool_keys = {
        'cpp': ('g++',),
        'java': ('javac', 'java'),
        'python': ('python',),
    }.get(language, (language, f'{language}c', f'{language}cc'))
    for tool_key in language_tool_keys:
        executable = compiler_paths.get(tool_key)
        if executable and os.path.isabs(executable):
            path_entries.append(os.path.dirname(os.path.abspath(executable)))
    path_entries.append(os.path.abspath(work_dir))
    env['PATH'] = os.pathsep.join(dict.fromkeys(path_entries))
    if language == 'python':
        env['PYTHONNOUSERSITE'] = '1'
    return env


def _create_pipes():
    """Create the stdout/stderr pipes, cleaning up if a later CreatePipe fails."""
    sa = pywintypes.SECURITY_ATTRIBUTES()
    sa.bInheritHandle = True

    created = []
    try:
        stdout_read, stdout_write = win32pipe.CreatePipe(sa, 0)
        created.extend((stdout_read, stdout_write))
        stderr_read, stderr_write = win32pipe.CreatePipe(sa, 0)
        created.extend((stderr_read, stderr_write))

        win32api.SetHandleInformation(stdout_read, win32con.HANDLE_FLAG_INHERIT, 0)
        win32api.SetHandleInformation(stderr_read, win32con.HANDLE_FLAG_INHERIT, 0)
    except Exception:
        for handle in created:
            _close_handle(handle)
        raise

    return (stdout_read, stdout_write, stderr_read, stderr_write)


def _open_stdin_file(work_dir, input_data):
    """Materialise stdin as an inheritable read handle on a workspace file.

    Writing a large input into an anonymous pipe blocks forever once the ~4 KiB
    buffer fills and the child never reads it, and that write happens before the
    timeout loop starts, so the worker process would hang with no watchdog. A file
    handle has no such backpressure.
    """
    stdin_path = os.path.join(work_dir, _STDIN_FILENAME)
    payload = b''
    if input_data:
        payload = (
            input_data
            if isinstance(input_data, bytes)
            else input_data.encode('utf-8', errors='replace')
        )
    with open(stdin_path, 'wb') as handle:
        handle.write(payload)

    sa = pywintypes.SECURITY_ATTRIBUTES()
    sa.bInheritHandle = True
    return (
        win32file.CreateFile(
            stdin_path,
            win32con.GENERIC_READ,
            win32con.FILE_SHARE_READ | win32con.FILE_SHARE_WRITE,
            sa,
            win32con.OPEN_EXISTING,
            win32con.FILE_ATTRIBUTE_NORMAL,
            None,
        ),
        stdin_path,
    )


def _spawn_appcontainer_process(
    cmd,
    work_dir,
    appcontainer_sid_ptr,
    stdin_read,
    stdout_write,
    stderr_write,
    environment,
    job=None,
):
    startup = _STARTUPINFOEX()
    startup.StartupInfo.cb = ctypes.sizeof(startup)
    startup.StartupInfo.dwFlags = win32con.STARTF_USESTDHANDLES
    startup.StartupInfo.hStdInput = _HANDLE(int(stdin_read))
    startup.StartupInfo.hStdOutput = _HANDLE(int(stdout_write))
    startup.StartupInfo.hStdError = _HANDLE(int(stderr_write))

    sec_caps = _build_security_capabilities(appcontainer_sid_ptr)
    attr_list, attr_buf, keepalive = _create_attribute_list(sec_caps, job=job)
    startup.lpAttributeList = attr_list

    cmdline = subprocess.list2cmdline(cmd)
    creation_flags = EXTENDED_STARTUPINFO_PRESENT | CREATE_NO_WINDOW | CREATE_UNICODE_ENVIRONMENT
    environment_block = ctypes.create_unicode_buffer(
        '\0'.join(f'{key}={value}' for key, value in sorted(environment.items())) + '\0\0'
    )

    try:
        pi = _PROCESS_INFORMATION()
        success = _CreateProcessW(
            None,
            cmdline,
            None,
            None,
            True,
            creation_flags,
            ctypes.cast(environment_block, ctypes.c_void_p),
            work_dir,
            ctypes.byref(startup),
            ctypes.byref(pi),
        )
        if not success:
            error_code = ctypes.get_last_error()
            raise SandboxError(
                f'CreateProcessW failed: {ctypes.FormatError(error_code)} ({error_code})'
            )
        return pi
    finally:
        _DeleteProcThreadAttributeList(attr_list)
        del attr_buf, keepalive


def _spawn_process_with_job(
    cmd,
    work_dir,
    stdin_read,
    stdout_write,
    stderr_write,
    environment,
    job,
):
    """Create a non-AppContainer process with Job Object admission at birth."""
    attr_list, attr_buf, keepalive = _create_attribute_list(job=job)
    try:
        cmdline = subprocess.list2cmdline(cmd)
        startup = win32process.STARTUPINFO()
        startup.dwFlags |= win32con.STARTF_USESTDHANDLES
        startup.hStdInput = stdin_read
        startup.hStdOutput = stdout_write
        startup.hStdError = stderr_write
        startup.lpAttributeList = attr_list
        return win32process.CreateProcess(
            None,
            cmdline,
            None,
            None,
            True,
            win32con.CREATE_NO_WINDOW
            | win32con.CREATE_UNICODE_ENVIRONMENT
            | EXTENDED_STARTUPINFO_PRESENT,
            environment,
            work_dir,
            startup,
        )
    finally:
        _DeleteProcThreadAttributeList(attr_list)
        del attr_buf, keepalive


def _decode_output(data):
    return data.decode('utf-8', errors='replace')


def _resolve_allow_paths(cmd, work_dir, compiler_paths, language, language_config=None):
    allow_paths = [work_dir]
    spec = (language_config or {}).get(language, {})
    default_compiler_keys = {'cpp': 'g++', 'java': 'javac', 'python': 'python'}
    compiler_key = spec.get('compiler_key', default_compiler_keys.get(language, language))
    compiler_exe = compiler_paths.get(compiler_key)
    if compiler_exe and os.path.isabs(compiler_exe):
        bin_dir = os.path.dirname(os.path.abspath(compiler_exe))
        if language in ('cpp', 'java') or spec.get('compiler_key'):
            allow_paths.append(bin_dir)
            if language == 'cpp':
                allow_paths.append(os.path.dirname(bin_dir))
            elif language == 'java':
                allow_paths.append(os.path.abspath(os.path.join(bin_dir, os.pardir)))
    if language == 'java':
        java_exe = compiler_paths.get(spec.get('run_tool_key', 'java'))
        if java_exe and os.path.isabs(java_exe):
            allow_paths.append(os.path.abspath(os.path.join(os.path.dirname(java_exe), os.pardir)))
    if language == 'python' or spec.get('interpreter_key'):
        python_exe = compiler_paths.get(spec.get('interpreter_key', 'python'))
        if python_exe and os.path.isabs(python_exe):
            path_python_dir = os.path.dirname(os.path.abspath(python_exe))
            allow_paths.append(path_python_dir)
            # A venv interpreter reads pyvenv.cfg from its parent directory.
            allow_paths.append(os.path.dirname(path_python_dir))
            # also allow Lib and DLLs
            allow_paths.append(os.path.join(path_python_dir, 'Lib'))
            allow_paths.append(os.path.join(path_python_dir, 'DLLs'))
    return allow_paths


def is_supported():
    return IS_WINDOWS and PYWIN32_AVAILABLE


class SandboxRunner:
    def __init__(self, config):
        self.config = config

    def run(
        self, cmd, work_dir, input_data, time_limit_ms, memory_limit_mb, compiler_paths, language
    ):
        if not is_supported():
            raise SandboxError('Sandbox requires Windows with pywin32 installed')

        profile_name = self.config.get('SANDBOX_PROFILE_NAME', 'EasyOJ.Sandbox')
        strict_appcontainer = self.config.get('SANDBOX_STRICT_APP_CONTAINER', True)
        use_appcontainer = self.config.get('SANDBOX_APP_CONTAINER', True)
        if (
            strict_appcontainer
            and self.config.get('JUDGE_REQUIRE_SANDBOX', True)
            and not use_appcontainer
        ):
            raise SandboxError('AppContainer is required by the sandbox policy')
        max_output = self.config.get('MAX_OUTPUT_SIZE', 64 * 1024)
        max_processes = self.config.get('SANDBOX_MAX_PROCESSES', 8)
        max_workspace_bytes = self.config.get('SANDBOX_MAX_WORKSPACE_BYTES', 64 * 1024 * 1024)
        max_workspace_files = self.config.get('SANDBOX_MAX_WORKSPACE_FILES', 1024)

        if use_appcontainer:
            sid_str = _get_appcontainer_sid_string(profile_name)
            appcontainer_sid = win32security.ConvertStringSidToSid(sid_str)
        else:
            appcontainer_sid = None

        allow_paths = _resolve_allow_paths(
            cmd,
            work_dir,
            compiler_paths,
            language,
            self.config.get('SUPPORTED_LANGUAGES', {}),
        )
        sandbox_environment = build_sandbox_environment(work_dir, compiler_paths, language)
        if use_appcontainer and appcontainer_sid:
            local_appdata = sandbox_environment['LOCALAPPDATA']
            profile_dir_name = ''.join(
                char if char.isalnum() or char in '._-' else '_' for char in profile_name
            )
            profile_dir = os.path.join(local_appdata, 'Packages', profile_dir_name)
            os.makedirs(os.path.join(profile_dir, 'AC', 'Temp'), exist_ok=True)
            os.makedirs(os.path.join(profile_dir, 'AC', 'INetCache'), exist_ok=True)
            # local_appdata lives directly under work_dir, so its parent was the
            # same directory being locked down on the line above.
            _apply_restrictive_dacl(work_dir, appcontainer_sid)
            _apply_restrictive_dacl(local_appdata, appcontainer_sid)
            for writable_dir in (
                profile_dir,
                os.path.join(profile_dir, 'AC'),
                os.path.join(profile_dir, 'AC', 'Temp'),
                os.path.join(profile_dir, 'AC', 'INetCache'),
            ):
                _apply_restrictive_dacl(writable_dir, appcontainer_sid)
            base_dir = os.path.abspath(self.config.get('BASE_DIR', os.getcwd()))
            temp_root = os.path.join(base_dir, 'data', 'temp')
            data_root = os.path.join(base_dir, 'data')
            _ensure_traverse_paths([base_dir, data_root, temp_root], appcontainer_sid)
            for path in allow_paths[1:]:
                _grant_read_execute(path, appcontainer_sid)

        stdout_read, stdout_write, stderr_read, stderr_write = _create_pipes()
        try:
            stdin_read, stdin_path = _open_stdin_file(work_dir, input_data)
        except Exception:
            for handle in (stdout_read, stdout_write, stderr_read, stderr_write):
                _close_handle(handle)
            raise

        sid_ptr = None
        process_handle = None
        thread_handle = None
        job = None
        monitor = None
        workspace_monitor = None
        limit_event = threading.Event()
        timed_out = False
        process_finished = False
        pid = None
        closed_handles = set()

        def close_once(handle):
            """Close a handle at most once.

            A handle value can be recycled by the OS right after the first close,
            so closing again in ``finally`` risks closing an unrelated object.
            """
            if handle is None:
                return
            key = int(handle)
            if key in closed_handles:
                return
            closed_handles.add(key)
            _close_handle(handle)

        try:
            # The Job Object is created before the child.  The job-list
            # startup attribute removes the create/assign race window.
            job = _create_job_object(time_limit_ms, memory_limit_mb, max_processes)
            if use_appcontainer:
                sid_ptr = _sid_ptr_from_string(sid_str)
                pi = _spawn_appcontainer_process(
                    cmd,
                    work_dir,
                    sid_ptr,
                    stdin_read,
                    stdout_write,
                    stderr_write,
                    sandbox_environment,
                    job=job,
                )
                process_handle = pywintypes.HANDLE(int(pi.hProcess))
                thread_handle = pywintypes.HANDLE(int(pi.hThread))
            else:
                process_handle, thread_handle, _, _ = _spawn_process_with_job(
                    cmd,
                    work_dir,
                    stdin_read,
                    stdout_write,
                    stderr_write,
                    sandbox_environment,
                    job,
                )

            pid = win32process.GetProcessId(process_handle)
            _verify_process_in_job(job, process_handle, pid)

            close_once(stdin_read)
            close_once(stdout_write)
            close_once(stderr_write)

            output_container = {}
            stdout_thread = threading.Thread(
                target=_read_handle,
                args=(stdout_read, max_output, output_container, 'stdout'),
                daemon=True,
            )
            stderr_thread = threading.Thread(
                target=_read_handle,
                args=(stderr_read, max_output, output_container, 'stderr'),
                daemon=True,
            )
            stdout_thread.start()
            stderr_thread.start()

            start_ts = time.monotonic()
            workspace_monitor = _WorkspaceMonitor(
                work_dir,
                max_workspace_bytes,
                max_workspace_files,
                limit_event.set,
            )
            workspace_monitor.start()
            monitor = _MemoryMonitor(
                pid,
                memory_limit_mb,
                limit_event.set,
                max_processes=max_processes,
            )
            monitor.start()

            deadline = time.monotonic() + max(0.001, int(time_limit_ms) / 1000)
            wait_code = win32con.WAIT_TIMEOUT
            limit_triggered = False
            while wait_code == win32con.WAIT_TIMEOUT:
                if limit_event.is_set():
                    limit_triggered = True
                    _terminate_and_wait(job, process_handle, pid)
                    break
                remaining_ms = max(1, int((deadline - time.monotonic()) * 1000))
                wait_code = win32event.WaitForSingleObject(
                    process_handle,
                    min(WAIT_SLICE_MS, remaining_ms),
                )
                if limit_event.is_set() and wait_code == win32con.WAIT_TIMEOUT:
                    limit_triggered = True
                    _terminate_and_wait(job, process_handle, pid)
                    break
                if time.monotonic() >= deadline and wait_code == win32con.WAIT_TIMEOUT:
                    break

            if wait_code == win32con.WAIT_TIMEOUT and not limit_triggered:
                timed_out = True
                _terminate_and_wait(job, process_handle, pid)

            process_finished = True

            # The process is gone, so the write ends are closed and the readers see
            # EOF. Joining generously here keeps them from touching a handle that
            # the finally block is about to close.
            stdout_thread.join(timeout=READER_JOIN_TIMEOUT_SECONDS)
            stderr_thread.join(timeout=READER_JOIN_TIMEOUT_SECONDS)

            end_ts = time.monotonic()
            monitor.stop()
            workspace_monitor.stop()

            exit_code = win32process.GetExitCodeProcess(process_handle)
            wall_ms = int((end_ts - start_ts) * 1000)
            job_usage = _job_usage(job)
            memory_used = max(
                int(monitor.max_memory_kb) if monitor else 0,
                job_usage.get('peak_memory_kb', 0),
            )

            stdout_data, stdout_truncated = output_container.get('stdout', (b'', False))
            stderr_data, stderr_truncated = output_container.get('stderr', (b'', False))

            error_text = _decode_output(stderr_data)
            output_text = _decode_output(stdout_data)

            # The job enforces a user-mode CPU limit and a memory ceiling. When it
            # acts, the process simply dies, so exit code alone would report RE for
            # what are really TLE and MLE.
            cpu_limit_hit = time_limit_ms and job_usage.get('user_time_ms', 0) >= int(time_limit_ms)
            memory_limit_hit = memory_limit_mb and job_usage.get('peak_memory_kb', 0) >= int(
                memory_limit_mb * 1024
            )

            if timed_out:
                status = 'TLE'
            elif monitor and monitor.killed_due_to_memory:
                status = 'MLE'
            elif exit_code != 0 and cpu_limit_hit:
                status = 'TLE'
            elif exit_code != 0 and memory_limit_hit:
                status = 'MLE'
            elif monitor and monitor.killed_due_to_process_limit:
                status = 'RE'
                error_text += ' [Process limit exceeded]'
            elif workspace_monitor and workspace_monitor.killed_due_to_limit:
                status = 'OLE'
                error_text += ' [Workspace limit exceeded]'
            elif stdout_truncated or stderr_truncated:
                status = 'OLE'
                error_text += ' [Output limit exceeded]'
            elif exit_code != 0:
                status = 'RE'
                error_text += f' [Exit Code: {exit_code}]'
            else:
                status = 'OK'

            return {
                'status': status,
                'output': output_text,
                'error': error_text,
                'time_used': wall_ms,
                'memory_used': memory_used,
                'workspace_bytes': workspace_monitor.bytes_used if workspace_monitor else 0,
                'workspace_files': workspace_monitor.files_used if workspace_monitor else 0,
            }
        except SandboxError as e:
            logger.error('Sandbox error: %s', e)
            return {
                'status': 'SystemError',
                'output': '',
                'error': str(e),
                'time_used': 0,
                'memory_used': 0,
            }
        except Exception as e:
            logger.error('Sandbox execution failure: %s', e)
            if strict_appcontainer:
                return {
                    'status': 'SystemError',
                    'output': '',
                    'error': str(e),
                    'time_used': 0,
                    'memory_used': 0,
                }
            raise
        finally:
            if monitor:
                monitor.stop()
            if workspace_monitor:
                workspace_monitor.stop()
            if process_handle and not process_finished:
                _terminate_sandbox_process(job, process_handle, pid)
                _terminate_process_tree(pid)
            if job:
                close_once(job)
            close_once(stdin_read)
            close_once(stdout_write)
            close_once(stderr_write)
            close_once(stdout_read)
            close_once(stderr_read)
            if process_handle:
                close_once(process_handle)
            if thread_handle:
                close_once(thread_handle)
            if sid_ptr:
                _LocalFree(sid_ptr)
            try:
                os.remove(stdin_path)
            except OSError:
                pass
