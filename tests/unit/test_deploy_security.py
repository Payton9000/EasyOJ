import json
import re
from pathlib import Path

import pytest

from scripts.deploy.windows.deploy_gui import BoundedDeploymentLog
from scripts.deploy.windows.deploy_gui import DeploymentError
from scripts.deploy.windows.deploy_gui import _wait_for_server
from scripts.deploy.windows.deploy_gui import run_server


def test_wait_for_server_requires_exact_ready_health_marker(monkeypatch):
    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps({'service': 'easyoj', 'status': 'ok', 'version': 999}).encode()

    monkeypatch.setattr(
        'scripts.deploy.windows.deploy_gui.urllib.request.urlopen',
        lambda *args, **kwargs: Response(),
    )
    monkeypatch.setattr('scripts.deploy.windows.deploy_gui.time.sleep', lambda _: None)

    assert _wait_for_server(5000, timeout_seconds=0.01) is False


def test_run_server_captures_bounded_log_tail_on_startup_failure(tmp_path, monkeypatch):
    (tmp_path / 'run.py').write_text('', encoding='utf-8')
    (tmp_path / 'app').mkdir()
    python_path = tmp_path / '.venv' / 'Scripts' / 'python.exe'
    python_path.parent.mkdir(parents=True)
    python_path.write_bytes(b'python')
    captured = {}

    class FakePipe:
        def __iter__(self):
            return iter([b'first error\n', b'last error\n'])

        def close(self):
            pass

    class FakeProcess:
        pid = 42
        stdout = FakePipe()

        def poll(self):
            return None

        def terminate(self):
            captured['terminated'] = True

        def wait(self, timeout=None):
            captured['wait_timeout'] = timeout
            return 1

        def kill(self):
            captured['killed'] = True

    def fake_popen(command, **kwargs):
        captured['command'] = command
        captured['kwargs'] = kwargs
        return FakeProcess()

    monkeypatch.setattr('scripts.deploy.windows.deploy_gui._port_is_open', lambda _: False)
    monkeypatch.setattr('scripts.deploy.windows.deploy_gui._wait_for_server', lambda _: False)
    monkeypatch.setattr('scripts.deploy.windows.deploy_gui.subprocess.Popen', fake_popen)
    monkeypatch.setattr('scripts.deploy.windows.deploy_gui.time.sleep', lambda _: None)

    with pytest.raises(DeploymentError, match='last error'):
        run_server(tmp_path, lambda _: None)

    assert captured['kwargs']['stdout'] is not None
    assert captured['kwargs']['stderr'] is not None
    assert captured['terminated'] is True
    log_path = tmp_path / 'data' / 'logs' / 'production.log'
    assert log_path.is_file()
    assert 'last error' in log_path.read_text(encoding='utf-8')


def test_production_log_rotates_with_a_bounded_size(tmp_path):
    log = BoundedDeploymentLog(tmp_path / 'production.log', max_bytes=1024, backups=2)

    for index in range(20):
        log.append(f'line-{index}-' + ('x' * 200))

    paths = [tmp_path / 'production.log'] + [tmp_path / f'production.log.{i}' for i in (1, 2)]
    assert all(path.stat().st_size <= 1024 for path in paths if path.exists())
    assert (tmp_path / 'production.log').is_file()


def test_toolchain_script_requires_hash_verification_before_execution():
    script = Path('scripts/deploy/windows/setup_toolchain.ps1').read_text(encoding='utf-8')

    assert 'Get-FileHash' in script
    assert 'Assert-Sha256' in script
    assert 'Download-VerifiedFile' in script
    assert 'verified' in script.lower()
    assert 'UseChinaMirror' in script
    assert 'gppPath --version' in script
    assert 'curl.exe' in script
    assert 'function Measure-UrlProbe' in script
    assert 'function Rank-UrlCandidates' in script
    assert 'BytesPerSecond' in script
    downloader = script.split('function Download-VerifiedFile', 1)[1].split('function Expand-Zip', 1)[0]
    assert 'Rank-UrlCandidates' in downloader
    assert 'ghfast.top' in script
    assert 'ghproxy.cn' in script
    assert 'mirrors.huaweicloud.com/python' in script
    assert 'cdn.npmmirror.com' in script
    assert 'www.python.org/ftp/python' in script
    assert 'github.com/brechtsanders/winlibs_mingw' in script


def test_windows_python_embed_pin_matches_current_python_org_zip():
    """python.org re-released python-3.11.9-embed-amd64.zip; the old pin fails checksum."""
    script = Path('scripts/deploy/windows/setup_toolchain.ps1').read_text(encoding='utf-8')
    match = re.search(r'\[string\]\$PythonSha256 = "([0-9a-f]{64})"', script)
    assert match, 'default PythonSha256 is missing'
    # MD5 6d9aa08531d48fcc261ba667e2df17c4 on python.org for the 64-bit embed zip.
    assert match.group(1) == '009d6bf7e3b2ddca3d784fa09f90fe54336d5b60f0e0f305c37f400bf83cfd3b'
    assert '33b448f95fecb7c6f802157dbd5e6b40a2ad9bfc8b95ca634a06ba4073ad1ac0' not in script
