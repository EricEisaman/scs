"""
scs_storage.py - Async asset cache for SCS (Integration 1).

Contract: persistence is ASYNCHRONOUS and INDEPENDENT of GPU resources.

  * localStorage: small preferences ONLY (sync, string-only).
  * IndexedDB: versioned binary asset data (async, structured).
  * Cache source assets or PROCESSED CPU-side representations --
    never live GPU handles (a GPUTexture cannot survive a reload,
    and cannot be serialised).
  * Cache keys carry an explicit schema version + a fingerprint of
    the processing options that produced the bytes. Same inputs
    with different options = different key, never a stale hit.
  * Miss / invalidation / write failure are NORMAL: rendering works
    without persistence. A failed write never throws into the frame.
  * Serialisation + cache population happen OUTSIDE the frame's
    critical path: populate on load / in idle time, never in
    begin_frame() / renderFrame().

Backends: IndexedDB when available, in-memory fallback otherwise.
The fallback has the same API, so code never branches on storage.
"""

import hashlib
import json


def _fingerprint(options):
    """Stable fingerprint of processing options: sorted keys, so
    {'quality': 2, 'format': 'rgba'} always hashes the same way."""
    try:
        canon = json.dumps(options or {}, sort_keys=True, separators=(',', ':'))
    except Exception:
        canon = str(options)
    return hashlib.sha256(canon.encode('utf-8')).hexdigest()[:16]


def cache_key(name, schema_version, options=None):
    """Explicit key: name + schema version + options fingerprint.
    Bumping schema_version invalidates every old entry at once."""
    return '%s@v%s:%s' % (name, schema_version, _fingerprint(options))


def _is_gpu_handle(value):
    """GPU handles are not cacheable. Refuse them loudly at the API
    boundary, not silently later during serialisation."""
    try:
        t = type(value).__name__
        if t in ('GPUTexture', 'GPUBuffer', 'WebGLTexture', 'GPUTextureView'):
            return True
        # Heuristic: objects with a GPU-ish label + no serialisable bytes.
        if hasattr(value, 'createView') and hasattr(value, 'destroy'):
            return True
    except Exception:
        pass
    return False


class PreferenceStore:
    """Small preferences ONLY: localStorage, sync, string-only.
    Never binary data, never per-frame data, never large blobs."""

    def __init__(self, prefix='scs-pref:'):
        self.prefix = prefix
        self._mem = {}

    def _ls(self):
        try:
            from browser import window
            return window.localStorage
        except Exception:
            return None

    def get(self, key, default=None):
        ls = self._ls()
        if ls is not None:
            try:
                v = ls.getItem(self.prefix + key)
                return default if v is None else v
            except Exception:
                pass
        return self._mem.get(key, default)

    def set(self, key, value):
        value = str(value)  # string-only by construction
        ls = self._ls()
        if ls is not None:
            try:
                ls.setItem(self.prefix + key, value)
                return True
            except Exception:
                # Quota / private mode: prefs are best-effort, not fatal.
                pass
        self._mem[key] = value
        return True


class AssetCache:
    """Async asset store. In the browser this is IndexedDB; without it
    (tests, private mode) it is an in-memory store with the same API."""

    def __init__(self, store_name='scs-assets', schema_version=1):
        self.store_name = store_name
        self.schema_version = schema_version
        self._mem = {}  # key -> (bytes, options)
        self._use_idb = False
        try:
            from browser import window
            self._use_idb = getattr(window, 'indexedDB', None) is not None
        except Exception:
            self._use_idb = False

    # -- keying ---------------------------------------------------
    def key(self, name, options=None):
        return cache_key(name, self.schema_version, options)

    # -- synchronous in-memory path (tests + fallback) ------------
    def put_sync(self, name, data, options=None):
        if _is_gpu_handle(data):
            raise TypeError(
                'AssetCache stores CPU-side bytes, not live GPU handles. '
                'Cache the source asset or processed CPU representation.')
        if not isinstance(data, (bytes, bytearray)):
            raise TypeError('AssetCache stores bytes; got %s' % type(data))
        k = self.key(name, options)
        self._mem[k] = (bytes(data), options)
        return k

    def get_sync(self, name, options=None):
        entry = self._mem.get(self.key(name, options))
        return entry[0] if entry is not None else None

    def invalidate_sync(self, name, options=None):
        self._mem.pop(self.key(name, options), None)

    def clear_sync(self):
        self._mem.clear()

    # -- async IndexedDB path (browser) ---------------------------
    def get(self, name, options=None):
        """Returns a Promise resolving to bytes or None (miss).
        Misses are normal, never an exception."""
        if not self._use_idb:
            return _resolved(self.get_sync(name, options))
        return self._idb_get(self.key(name, options))

    def put(self, name, data, options=None):
        """Returns a Promise resolving to the key. Write failures
        resolve to None (not a rejection into the frame) -- the
        caller logs and continues without persistence."""
        if _is_gpu_handle(data):
            raise TypeError('AssetCache stores CPU-side bytes, not GPU handles.')
        if not self._use_idb:
            try:
                return _resolved(self.put_sync(name, data, options))
            except Exception:
                return _resolved(None)
        return self._idb_put(self.key(name, options), data)

    # -- IndexedDB internals (browser only) -----------------------
    def _idb_open(self):
        from browser import window
        db_name = 'scs-' + self.store_name

        def executor(resolve, reject):
            try:
                req = window.indexedDB.open(db_name, 1)

                def on_upgrade(ev):
                    db = ev.target.result
                    try:
                        if not db.objectStoreNames.contains('assets'):
                            db.createObjectStore('assets')
                    except Exception:
                        pass

                req.onupgradeneeded = on_upgrade
                req.onsuccess = lambda ev: resolve(ev.target.result)
                req.onerror = lambda ev: reject(ev)
            except Exception as e:
                reject(e)
        return window.Promise.new(executor)

    def _idb_get(self, key):
        from browser import window

        def executor(resolve, _reject):
            def on_db(db):
                try:
                    tx = db.transaction('assets', 'readonly')
                    req = tx.objectStore('assets').get(key)
                    req.onsuccess = lambda ev: resolve(
                        bytes(ev.target.result) if ev.target.result is not None else None)
                    req.onerror = lambda _ev: resolve(None)  # miss, not error
                except Exception:
                    resolve(None)
            try:
                self._idb_open().then(on_db)
            except Exception:
                resolve(None)
        return window.Promise.new(executor)

    def _idb_put(self, key, data):
        from browser import window

        def executor(resolve, _reject):
            def on_db(db):
                try:
                    tx = db.transaction('assets', 'readwrite')
                    req = tx.objectStore('assets').put(data, key)
                    req.onsuccess = lambda _ev: resolve(key)
                    req.onerror = lambda _ev: resolve(None)  # write failure: normal
                except Exception:
                    resolve(None)
            try:
                self._idb_open().then(on_db)
            except Exception:
                resolve(None)
        return window.Promise.new(executor)


def _resolved(value):
    """Promise.resolve in the browser; plain value in tests."""
    try:
        from browser import window
        return window.Promise.resolve(value)
    except Exception:
        return value


# Module-level singletons: one prefs store, one asset cache.
prefs = PreferenceStore()
assets = AssetCache()
