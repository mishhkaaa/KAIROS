#!/usr/bin/env python3
"""orgfs: the organization's knowledge as a real filesystem at /org, served by the KAIROS gateway (FUSE, fusepy).

    ls /org/finance                   folders and documents, as in the console's Knowledge app
    cat /org/finance/apollo-budget.md a document: its frontmatter (trust, owner, source) and body
    ls "/org/.search/apollo overrun"  hybrid search: the hits, as links to the documents
    cat /org/.kairos/status           the kernel, and who this machine is signed in as
    cp notes.md /org/uploads/         a new document: converted, indexed, searchable by agents
    ls /org/mnt                       folders of this computer mounted with `kairos mount`

Documents are read-only here: agents and people change knowledge through governed paths (uploads, mounts, connector
sync), never by editing files in place. Listings are cached for a few seconds.
"""
from __future__ import annotations

import errno
import json
import logging
import os
import stat
import sys
import threading
import time
from typing import Any

try:  # Debian's python3-fusepy installs the module as `fusepy`; pip's fusepy as `fuse`
    from fusepy import FUSE, FuseOSError, LoggingMixIn, Operations
except ImportError:
    from fuse import FUSE, FuseOSError, LoggingMixIn, Operations

sys.path.insert(0, "/opt/kairos")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kairosos as m  # noqa: E402

log = logging.getLogger("orgfs")
TTL = 5.0
READ_ONLY_TOP = {"mnt", ".search", ".kairos"}


class Cache:
    def __init__(self) -> None:
        self._d: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str, fetch, ttl: float = TTL) -> Any:
        with self._lock:
            hit = self._d.get(key)
            if hit and time.monotonic() - hit[0] < ttl:
                return hit[1]
        value = fetch()
        with self._lock:
            self._d[key] = (time.monotonic(), value)
        return value

    def drop(self, prefix: str = "") -> None:
        with self._lock:
            for k in [k for k in self._d if k.startswith(prefix)]:
                del self._d[k]


class OrgFS(LoggingMixIn, Operations):
    def __init__(self) -> None:
        self.cache = Cache()
        # Run by systemd as root (so it may allow other users in); files show as the desktop user's.
        owner = os.environ.get("ORGFS_OWNER")
        if owner:
            import pwd

            rec = pwd.getpwnam(owner)
            self.uid, self.gid = rec.pw_uid, rec.pw_gid
        else:
            self.uid, self.gid = os.getuid(), os.getgid()
        self.pending: dict[str, bytearray] = {}  # files being written, by fs path
        self.new_dirs: set[str] = set()
        self.t0 = time.time()

    # ------------------------------------------------------------------ gateway
    def _listing(self, org_path: str) -> dict[str, dict[str, Any]]:
        def fetch():
            try:
                res = m.call("GET", "/knowledge/tree" + m.q(path=org_path), timeout=10)
            except m.GatewayError as e:
                if e.status == 404:
                    return {}
                raise FuseOSError(errno.EHOSTDOWN if e.status == 0 else errno.EACCES) from None
            out = {}
            for entry in res.get("entries", []):
                name = entry["path"].rsplit("/", 1)[-1]
                out[name if entry.get("is_dir") else f"{name}.md"] = entry
            return out

        return self.cache.get(f"tree:{org_path}", fetch)

    def _document(self, org_path: str) -> bytes:
        def fetch():
            try:
                return m.render(m.call("GET", "/knowledge/object" + m.q(path=org_path), timeout=10)).encode()
            except m.GatewayError as e:
                raise FuseOSError(errno.ENOENT if e.status == 404 else errno.EIO) from None

        return self.cache.get(f"obj:{org_path}", fetch, ttl=TTL * 2)

    def _search(self, text: str) -> dict[str, str]:
        def fetch():
            try:
                hits = m.call("GET", "/knowledge/search" + m.q(q=text, top_k=10), timeout=30).get("hits", [])
            except m.GatewayError:
                return {}
            out: dict[str, str] = {}
            for i, h in enumerate(hits, 1):
                out[f"{i:02d}-{h['path'].rsplit('/', 1)[-1]}.md"] = "/org" + h["path"][4:] + ".md"
            return out

        return self.cache.get(f"search:{text}", fetch, ttl=60)

    def _special(self, name: str) -> bytes:
        def fetch():
            try:
                if name == "status":
                    s = m.call("GET", "/system/status", timeout=5)
                    lines = [f"kernel {s['version']} (contract {s['contract_version']}), {'ready' if s['ready'] else 'starting'}",
                             *[f"  {'ok ' if x['ok'] else 'DOWN'} {x['component']:<12} {x.get('mode', '')}" for x in s["components"]]]
                    return ("\n".join(lines) + "\n").encode()
                me = m.call("GET", "/auth/me", timeout=5)
                return (json.dumps(me, indent=2) + "\n").encode()
            except m.GatewayError as e:
                return f"{e.message}\n".encode()

        return self.cache.get(f"special:{name}", fetch)

    # ------------------------------------------------------------------ paths
    @staticmethod
    def _org(path: str) -> str:
        """/finance/apollo-budget.md -> /org/finance/apollo-budget; / -> /org."""
        p = path[:-3] if path.endswith(".md") else path
        return "/org" + (p if p != "/" else "")

    def _kind(self, path: str) -> tuple[str, Any]:
        """('dir'|'file'|'link'|'pending', detail) or ENOENT."""
        if path in ("/", "/.search", "/.kairos", "/uploads") or path in self.new_dirs:
            return "dir", None
        if path in self.pending:
            return "pending", None
        parts = path.strip("/").split("/")
        if parts[0] == ".kairos" and len(parts) == 2 and parts[1] in ("status", "whoami"):
            return "file", self._special(parts[1])
        if parts[0] == ".search":
            if len(parts) == 2:
                return "dir", None
            if len(parts) == 3:
                target = self._search(parts[1]).get(parts[2])
                if target:
                    return "link", target
            raise FuseOSError(errno.ENOENT)
        parent = "/" + "/".join(parts[:-1]) if len(parts) > 1 else "/"
        entry = self._listing(self._org(parent)).get(parts[-1])
        if not entry:
            raise FuseOSError(errno.ENOENT)
        return ("dir", entry) if entry.get("is_dir") else ("file", None)

    # ------------------------------------------------------------------ reading
    def getattr(self, path: str, fh: int | None = None) -> dict[str, Any]:
        kind, detail = self._kind(path)
        base = {"st_uid": self.uid, "st_gid": self.gid, "st_atime": self.t0, "st_mtime": self.t0, "st_ctime": self.t0}
        if kind == "dir":
            return {**base, "st_mode": stat.S_IFDIR | 0o755, "st_nlink": 2}
        if kind == "link":
            return {**base, "st_mode": stat.S_IFLNK | 0o777, "st_nlink": 1, "st_size": len(detail)}
        if kind == "pending":
            return {**base, "st_mode": stat.S_IFREG | 0o644, "st_nlink": 1, "st_size": len(self.pending[path]), "st_mtime": time.time()}
        data = detail if detail is not None else self._document(self._org(path))
        return {**base, "st_mode": stat.S_IFREG | 0o444, "st_nlink": 1, "st_size": len(data)}

    def readdir(self, path: str, fh: int) -> list[str]:
        names = [".", ".."]
        if path == "/.search":
            return names
        if path == "/.kairos":
            return [*names, "status", "whoami"]
        if path.startswith("/.search/"):
            return [*names, *self._search(path.split("/", 2)[2])]
        names += list(self._listing(self._org(path)))
        if path == "/":
            names += ["uploads", ".search", ".kairos"]  # uploads: the drop folder, there before the first upload
        names += [p.rsplit("/", 1)[-1] for p in (*self.pending, *self.new_dirs) if p.rsplit("/", 1)[0] == path.rstrip("/")]
        return list(dict.fromkeys(names))

    def readlink(self, path: str) -> str:
        kind, target = self._kind(path)
        if kind != "link":
            raise FuseOSError(errno.EINVAL)
        return target

    def read(self, path: str, size: int, offset: int, fh: int) -> bytes:
        if path in self.pending:
            return bytes(self.pending[path][offset:offset + size])
        kind, detail = self._kind(path)
        if kind != "file":
            raise FuseOSError(errno.EISDIR)
        data = detail if detail is not None else self._document(self._org(path))
        return data[offset:offset + size]

    # ------------------------------------------------------------------ adding knowledge
    def _writable_dir(self, path: str) -> None:
        top = path.strip("/").split("/")[0]
        if top in READ_ONLY_TOP or path == "/":
            raise FuseOSError(errno.EACCES)

    def create(self, path: str, mode: int, fi=None) -> int:
        self._writable_dir(path)
        self.pending[path] = bytearray()
        return 0

    def open(self, path: str, flags: int) -> int:
        if flags & (os.O_WRONLY | os.O_RDWR) and path not in self.pending:
            raise FuseOSError(errno.EACCES)  # documents change through governed paths, not in place
        return 0

    def write(self, path: str, data: bytes, offset: int, fh: int) -> int:
        buf = self.pending.get(path)
        if buf is None:
            raise FuseOSError(errno.EACCES)
        buf[offset:offset + len(data)] = data
        return len(data)

    def truncate(self, path: str, length: int, fh: int | None = None) -> None:
        if path not in self.pending:
            raise FuseOSError(errno.EACCES)
        del self.pending[path][length:]

    def release(self, path: str, fh: int) -> int:
        data = self.pending.pop(path, None)
        if data is None:
            return 0
        folder, name = path.rsplit("/", 1)
        try:
            res = m.upload([(name, bytes(data))], self._org(folder or "/"))
            log.info("uploaded %s -> %s", path, res.get("created") or res.get("updated") or res.get("skipped"))
        except m.GatewayError as e:
            log.warning("upload of %s failed: %s", path, e.message)
        self.cache.drop("tree:")
        return 0

    def mkdir(self, path: str, mode: int) -> None:
        self._writable_dir(path)
        self.new_dirs.add(path)

    def unlink(self, path: str) -> None:
        if path in self.pending:
            del self.pending[path]
            return
        raise FuseOSError(errno.EACCES)

    def chmod(self, path: str, mode: int) -> int:
        return 0

    def chown(self, path: str, uid: int, gid: int) -> int:
        return 0

    def utimens(self, path: str, times=None) -> int:
        return 0

    def statfs(self, path: str) -> dict[str, int]:
        return {"f_bsize": 4096, "f_frsize": 4096, "f_blocks": 1 << 20, "f_bfree": 1 << 19, "f_bavail": 1 << 19, "f_namemax": 255}


def main() -> None:
    mountpoint = sys.argv[1] if len(sys.argv) > 1 else "/org"
    logging.basicConfig(level=logging.INFO, format="orgfs %(levelname)s %(message)s")
    log.info("serving %s from %s", mountpoint, m.gateway_url())
    FUSE(OrgFS(), mountpoint, foreground=True, nothreads=False, allow_other=os.getuid() == 0, fsname="kairos-org")


if __name__ == "__main__":
    main()
