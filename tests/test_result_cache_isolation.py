"""Cache path isolation regression tests (no real database access)."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_default_cache_location_is_backward_compatible():
    env = os.environ.copy()
    env.pop("DERMASCAN_CACHE_DB_PATH", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    script = """
from pathlib import Path
from skin_cancer.webapp.services import result_cache
assert result_cache.CACHE_DB_PATH == Path.cwd() / 'instance' / 'cache.db'
"""
    result = subprocess.run(
        [sys.executable, "-B", "-c", script],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr


def _probe(tmp_path: Path, *, roundtrip: bool):
    cache_path = tmp_path / "isolated-cache.db"
    env = os.environ.copy()
    env["DERMASCAN_CACHE_DB_PATH"] = str(cache_path)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["CACHE_TEST_ROUNDTRIP"] = "1" if roundtrip else "0"
    script = """
import os
from pathlib import Path
from skin_cancer.webapp.services import result_cache

expected = Path(os.environ['DERMASCAN_CACHE_DB_PATH'])
assert result_cache.CACHE_DB_PATH == expected, (
    'Cache isolation not configured; refusing to touch the repository cache'
)
if os.environ['CACHE_TEST_ROUNDTRIP'] == '1':
    result_cache._get_client = lambda: None
    result_cache.save_cached('qa:isolated', {'safe': True})
    result_cache._mem_cache.clear()
    assert result_cache.get_cached('qa:isolated') == {'safe': True}
    assert expected.exists()
"""
    return subprocess.run(
        [sys.executable, "-B", "-c", script],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=15,
    )


def test_cache_override_is_honored(tmp_path):
    result = _probe(tmp_path, roundtrip=False)
    assert result.returncode == 0, result.stderr


def test_cache_round_trip_stays_in_temporary_directory(tmp_path):
    result = _probe(tmp_path, roundtrip=True)
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "isolated-cache.db").is_file()
