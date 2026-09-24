def _get(key, default=None):
    if isinstance(res, dict):
        return res.get(key, default)
    try:
        return res[key]
    except:
        return getattr(res, key, default)