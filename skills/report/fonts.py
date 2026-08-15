"""System CJK fonts for matplotlib charts and HTML reports.

Matplotlib's default DejaVu Sans cannot draw Chinese, so PNG titles become
boxes. On Windows the usual fix is to load ``msyh.ttc`` / ``simhei.ttf`` from
``%WINDIR%\\Fonts`` and register them with the font manager — name-only
``rcParams`` lookups often miss those files because of the font cache.
"""

from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path

from matplotlib import font_manager
from matplotlib.font_manager import FontProperties
from matplotlib.ft2font import FT2Font
from matplotlib.text import Text

HTML_FONT_FAMILY = (
    '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", '
    '"Hiragino Sans GB", "Microsoft YaHei", "Microsoft YaHei UI", "微软雅黑", '
    '"SimHei", "黑体", "Noto Sans SC", "Noto Sans CJK SC", '
    '"Source Han Sans SC", "WenQuanYi Zen Hei", sans-serif'
)

_FILENAME_NEEDLES = (
    "pingfangsc",
    "hiraginosansgb",
    "heitisc",
    "songtisc",
    "msyh",
    "yahei",
    "simhei",
    "notosanscjksc",
    "notosanssc",
    "notosanscjk",
    "sourcehansans",
    "wqy-zenhei",
    "wqy-microhei",
    "dengxian",
    "pingfang",
    "stheiti",
    "msjh",
    "jhenghei",
    "arialunicode",
    "songti",
    "simsun",
    "simfang",
    "simkai",
    "heiti",
)

_WINDOWS_FONT_NAMES = (
    "msyh.ttc",
    "msyh.ttf",
    "msyhl.ttc",
    "msyhbd.ttc",
    "simhei.ttf",
    "simsun.ttc",
    "simfang.ttf",
    "simkai.ttf",
    "deng.ttf",
    "dengb.ttf",
    "msjh.ttc",
    "msjh.ttf",
)

_CJK_CHAR = "中"
_registered_font_path: str | None = None


def reset_cjk_font_cache() -> None:
    """Clear cached font path and registration. Intended for tests."""
    global _registered_font_path
    _registered_font_path = None
    find_cjk_font_path.cache_clear()
    cjk_font_properties.cache_clear()


@lru_cache(maxsize=1)
def find_cjk_font_path() -> str | None:
    """Return a font file that can draw simplified Chinese, if one exists."""
    for path in _priority_font_files():
        if _has_cjk_glyph(path):
            return os.fspath(path)
    ranked: list[tuple[int, Path]] = []
    for path in _iter_font_files():
        rank = _needle_rank(path)
        if rank is None:
            continue
        ranked.append((rank + _traditional_penalty(path), path))
    ranked.sort(key=lambda item: (item[0], str(item[1])))
    for _rank, path in ranked:
        if _has_cjk_glyph(path):
            return os.fspath(path)
    return None


@lru_cache(maxsize=1)
def cjk_font_properties() -> FontProperties | None:
    path = find_cjk_font_path()
    if path is None:
        return None
    _register_font(path)
    return FontProperties(fname=path)


def configure_cjk_matplotlib() -> str | None:
    """Point matplotlib at a CJK-capable sans font. Returns the family name."""
    import matplotlib as mpl

    mpl.rcParams["axes.unicode_minus"] = False
    path = find_cjk_font_path()
    if path is None:
        _apply_name_fallbacks()
        return None
    _register_font(path)
    props = FontProperties(fname=path)
    family = props.get_name()
    aliases = _family_aliases(path, family)
    current = [str(name) for name in mpl.rcParams["font.sans-serif"]]
    mpl.rcParams["font.family"] = "sans-serif"
    merged: list[str] = []
    for name in [*aliases, *current]:
        if name not in merged:
            merged.append(name)
    mpl.rcParams["font.sans-serif"] = merged
    return family


def apply_cjk_font(fig) -> None:
    """Force every text artist on ``fig`` to the selected CJK font."""
    props = cjk_font_properties()
    if props is None:
        return
    for artist in fig.findobj(Text):
        artist.set_fontproperties(props)


def _apply_name_fallbacks() -> None:
    """Last-resort rcParams names when no font file could be opened."""
    import matplotlib as mpl

    extras = [
        "Microsoft YaHei",
        "微软雅黑",
        "SimHei",
        "黑体",
        "Noto Sans CJK SC",
        "Noto Sans SC",
    ]
    current = [str(name) for name in mpl.rcParams["font.sans-serif"]]
    mpl.rcParams["font.family"] = "sans-serif"
    mpl.rcParams["font.sans-serif"] = [name for name in extras if name not in current] + current


def _family_aliases(path: str, family: str) -> list[str]:
    name = Path(path).name.lower()
    family_l = family.lower()
    aliases = [family]
    if "msyh" in name or "yahei" in family_l:
        aliases.extend(["Microsoft YaHei", "Microsoft YaHei UI", "微软雅黑"])
    if "simhei" in name or family_l == "simhei":
        aliases.extend(["SimHei", "黑体"])
    if "simsun" in name or family_l == "simsun":
        aliases.extend(["SimSun", "宋体"])
    unique: list[str] = []
    for item in aliases:
        if item not in unique:
            unique.append(item)
    return unique


def _register_font(path: str) -> None:
    global _registered_font_path
    if _registered_font_path == path:
        return
    try:
        font_manager.fontManager.addfont(path)
    except (OSError, RuntimeError, TypeError, ValueError):
        return
    _registered_font_path = path


def _priority_font_files() -> list[Path]:
    if sys.platform == "win32":
        return _windows_font_files()
    if sys.platform == "darwin":
        return [path for path in _known_system_font_files() if path.is_file()]
    return [path for path in _known_system_font_files() if path.is_file()]


def _windows_fonts_dir() -> Path:
    windir = os.environ.get("WINDIR") or os.environ.get("SYSTEMROOT") or r"C:\Windows"
    return Path(windir) / "Fonts"


def _windows_font_files() -> list[Path]:
    fonts_dir = _windows_fonts_dir()
    if not fonts_dir.is_dir():
        return []
    try:
        existing = {path.name.lower(): path for path in fonts_dir.iterdir() if path.is_file()}
    except OSError:
        return [fonts_dir / name for name in _WINDOWS_FONT_NAMES]
    files: list[Path] = []
    for name in _WINDOWS_FONT_NAMES:
        path = existing.get(name.lower())
        if path is not None:
            files.append(path)
    return files


def _needle_rank(path: Path) -> int | None:
    blob = path.name.lower().replace(" ", "").replace("_", "")
    for index, needle in enumerate(_FILENAME_NEEDLES):
        if needle.replace(" ", "") in blob:
            return index
    return None


def _traditional_penalty(path: Path) -> int:
    """Prefer simplified-Chinese faces over HK/TC collections."""
    try:
        family = _ft2font(path).family_name.lower()
    except (OSError, RuntimeError, TypeError, ValueError):
        family = path.name.lower()
    blob = f"{family} {path.name.lower()}"
    if any(token in blob for token in (" sc", "gb", "yahei", "simhei", "simplified")):
        return 0
    if any(token in blob for token in (" hk", " tc", "jhenghei", "traditional")):
        return 50
    return 0


def _ft2font(path: Path) -> FT2Font:
    fspath = os.fspath(path)
    try:
        return FT2Font(fspath)
    except (OSError, RuntimeError, TypeError, ValueError):
        return font_manager.get_font(fspath)


def _has_cjk_glyph(path: Path) -> bool:
    try:
        font = _ft2font(path)
    except (OSError, RuntimeError, TypeError, ValueError):
        return False
    try:
        return font.get_char_index(ord(_CJK_CHAR)) != 0
    except (OSError, RuntimeError, TypeError, ValueError):
        return False


def _iter_font_files() -> list[Path]:
    files: list[Path] = []
    files.extend(_priority_font_files())
    try:
        files.extend(Path(item) for item in font_manager.findSystemFonts())
    except (OSError, RuntimeError, TypeError, ValueError):
        pass
    unique: list[Path] = []
    seen: set[str] = set()
    for path in files:
        key = os.fspath(path)
        if key in seen:
            continue
        seen.add(key)
        if path.is_file():
            unique.append(path)
    return unique


def _known_system_font_files() -> list[Path]:
    if sys.platform == "darwin":
        folders = (
            Path("/System/Library/Fonts"),
            Path("/System/Library/Fonts/Supplemental"),
            Path("/Library/Fonts"),
            Path.home() / "Library" / "Fonts",
        )
        names = (
            "PingFang*.ttc",
            "Hiragino Sans GB*",
            "STHeiti*",
            "Songti*",
            "Arial Unicode*",
        )
        files: list[Path] = []
        for folder in folders:
            if not folder.is_dir():
                continue
            for pattern in names:
                files.extend(folder.glob(pattern))
        return files
    if sys.platform == "win32":
        return _windows_font_files()
    folders = (
        Path("/usr/share/fonts"),
        Path("/usr/local/share/fonts"),
        Path.home() / ".fonts",
        Path.home() / ".local" / "share" / "fonts",
    )
    patterns = (
        "NotoSansCJK*",
        "NotoSansSC*",
        "SourceHanSans*",
        "wqy-*.ttc",
        "wqy-*.ttf",
        "wqy-*.otf",
    )
    files = []
    for folder in folders:
        if not folder.is_dir():
            continue
        for pattern in patterns:
            files.extend(folder.rglob(pattern))
    return files
