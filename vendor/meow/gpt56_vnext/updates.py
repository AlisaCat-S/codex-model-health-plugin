"""Check, stage and hand off explicitly requested official application updates."""
from __future__ import annotations

import asyncio
import hashlib
import os
from pathlib import Path
import re
import tempfile
import subprocess
import sys
import uuid
from urllib.parse import urljoin, urlsplit

import httpx

from . import __version__
from .catalog import REPOSITORY, download_bytes
from .errors import AppError
from .proxies import http_client_options
from .utils import strict_json_loads, utc_now, atomic_write_json
from .installation import metadata, verify, unpack, prepare_environment

MAX_RELEASE_BYTES = 256 * 1024 * 1024


def release_info(value: dict, locale: str, kind='source') -> dict:
    if locale not in {"zh-CN", "en"}:
        raise AppError("unsupported_language")
    tag = value.get("tag_name", "")
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", tag)
    if not match or value.get("draft") or value.get("prerelease"):
        raise AppError("unsupported_release")
    version = ".".join(match.groups())
    available = tuple(map(int, match.groups())) > tuple(map(int, __version__.split(".")))
    suffix = 'windows-x64-portable-' if kind == 'windows-x64-portable' else ''
    name = f"meow-llm-detector-v{version}-{suffix}{locale}.zip"
    asset = next((asset for asset in value.get("assets", []) if asset.get("name") == name), None)
    download = None
    if asset:
        expected = f"https://github.com/{REPOSITORY}/releases/download/{tag}/{name}"
        digest = asset.get("digest", "")
        size = asset.get("size")
        if asset.get("browser_download_url") == expected and isinstance(digest, str) and re.fullmatch(r"sha256:[a-f0-9]{64}", digest) and type(size) is int and 0 < size <= MAX_RELEASE_BYTES:
            download = {"url": expected, "sha256": digest[7:], "size": size, "name": name}
    return {"current_version": __version__, "latest_version": version, "available": available,
            "locale": locale, "checked_at": utc_now(), "release_url": f"https://github.com/{REPOSITORY}/releases/tag/{tag}",
            "notes": str(value.get("body") or "")[:16000], "download": download,
            "installation": "managed_stage_wait_restart", "kind": kind}


class ProgramUpdates:
    def __init__(self, root: Path, store):
        self.root, self.store = root, store
        self._download_lock = asyncio.Lock()
        self.application = Path(__file__).resolve().parent.parent
        self.launch_root = Path(os.environ.get('MEOW_LAUNCH_ROOT', self.application)).resolve()
        self.control = Path(os.environ.get('MEOW_UPDATE_CONTROL', self.root / 'control')).resolve()
        self.operation = None
        try:
            self.kind = metadata(self.application)['kind']
        except AppError:
            self.kind = 'source'
        if not os.environ.get('MEOW_UPDATE_CONTROL') and self.busy():
            self.set_status('failed', message='Interrupted update; current application preserved.')

    async def check(self, locale="zh-CN"):
        try:
            raw = await download_bytes(f"https://api.github.com/repos/{REPOSITORY}/releases/latest", 1024 * 1024)
            info = release_info(strict_json_loads(raw), locale, self.kind)
        except (httpx.HTTPError, AppError) as exc:
            raise AppError("update_check_unavailable", status=502) from exc
        self.store.put_document("program_update", locale, info)
        return info

    def status(self):
        path = self.control / 'status.json'
        return strict_json_loads(path.read_bytes()) if path.exists() else {'stage': 'idle'}

    def busy(self):
        return self.status()['stage'] in ('downloading','preparing','waiting','starting')

    def set_status(self, stage, **extra):
        atomic_write_json(self.control / 'status.json', {'stage':stage, **extra})

    async def install(self, version, locale, state, server):
        if self.operation and not self.operation.done():
            return self.status()
        verify(self.application)
        self.operation = asyncio.create_task(self._install(version, locale, state, server))
        return {'stage':'preparing'}

    async def _install(self, version, locale, state, server):
        saved_schedule = None
        try:
            self.set_status('downloading')
            saved_schedule = state.schedule.status()
            state.schedule.pause()
            archive = await self.download(version, locale)
            self.set_status('preparing')
            stage = self.launch_root / '.meow-versions' / (version + '-' + uuid.uuid4().hex[:8])
            await asyncio.to_thread(unpack, Path(archive['path']), stage, version, self.kind)
            await asyncio.to_thread(prepare_environment, stage, self.kind)
            self.set_status('waiting', message='Waiting for current tasks to finish')
            while state.active:
                await asyncio.sleep(.5)
            if saved_schedule and saved_schedule.get('enabled'):
                self.store.put_document('settings', 'resume_schedule_after_update', {'resume':True})
            info = metadata(self.application)
            job = {'prepared':str(stage),'previous':str(self.application),'previous_version':info['version'],
                   'version':version,'kind':self.kind,'data':str(state.root),'locale':locale,
                   'port':server.server_port,'launch_root':str(self.launch_root)}
            job_path = self.control / 'job.json'; atomic_write_json(job_path,job)
            hidden = {'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {'start_new_session':True}
            subprocess.Popen([sys.executable,'-B','-m','gpt56_vnext.update_runtime','--job',str(job_path)],
                             cwd=self.application,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL,**hidden)
            import threading
            threading.Thread(target=server.shutdown,daemon=True).start()
        except Exception as exc:
            self.set_status('failed',message=exc.code if isinstance(exc,AppError) else 'Update preparation failed; current version preserved.')
            if saved_schedule and saved_schedule.get('enabled'):
                if state.schedule.task:
                    await asyncio.gather(state.schedule.task, return_exceptions=True)
                await state.schedule.resume_after_update()

    async def download(self, version: str, locale="zh-CN"):
        if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+", version):
            raise AppError("invalid_version")
        if locale not in {"zh-CN", "en"}:
            raise AppError("unsupported_language")
        info = self.store.document("program_update", locale)
        if not info or not info["available"] or info["latest_version"] != version or not info["download"]:
            raise AppError("verified_release_asset_unavailable")
        asset = info["download"]
        target = self.root / version / asset["name"]
        async with self._download_lock:
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == asset["sha256"]:
                return {"path": str(target), "verified": True, "installed": False}
            temporary = None
            try:
                async with asyncio.timeout(300), httpx.AsyncClient(timeout=30, **http_client_options(asset["url"])) as client:
                    url = asset["url"]
                    for _ in range(4):
                        parsed = urlsplit(url)
                        if parsed.scheme != "https" or parsed.hostname not in {"github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com"} or parsed.username or parsed.password or parsed.port not in {None, 443}:
                            raise AppError("release_redirect_rejected")
                        async with client.stream("GET", url, headers={"Accept-Encoding": "identity", "User-Agent": "meow-llm-detector/" + __version__}) as response:
                            if response.status_code in {301, 302, 303, 307, 308}:
                                url = urljoin(url, response.headers.get("location", ""))
                                continue
                            if response.status_code != 200:
                                raise AppError("release_download_failed")
                            digest, size = hashlib.sha256(), 0
                            with tempfile.NamedTemporaryFile(dir=target.parent, suffix=".part", delete=False) as handle:
                                temporary = Path(handle.name)
                                async for chunk in response.aiter_bytes():
                                    size += len(chunk)
                                    if size > min(asset["size"], MAX_RELEASE_BYTES):
                                        raise AppError("release_size_mismatch")
                                    digest.update(chunk)
                                    handle.write(chunk)
                                handle.flush()
                                os.fsync(handle.fileno())
                            if size != asset["size"] or digest.hexdigest() != asset["sha256"]:
                                raise AppError("release_hash_mismatch")
                            os.replace(temporary, target)
                            return {"path": str(target), "verified": True, "installed": False}
                    raise AppError("release_redirect_rejected")
            finally:
                if temporary:
                    temporary.unlink(missing_ok=True)
