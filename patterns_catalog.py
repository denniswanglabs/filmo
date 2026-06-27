"""Single source of truth for Filmo's curated scene-pattern library.
Read by the assembler (style_fill) AND the landing Lookbook (via the JSON)."""
import json
import os

_CATALOG_PATH = os.path.join(os.path.dirname(__file__), "studio", "src", "timeline", "patterns.catalog.json")
_REQUIRED = ("id", "name", "purpose", "whenToUse", "dataContract", "exampleProps")


def load_catalog(path=None):
    """Return the list of pattern dicts. Raises ValueError on a malformed catalog."""
    with open(path or _CATALOG_PATH, encoding="utf-8") as fh:
        data = json.load(fh)
    pats = data.get("patterns")
    if not isinstance(pats, list) or not pats:
        raise ValueError("catalog has no patterns")
    seen = set()
    for p in pats:
        for k in _REQUIRED:
            if k not in p:
                raise ValueError("pattern %r missing %r" % (p.get("id"), k))
        if p["id"] in seen:
            raise ValueError("duplicate pattern id %r" % p["id"])
        seen.add(p["id"])
    return pats


def pattern_ids(path=None):
    return [p["id"] for p in load_catalog(path)]
