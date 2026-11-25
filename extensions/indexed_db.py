# extensions/indexed_db.py - App-agnostic local high scores on top of IndexedDB.
# Without modifying any other extension. Model-only, never imports scs, never draws.
# Local players only for now. No network, no server, no sharing, no CORS.
# EVENT-DRIVEN ONLY - No timeouts, no setTimeout, no polling.
# IndexedDB work is driven by onsuccess, onerror, onupgradeneeded events.
# Every IndexedDB call also mirrors to localStorage, so sync reads stay fresh
# and the game still works if IndexedDB is blocked or unavailable.
# App-agnostic usage:
#   from extensions.indexed_db import LocalStore
#   store = LocalStore()
#   scores = store.top_scores_sync("mygame", limit=5)
#   store.add_score_sync("mygame", "local", 1200, level=2)
# Async usage:
#   scores = await store.top_scores("mygame", limit=5)
#   await store.add_score("mygame", "local", 1200, level=2)

try:
    from browser import window as _window
    from browser import aio as _aio
    HAS_BROWSER = True
except Exception:
    _window = None
    _aio = None
    HAS_BROWSER = False

import json

DEFAULT_DB = "scs_local"
DEFAULT_STORE = "high_scores"
DEFAULT_PLAYER = "local"
MAX_SCORES = 10

def _now_iso():
    try:
        if HAS_BROWSER and _window is not None:
            d = _window.Date.new()
            return d.toISOString()
    except Exception:
        pass
    return ""

def _ls_key(db_name, store_name, key):
    return db_name + ":" + store_name + ":" + str(key)

def _ls_get(db_name, store_name, key, default=None):
    try:
        if HAS_BROWSER and _window is not None:
            ls = getattr(_window, 'localStorage', None)
            if ls is not None:
                raw = ls.getItem(_ls_key(db_name, store_name, key))
                if raw is None:
                    return default
                try:
                    return json.loads(raw)
                except Exception:
                    return raw
    except Exception:
        pass
    return default

def _ls_put(db_name, store_name, key, value):
    try:
        if HAS_BROWSER and _window is not None:
            ls = getattr(_window, 'localStorage', None)
            if ls is not None:
                try:
                    raw = json.dumps(value)
                except Exception:
                    raw = str(value)
                ls.setItem(_ls_key(db_name, store_name, key), raw)
                return True
    except Exception:
        pass
    return False

def _ls_delete(db_name, store_name, key):
    try:
        if HAS_BROWSER and _window is not None:
            ls = getattr(_window, 'localStorage', None)
            if ls is not None:
                ls.removeItem(_ls_key(db_name, store_name, key))
                return True
    except Exception:
        pass
    return False

def _sort_scores(scores):
    try:
        return sorted(scores, key=lambda s: s.get('score', 0) if isinstance(s, dict) else 0, reverse=True)
    except Exception:
        return scores

class LocalStore:
    # App-agnostic local store. One store can hold many apps, keyed by app_id.
    # Scores are kept per app_id, per player, local only.
    def __init__(self, db_name=DEFAULT_DB, store_name=DEFAULT_STORE):
        self.db_name = db_name
        self.store_name = store_name
        self._memory = {}
        self._db = None
        self._db_failed = False

    # Sync helpers, localStorage mirror only, safe to call from onAppStart.
    def get_sync(self, key, default=None):
        if key in self._memory:
            return self._memory[key]
        v = _ls_get(self.db_name, self.store_name, key, None)
        if v is not None:
            self._memory[key] = v
            return v
        return default

    def put_sync(self, key, value):
        self._memory[key] = value
        _ls_put(self.db_name, self.store_name, key, value)
        # Also try async IndexedDB in background if aio is available, never block.
        try:
            if HAS_BROWSER and _aio is not None:
                _aio.run(self.put(key, value))
        except Exception:
            pass
        return True

    def delete_sync(self, key):
        try:
            del self._memory[key]
        except Exception:
            pass
        _ls_delete(self.db_name, self.store_name, key)
        try:
            if HAS_BROWSER and _aio is not None:
                _aio.run(self.delete(key))
        except Exception:
            pass
        return True

    def top_scores_sync(self, app_id, limit=5, player=None):
        try:
            raw = self.get_sync("scores:" + str(app_id), [])
            if not isinstance(raw, list):
                raw = []
            if player is not None:
                raw = [s for s in raw if isinstance(s, dict) and s.get('player', '') == player]
            raw = _sort_scores(raw)
            return raw[:limit]
        except Exception:
            return []

    def best_score_sync(self, app_id, player=None):
        try:
            top = self.top_scores_sync(app_id, limit=1, player=player)
            if top:
                return int(top[0].get('score', 0))
            return 0
        except Exception:
            return 0

    def add_score_sync(self, app_id, player, score, level=None, extra=None):
        try:
            entry = {'player': str(player), 'score': int(score), 'app': str(app_id), 'date': _now_iso()}
            if level is not None:
                entry['level'] = level
            if extra is not None:
                entry['extra'] = extra
            raw = self.get_sync("scores:" + str(app_id), [])
            if not isinstance(raw, list):
                raw = []
            raw.append(entry)
            raw = _sort_scores(raw)[:MAX_SCORES]
            self.put_sync("scores:" + str(app_id), raw)
            # Also keep a simple best key for fast sync reads.
            best = 0
            if raw:
                best = int(raw[0].get('score', 0))
            self.put_sync("best:" + str(app_id), best)
            if player is not None:
                pbest = self.best_score_sync(app_id, player=player)
                self.put_sync("best:" + str(app_id) + ":" + str(player), pbest)
            return raw
        except Exception:
            return []

    def clear_scores_sync(self, app_id):
        try:
            self.put_sync("scores:" + str(app_id), [])
            self.put_sync("best:" + str(app_id), 0)
            return True
        except Exception:
            return False

    # Async IndexedDB helpers, event driven.
    def _idb(self):
        try:
            if not HAS_BROWSER or _window is None:
                return None
            idb = getattr(_window, 'indexedDB', None)
            if idb is None:
                idb = getattr(_window, 'webkitIndexedDB', None)
            return idb
        except Exception:
            return None

    async def _open_db(self):
        # Open or create DB, onupgradeneeded creates the object store.
        if self._db is not None:
            return self._db
        if self._db_failed:
            return None
        idb = self._idb()
        if idb is None:
            return None
        try:
            store_name = self.store_name
            def executor(resolve, reject):
                try:
                    req = idb.open(self.db_name, 1)
                    def on_upgrade(e):
                        try:
                            db = e.target.result
                            if store_name not in db.objectStoreNames:
                                db.createObjectStore(store_name)
                        except Exception as ex:
                            pass
                    def on_success(e):
                        try:
                            resolve(e.target.result)
                        except Exception as ex:
                            reject(ex)
                    def on_error(e):
                        try:
                            reject(e)
                        except Exception:
                            reject(e)
                    req.onupgradeneeded = on_upgrade
                    req.onsuccess = on_success
                    req.onerror = on_error
                except Exception as ex:
                    reject(ex)
            db = await _window.Promise.new(executor)
            self._db = db
            return db
        except Exception:
            self._db_failed = True
            return None

    async def _idb_request(self, mode, fn):
        # Run fn(store) -> IDBRequest, await it via Promise, event driven.
        try:
            db = await self._open_db()
            if db is None:
                return None
            tx = db.transaction(self.store_name, mode)
            store = tx.objectStore(self.store_name)
            req = fn(store)
            if req is None:
                return None
            def executor(resolve, reject):
                def on_success(e):
                    try:
                        resolve(e.target.result)
                    except Exception as ex:
                        reject(ex)
                def on_error(e):
                    try:
                        reject(e)
                    except Exception:
                        reject(e)
                try:
                    req.onsuccess = on_success
                    req.onerror = on_error
                except Exception as ex:
                    reject(ex)
            result = await _window.Promise.new(executor)
            return result
        except Exception:
            return None

    async def get(self, key, default=None):
        try:
            result = await self._idb_request("readonly", lambda store: store.get(str(key)))
            if result is not None:
                try:
                    val = result
                    if isinstance(val, dict) and 'value' in val:
                        val = val['value']
                    self._memory[key] = val
                    return val
                except Exception:
                    return result
        except Exception:
            pass
        return self.get_sync(key, default)

    async def put(self, key, value):
        # Always mirror to localStorage first so sync reads stay correct.
        self._memory[key] = value
        _ls_put(self.db_name, self.store_name, key, value)
        try:
            payload = {'key': str(key), 'value': value}
            await self._idb_request("readwrite", lambda store: store.put(payload, str(key)))
        except Exception:
            pass
        return True

    async def delete(self, key):
        try:
            del self._memory[key]
        except Exception:
            pass
        _ls_delete(self.db_name, self.store_name, key)
        try:
            await self._idb_request("readwrite", lambda store: store.delete(str(key)))
        except Exception:
            pass
        return True

    async def get_all(self):
        try:
            result = await self._idb_request("readonly", lambda store: store.getAll())
            if isinstance(result, list) and len(result) > 0:
                out = {}
                for item in result:
                    try:
                        if isinstance(item, dict) and 'key' in item:
                            out[item['key']] = item.get('value', item)
                    except Exception:
                        pass
                if out:
                    return out
        except Exception:
            pass
        # Fallback: memory only, localStorage keys are not enumerable reliably here.
        return dict(self._memory)

    async def top_scores(self, app_id, limit=5, player=None):
        try:
            raw = await self.get("scores:" + str(app_id), [])
            if raw is None:
                raw = self.get_sync("scores:" + str(app_id), [])
            if not isinstance(raw, list):
                raw = []
            if player is not None:
                raw = [s for s in raw if isinstance(s, dict) and s.get('player', '') == player]
            raw = _sort_scores(raw)
            return raw[:limit]
        except Exception:
            return self.top_scores_sync(app_id, limit=limit, player=player)

    async def best_score(self, app_id, player=None):
        try:
            top = await self.top_scores(app_id, limit=1, player=player)
            if top:
                return int(top[0].get('score', 0))
            return 0
        except Exception:
            return self.best_score_sync(app_id, player=player)

    async def add_score(self, app_id, player, score, level=None, extra=None):
        try:
            entry = {'player': str(player), 'score': int(score), 'app': str(app_id), 'date': _now_iso()}
            if level is not None:
                entry['level'] = level
            if extra is not None:
                entry['extra'] = extra
            raw = await self.get("scores:" + str(app_id), [])
            if raw is None:
                raw = []
            if not isinstance(raw, list):
                raw = []
            raw.append(entry)
            raw = _sort_scores(raw)[:MAX_SCORES]
            await self.put("scores:" + str(app_id), raw)
            if raw:
                await self.put("best:" + str(app_id), int(raw[0].get('score', 0)))
            return raw
        except Exception:
            return self.add_score_sync(app_id, player, score, level=level, extra=extra)

    async def clear_scores(self, app_id):
        try:
            await self.put("scores:" + str(app_id), [])
            await self.put("best:" + str(app_id), 0)
            return True
        except Exception:
            return self.clear_scores_sync(app_id)

# Module-level default store, one per app process.
_default_store = None
def get_store(db_name=DEFAULT_DB, store_name=DEFAULT_STORE):
    global _default_store
    if _default_store is None:
        _default_store = LocalStore(db_name=db_name, store_name=store_name)
    return _default_store

def get_store_for(app_id, db_name=DEFAULT_DB):
    # App-agnostic: same store object, scores are namespaced by app_id.
    return get_store(db_name=db_name, store_name=DEFAULT_STORE)

# Convenience sync helpers, easiest for onAppStart.
def get_high_scores_sync(app_id, limit=5, player=None):
    return get_store().top_scores_sync(app_id, limit=limit, player=player)

def add_high_score_sync(app_id, player, score, level=None, extra=None):
    return get_store().add_score_sync(app_id, player, score, level=level, extra=extra)

def get_best_sync(app_id, player=None):
    return get_store().best_score_sync(app_id, player=player)

def clear_high_scores_sync(app_id):
    return get_store().clear_scores_sync(app_id)

# Convenience async helpers.
async def get_high_scores(app_id, limit=5, player=None):
    return await get_store().top_scores(app_id, limit=limit, player=player)

async def add_high_score(app_id, player, score, level=None, extra=None):
    return await get_store().add_score(app_id, player, score, level=level, extra=extra)

async def get_best(app_id, player=None):
    return await get_store().best_score(app_id, player=player)

__all__ = ['LocalStore', 'get_store', 'get_store_for', 'get_high_scores_sync', 'add_high_score_sync', 'get_best_sync', 'clear_high_scores_sync', 'get_high_scores', 'add_high_score', 'get_best', 'HAS_BROWSER']
