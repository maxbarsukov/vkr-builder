from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .paths import project_root
from .typography import TypographySettings

_DEFAULTS_YAML = project_root() / "config.defaults.yaml"
_USER_YAML = project_root() / "config.yaml"

NEUTRAL_TIMESTAMP = dt.datetime(2026, 1, 1, 0, 0, 0)


@dataclass(frozen=True)
class ProfileConfig:
    docx: Path
    markdown_dir: Path
    images_dir: Path | None
    markdown_files: tuple[str, ...]
    listings_dir: Path | None = None

    @property
    def listings_root(self) -> Path | None:
        return self.listings_dir or self.images_dir


@dataclass(frozen=True)
class WordNamesConfig:
    body: str = "ДИПЛОМ - Обычный текст"
    toc_heading: str = "ДИПЛОМ - Заголовок"
    figure: str = "ДИПЛОМ - Рисунки"
    table_caption: str = "ДИПЛОМ - Таблицы"
    code: str = "ДИПЛОМ - Код"
    list_paragraph: str = "List Paragraph"
    heading_1: str = "Heading 1"
    heading_2: str = "Heading 2"
    heading_3: str = "Heading 3"
    toc_1: str = "toc 1"
    toc_2: str = "toc 2"
    toc_3: str = "toc 3"
    footer: str = "Footer"

    def to_mapping(self) -> dict[str, str]:
        return {k: str(v) for k, v in asdict(self).items()}


_WORD_NAMES_KNOWN = frozenset(WordNamesConfig.__dataclass_fields__.keys())


@dataclass(frozen=True)
class TableContinuationConfig:
    enabled: bool = True
    label: str = "Продолжение таблицы {n}"
    align: str = "right"

    def to_mapping(self) -> dict[str, Any]:
        return {"enabled": self.enabled, "label": self.label, "align": self.align}


@dataclass(frozen=True)
class DashConfig:
    normalize: bool = True
    captions: str = "en-dash"
    body: str = "en-dash"

    def to_mapping(self) -> dict[str, Any]:
        return {"normalize": self.normalize, "captions": self.captions, "body": self.body}


@dataclass(frozen=True)
class StyleConfig:
    typography: TypographySettings
    word_styles: WordNamesConfig
    max_image_width_cm: float = 14.0
    tables: TableContinuationConfig = field(default_factory=TableContinuationConfig)
    dashes: DashConfig = field(default_factory=DashConfig)


@dataclass(frozen=True)
class LintConfig:
    strict: bool = False


@dataclass(frozen=True)
class StatsConfig:
    min_sources: int | None = None
    page_min: int | None = None
    page_max: int | None = None


@dataclass(frozen=True)
class BuildEngineConfig:
    pagination_engine: str = "auto"
    libreoffice_path: str | None = None
    pdf: bool = False
    pdf_engine: str | None = None
    sort_dictionary_lists: bool = False
    diagnose: bool = False


@dataclass(frozen=True)
class WatchConfig:
    debounce_ms: int = 1000


@dataclass(frozen=True)
class DocumentMetadata:
    title: str | None = None
    author: str | None = None
    subject: str | None = None
    keywords: str | None = None
    category: str | None = None
    comments: str | None = None
    language: str | None = None
    last_modified_by: str | None = None
    created: str | None = None
    modified: str | None = None

    def to_mapping(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for f in (
            "title", "author", "subject", "keywords", "category",
            "comments", "language", "last_modified_by", "created", "modified",
        ):
            val = getattr(self, f)
            if val:
                out[f] = val
        return out


@dataclass(frozen=True)
class BuildConfig:
    defaults_path: Path
    user_config_path: Path | None
    base_dir: Path
    profile_name: str
    profile: ProfileConfig
    style: StyleConfig
    build: BuildEngineConfig
    lint: LintConfig
    stats: StatsConfig
    watch: WatchConfig
    metadata: DocumentMetadata


class ConfigError(ValueError):
    pass


def _engine_choice(key: str, value: str) -> str:
    from . import engines

    name = value.strip().lower()
    if name not in engines.ENGINE_CHOICES:
        raise ConfigError(
            f"{key}: expected one of {', '.join(engines.ENGINE_CHOICES)} "
            f"(got {value!r})"
        )
    return name


def _load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigError(f"YAML root must be a mapping: {path}")
    return data


def default_page_number_from(
    defaults_path: str | Path | None = None,
) -> int:
    defaults_file = Path(defaults_path or _DEFAULTS_YAML).resolve()
    if not defaults_file.is_file():
        raise FileNotFoundError(f"System config not found: {defaults_file}")
    raw = _load_yaml(defaults_file)
    style = raw.get("style")
    if not isinstance(style, dict):
        raise ConfigError("config.defaults.yaml: missing style section")
    page = style.get("page")
    if not isinstance(page, dict) or "number_from" not in page:
        raise ConfigError("config.defaults.yaml: style.page.number_from is required")
    val = page["number_from"]
    if not isinstance(val, int) or val < 1:
        raise ConfigError(
            "config.defaults.yaml: style.page.number_from must be an integer >= 1"
        )
    return int(val)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_merged_config(
    user_config_path: str | Path | None = None,
    *,
    defaults_path: str | Path | None = None,
) -> tuple[dict[str, Any], Path, Path, Path | None]:
    defaults_file = Path(defaults_path or _DEFAULTS_YAML).resolve()
    if not defaults_file.is_file():
        raise FileNotFoundError(f"System config not found: {defaults_file}")

    raw = _load_yaml(defaults_file)

    user_file: Path | None
    if user_config_path is not None:
        user_file = Path(user_config_path).resolve()
        if not user_file.is_file():
            raise FileNotFoundError(f"User config not found: {user_file}")
        raw = _deep_merge(raw, _load_yaml(user_file))
    elif _USER_YAML.is_file():
        user_file = _USER_YAML.resolve()
        raw = _deep_merge(raw, _load_yaml(user_file))
    else:
        user_file = None

    base_dir = (user_file or defaults_file).parent
    return raw, base_dir, defaults_file, user_file


def _parse_profile(base: Path, block: dict[str, Any], name: str) -> ProfileConfig:
    docx = block.get("docx", "VKR.docx")
    if not isinstance(docx, str):
        raise ConfigError(f"profiles.{name}.docx must be a string")

    markdown_dir = block.get("markdown_dir", ".")
    if not isinstance(markdown_dir, str):
        raise ConfigError(f"profiles.{name}.markdown_dir must be a string")

    images_raw = block.get("images_dir")
    images_dir: Path | None
    if images_raw is None:
        images_dir = None
    elif not isinstance(images_raw, str):
        raise ConfigError(f"profiles.{name}.images_dir must be a string or null")
    else:
        images_dir = (base / images_raw).resolve()

    listings_raw = block.get("listings_dir")
    listings_dir: Path | None
    if listings_raw is None:
        listings_dir = None
    elif not isinstance(listings_raw, str):
        raise ConfigError(f"profiles.{name}.listings_dir must be a string or null")
    else:
        listings_dir = (base / listings_raw).resolve()

    markdown_files = block.get("markdown_files")
    if (
        not isinstance(markdown_files, list)
        or not markdown_files
        or not all(isinstance(x, str) for x in markdown_files)
    ):
        raise ConfigError(
            f"profiles.{name}.markdown_files must be a non-empty list of strings"
        )

    return ProfileConfig(
        docx=(base / docx).resolve(),
        markdown_dir=(base / markdown_dir).resolve(),
        images_dir=images_dir,
        markdown_files=tuple(str(x) for x in markdown_files),
        listings_dir=listings_dir,
    )


def _parse_word_styles(raw: dict[str, Any] | None) -> WordNamesConfig:
    if raw is None:
        return WordNamesConfig()
    if not isinstance(raw, dict):
        raise ConfigError("style.word_styles must be a mapping or absent")
    merged = WordNamesConfig().to_mapping()
    for key, val in raw.items():
        if key not in _WORD_NAMES_KNOWN:
            raise ConfigError(
                f"Unknown word_styles key: {key!r}. "
                f"Allowed: {', '.join(sorted(_WORD_NAMES_KNOWN))}"
            )
        if not isinstance(val, str) or not val.strip():
            raise ConfigError(f"style.word_styles.{key} must be a non-empty string")
        merged[key] = val.strip()
    return WordNamesConfig(**merged)


_STYLE_FIGURES_KEYS = frozenset({"max_width_cm"})
_STYLE_PAGE_KEYS = frozenset(
    {
        "width_cm",
        "height_cm",
        "margins_cm",
        "header_distance_cm",
        "footer_distance_cm",
        "number_from",
    }
)
_STYLE_TEXT_KEYS = frozenset(
    {
        "font_family",
        "body_font_pt",
        "heading_font_pt",
        "toc_entry_font_pt",
        "caption_font_pt",
        "listing_font_family",
        "code_line_font_pt",
        "footer_page_font_pt",
        "table_cell_font_pt",
        "line_spacing",
        "line_spacing_rule",
        "indent_cm",
        "justify",
    }
)
_TEXT_TO_TYPOGRAPHY = {
    "font_family": "font_family",
    "body_font_pt": "body_font_pt",
    "heading_font_pt": "heading_font_pt",
    "toc_entry_font_pt": "toc_entry_font_pt",
    "caption_font_pt": "caption_font_pt",
    "listing_font_family": "listing_font_family",
    "code_line_font_pt": "code_line_font_pt",
    "footer_page_font_pt": "footer_page_font_pt",
    "table_cell_font_pt": "table_cell_font_pt",
    "line_spacing": "line_spacing_multiple",
    "line_spacing_rule": "body_line_spacing_rule",
    "indent_cm": "paragraph_indent_cm",
    "justify": "body_justify",
}


def _check_style_section(name: str, block: Any, allowed: frozenset[str]) -> dict[str, Any]:
    if block is None:
        return {}
    if not isinstance(block, dict):
        raise ConfigError(f"style.{name} must be a mapping or absent")
    unknown = set(block) - allowed
    if unknown:
        raise ConfigError(
            f"Unknown style.{name} keys: {', '.join(sorted(unknown))}. "
            f"Allowed: {', '.join(sorted(allowed))}"
        )
    return block


def _flatten_style_block(
    style_block: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, float, dict[str, Any] | None]:
    if not isinstance(style_block, dict):
        return None, 14.0, None

    allowed_top = frozenset({"figures", "page", "text", "word_styles", "tables", "dashes"})
    unknown_top = set(style_block) - allowed_top
    if unknown_top:
        raise ConfigError(
            f"Unknown style keys: {', '.join(sorted(unknown_top))}. "
            f"Allowed: {', '.join(sorted(allowed_top))}"
        )

    figures = _check_style_section("figures", style_block.get("figures"), _STYLE_FIGURES_KEYS)
    page = _check_style_section("page", style_block.get("page"), _STYLE_PAGE_KEYS)
    text = _check_style_section("text", style_block.get("text"), _STYLE_TEXT_KEYS)
    word_styles_raw = style_block.get("word_styles")
    if word_styles_raw is not None and not isinstance(word_styles_raw, dict):
        raise ConfigError("style.word_styles must be a mapping or absent")

    width = figures.get("max_width_cm", 14)
    if not isinstance(width, (int, float)) or width <= 0:
        raise ConfigError("style.figures.max_width_cm must be a positive number")

    typography: dict[str, Any] = {}
    if "width_cm" in page:
        typography["page_width_cm"] = page["width_cm"]
    if "height_cm" in page:
        typography["page_height_cm"] = page["height_cm"]
    if "margins_cm" in page:
        typography["margins_cm"] = page["margins_cm"]
    if "header_distance_cm" in page:
        typography["header_distance_cm"] = page["header_distance_cm"]
    if "footer_distance_cm" in page:
        typography["footer_distance_cm"] = page["footer_distance_cm"]
    if "number_from" in page:
        val = page["number_from"]
        if not isinstance(val, int) or val < 1:
            raise ConfigError("style.page.number_from must be an integer >= 1")
        typography["page_number_from"] = val

    for yaml_key, flat_key in _TEXT_TO_TYPOGRAPHY.items():
        if yaml_key in text:
            typography[flat_key] = text[yaml_key]

    return (typography or None), float(width), word_styles_raw


_STYLE_TABLES_KEYS = frozenset(
    {"continuation", "continued_label", "continuation_align"}
)


def _parse_table_continuation(block: Any) -> TableContinuationConfig:
    block = _check_style_section("tables", block, _STYLE_TABLES_KEYS)
    enabled = block.get("continuation", True)
    if not isinstance(enabled, bool):
        raise ConfigError("style.tables.continuation must be true or false")
    label = block.get("continued_label", "Продолжение таблицы {n}")
    if not isinstance(label, str) or not label.strip():
        raise ConfigError("style.tables.continued_label must be a non-empty string")
    align = block.get("continuation_align", "right")
    if not isinstance(align, str) or align.strip().lower() not in (
        "left", "right", "center",
    ):
        raise ConfigError(
            "style.tables.continuation_align must be 'left', 'right' or 'center'"
        )
    return TableContinuationConfig(
        enabled=enabled, label=label.strip(), align=align.strip().lower()
    )


_DASH_VALUES = frozenset({"en-dash", "em-dash"})


def _parse_dashes(raw: Any) -> DashConfig:
    if raw is None:
        return DashConfig()
    if not isinstance(raw, dict):
        raise ConfigError("style.dashes must be a mapping or absent")
    unknown = set(raw) - {"normalize", "captions", "body"}
    if unknown:
        raise ConfigError(
            "Unknown style.dashes keys: " + ", ".join(sorted(unknown))
            + ". Allowed: body, captions, normalize"
        )
    values: dict[str, Any] = {}
    if raw.get("normalize") is not None:
        values["normalize"] = bool(raw["normalize"])
    for key in ("captions", "body"):
        if raw.get(key) is None:
            continue
        name = str(raw[key]).strip().lower()
        if name not in _DASH_VALUES:
            raise ConfigError(
                f"style.dashes.{key} must be 'en-dash' or 'em-dash' "
                f"(got {raw[key]!r})"
            )
        values[key] = name
    return DashConfig(**values)


def _parse_style(raw: dict[str, Any]) -> StyleConfig:
    style_block = raw.get("style")
    typography_raw, max_image_width_cm, word_styles_raw = _flatten_style_block(
        style_block if isinstance(style_block, dict) else None
    )
    if typography_raw is None:
        typography = TypographySettings.merge_with_defaults(
            None, page_number_from=default_page_number_from()
        )
    elif "page_number_from" not in typography_raw:
        typography = TypographySettings.merge_with_defaults(
            typography_raw, page_number_from=default_page_number_from()
        )
    else:
        try:
            typography = TypographySettings.from_flat(typography_raw)
        except ValueError as e:
            raise ConfigError(str(e)) from e
    style_block_dict = style_block if isinstance(style_block, dict) else None
    tables_cfg = _parse_table_continuation(
        style_block_dict.get("tables") if style_block_dict else None
    )
    return StyleConfig(
        typography=typography,
        word_styles=_parse_word_styles(word_styles_raw),
        max_image_width_cm=max_image_width_cm,
        tables=tables_cfg,
        dashes=_parse_dashes(style_block_dict.get("dashes") if style_block_dict else None),
    )


def _parse_lint(raw: dict[str, Any]) -> LintConfig:
    block = raw.get("lint")
    if block is None:
        return LintConfig()
    if not isinstance(block, dict):
        raise ConfigError("lint must be a mapping or absent")
    allowed = frozenset({"strict"})
    unknown = set(block) - allowed
    if unknown:
        raise ConfigError(
            f"Unknown lint keys: {', '.join(sorted(unknown))}. "
            f"Allowed: {', '.join(sorted(allowed))}"
        )
    strict = block.get("strict", False)
    if not isinstance(strict, bool):
        raise ConfigError("lint.strict must be true or false")
    return LintConfig(strict=strict)


def _parse_watch(raw: dict[str, Any]) -> WatchConfig:
    block = raw.get("watch")
    if block is None:
        return WatchConfig()
    if not isinstance(block, dict):
        raise ConfigError("watch must be a mapping or absent")
    unknown = set(block) - {"debounce_ms"}
    if unknown:
        raise ConfigError(
            f"Unknown watch keys: {', '.join(sorted(unknown))}. Allowed: debounce_ms"
        )
    value = block.get("debounce_ms")
    if value is None:
        return WatchConfig()
    if not isinstance(value, int) or isinstance(value, bool) or not 50 <= value <= 60000:
        raise ConfigError(
            "watch.debounce_ms must be an integer between 50 and 60000, or null"
        )
    return WatchConfig(debounce_ms=value)


def _parse_stats(raw: dict[str, Any]) -> StatsConfig:
    block = raw.get("stats")
    if block is None:
        return StatsConfig()
    if not isinstance(block, dict):
        raise ConfigError("stats must be a mapping or absent")
    allowed = frozenset({"min_sources", "page_min", "page_max"})
    unknown = set(block) - allowed
    if unknown:
        raise ConfigError(
            f"Unknown stats keys: {', '.join(sorted(unknown))}. "
            f"Allowed: {', '.join(sorted(allowed))}"
        )
    min_sources = block.get("min_sources")
    if min_sources is not None and (not isinstance(min_sources, int) or min_sources < 0):
        raise ConfigError("stats.min_sources must be a non-negative integer or null")
    page_min = block.get("page_min")
    if page_min is not None and (not isinstance(page_min, int) or page_min < 1):
        raise ConfigError("stats.page_min must be an integer >= 1 or null")
    page_max = block.get("page_max")
    if page_max is not None and (not isinstance(page_max, int) or page_max < 1):
        raise ConfigError("stats.page_max must be an integer >= 1 or null")
    if (
        page_min is not None
        and page_max is not None
        and page_min > page_max
    ):
        raise ConfigError("stats.page_min must not exceed stats.page_max")
    return StatsConfig(min_sources=min_sources, page_min=page_min, page_max=page_max)


def _parse_build(raw: dict[str, Any]) -> BuildEngineConfig:
    block = raw.get("build")
    if block is None:
        return BuildEngineConfig()
    if not isinstance(block, dict):
        raise ConfigError("build must be a mapping or absent")
    allowed = frozenset(
        {
            "pagination_engine",
            "libreoffice_path",
            "pdf",
            "pdf_engine",
            "sort_dictionary_lists",
            "diagnose",
        }
    )
    unknown = set(block) - allowed
    if unknown:
        raise ConfigError(
            f"Unknown build keys: {', '.join(sorted(unknown))}. "
            f"Allowed: {', '.join(sorted(allowed))}"
        )
    engine = block.get("pagination_engine", "auto")
    if not isinstance(engine, str) or not engine.strip():
        raise ConfigError("build.pagination_engine must be a non-empty string")
    engine_norm = _engine_choice("build.pagination_engine", engine)

    lo_path = block.get("libreoffice_path")
    if lo_path is None:
        lo_resolved = None
    elif not isinstance(lo_path, str) or not lo_path.strip():
        raise ConfigError("build.libreoffice_path must be a string or null")
    else:
        lo_resolved = lo_path.strip()

    pdf_flag = block.get("pdf", False)
    if not isinstance(pdf_flag, bool):
        raise ConfigError("build.pdf must be true or false")

    pdf_engine = block.get("pdf_engine")
    if pdf_engine is None:
        pdf_engine_norm = None
    elif not isinstance(pdf_engine, str) or not pdf_engine.strip():
        raise ConfigError("build.pdf_engine must be a string or null")
    else:
        pdf_engine_norm = _engine_choice("build.pdf_engine", pdf_engine)

    sort_dict = block.get("sort_dictionary_lists", False)
    if not isinstance(sort_dict, bool):
        raise ConfigError("build.sort_dictionary_lists must be true or false")

    diagnose_flag = block.get("diagnose", False)
    if not isinstance(diagnose_flag, bool):
        raise ConfigError("build.diagnose must be true or false")

    return BuildEngineConfig(
        pagination_engine=engine_norm,
        libreoffice_path=lo_resolved,
        pdf=pdf_flag,
        pdf_engine=pdf_engine_norm,
        sort_dictionary_lists=sort_dict,
        diagnose=diagnose_flag,
    )


def _resolve_profile_block(
    raw: dict[str, Any], profile: str | None
) -> tuple[str, dict[str, Any]]:
    profiles = raw.get("profiles")
    if profiles is None:
        return "default", raw
    if not isinstance(profiles, dict) or not profiles:
        raise ConfigError("profiles must be a non-empty mapping")
    name = profile or raw.get("active_profile") or raw.get("default_profile")
    if not isinstance(name, str) or not name:
        if len(profiles) == 1:
            name = next(iter(profiles))
        else:
            raise ConfigError(
                "Specify --profile or active_profile in the config "
                f"(available: {', '.join(sorted(profiles))})"
            )
    if name not in profiles:
        raise ConfigError(
            f"Profile {name!r} not found. Available: {', '.join(sorted(profiles))}"
        )
    block = profiles[name]
    if not isinstance(block, dict):
        raise ConfigError(f"profiles.{name} must be a mapping")
    return name, block


_METADATA_FIELDS = frozenset(
    {
        "title", "author", "subject", "keywords", "category",
        "comments", "language", "last_modified_by", "created", "modified",
    }
)


_METADATA_DATE_FIELDS = frozenset({"created", "modified"})


def _parse_metadata(raw: dict[str, Any]) -> DocumentMetadata:
    block = raw.get("metadata")
    if block is None:
        return DocumentMetadata()
    if not isinstance(block, dict):
        raise ConfigError("metadata must be a mapping or absent")
    unknown = set(block) - _METADATA_FIELDS
    if unknown:
        raise ConfigError(
            f"Unknown metadata keys: {', '.join(sorted(unknown))}. "
            f"Allowed: {', '.join(sorted(_METADATA_FIELDS))}"
        )
    values: dict[str, str] = {}
    for key, val in block.items():
        if val is None:
            continue
        if key in _METADATA_DATE_FIELDS and isinstance(val, (dt.date, dt.datetime)):
            val = val.isoformat(sep=" ") if isinstance(val, dt.datetime) else val.isoformat()
        if not isinstance(val, str) or not val.strip():
            raise ConfigError(f"metadata.{key} must be a non-empty string or null")
        values[key] = val.strip()
    return DocumentMetadata(**values)


def load_build_config(
    user_config_path: str | Path | None = None,
    *,
    defaults_path: str | Path | None = None,
    profile: str | None = None,
) -> BuildConfig:
    raw, base, defaults_file, user_file = load_merged_config(
        user_config_path,
        defaults_path=defaults_path,
    )

    profile_name, block = _resolve_profile_block(raw, profile)
    style = _parse_style(raw)
    build = _parse_build(raw)
    lint = _parse_lint(raw)
    stats = _parse_stats(raw)
    watch = _parse_watch(raw)
    metadata = _parse_metadata(raw)
    profile_cfg = _parse_profile(base, block, profile_name)

    return BuildConfig(
        defaults_path=defaults_file,
        user_config_path=user_file,
        base_dir=base,
        profile_name=profile_name,
        profile=profile_cfg,
        style=style,
        build=build,
        lint=lint,
        stats=stats,
        watch=watch,
        metadata=metadata,
    )
