from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Mapping


@dataclass(frozen=True)
class TypographySettings:
    font_family: str = "Times New Roman"
    body_font_pt: float = 14.0
    heading_font_pt: float = 14.0
    toc_entry_font_pt: float = 14.0
    caption_font_pt: float = 14.0
    listing_font_family: str = "Courier New"
    code_line_font_pt: float = 10.0
    footer_page_font_pt: float = 14.0
    table_cell_font_pt: float = 12.0
    line_spacing_multiple: float = 1.5
    body_line_spacing_rule: str = "multiple"
    paragraph_indent_cm: float = 1.25
    body_justify: bool = True
    page_width_cm: float = 21.0
    page_height_cm: float = 29.7
    margin_left_cm: float = 3.0
    margin_right_cm: float = 1.5
    margin_top_cm: float = 2.0
    margin_bottom_cm: float = 2.0
    header_distance_cm: float = 1.0
    footer_distance_cm: float = 1.0
    page_number_from: int = 6

    def to_flat(self) -> dict[str, Any]:
        return {
            "font_family": self.font_family,
            "body_font_pt": self.body_font_pt,
            "heading_font_pt": self.heading_font_pt,
            "toc_entry_font_pt": self.toc_entry_font_pt,
            "caption_font_pt": self.caption_font_pt,
            "listing_font_family": self.listing_font_family,
            "code_line_font_pt": self.code_line_font_pt,
            "footer_page_font_pt": self.footer_page_font_pt,
            "table_cell_font_pt": self.table_cell_font_pt,
            "line_spacing_multiple": self.line_spacing_multiple,
            "body_line_spacing_rule": self.body_line_spacing_rule,
            "paragraph_indent_cm": self.paragraph_indent_cm,
            "body_justify": self.body_justify,
            "page_width_cm": self.page_width_cm,
            "page_height_cm": self.page_height_cm,
            "margin_left_cm": self.margin_left_cm,
            "margin_right_cm": self.margin_right_cm,
            "margin_top_cm": self.margin_top_cm,
            "margin_bottom_cm": self.margin_bottom_cm,
            "header_distance_cm": self.header_distance_cm,
            "footer_distance_cm": self.footer_distance_cm,
            "page_number_from": self.page_number_from,
        }

    @classmethod
    def from_flat(cls, flat: Mapping[str, Any]) -> TypographySettings:
        merged = cls().to_flat()
        for key, val in flat.items():
            if key == "margins_cm":
                if not isinstance(val, dict):
                    raise ValueError("margins_cm must be a mapping")
                submap = {
                    "left": "margin_left_cm",
                    "right": "margin_right_cm",
                    "top": "margin_top_cm",
                    "bottom": "margin_bottom_cm",
                }
                for sk, tk in submap.items():
                    if sk in val:
                        merged[tk] = float(val[sk])
                continue
            if key not in merged:
                raise ValueError(f"Unknown typography key: {key!r}")
            if key == "page_number_from":
                merged[key] = int(val)
            elif key in ("body_justify",):
                merged[key] = bool(val)
            elif key in ("font_family", "listing_font_family", "body_line_spacing_rule"):
                merged[key] = str(val).strip()
            else:
                merged[key] = float(val)
        return cls.validate(merged)

    @classmethod
    def validate(cls, flat: Mapping[str, Any]) -> TypographySettings:
        f = dict(flat)
        if f["body_font_pt"] < 12:
            raise ValueError("body_font_pt must be >= 12")
        if f["line_spacing_multiple"] <= 0:
            raise ValueError("line_spacing_multiple must be > 0")
        if f["paragraph_indent_cm"] <= 0:
            raise ValueError("paragraph_indent_cm must be > 0")
        if f["table_cell_font_pt"] < 12:
            raise ValueError("table_cell_font_pt must be >= 12")
        for fk in (
            "heading_font_pt",
            "toc_entry_font_pt",
            "caption_font_pt",
            "footer_page_font_pt",
        ):
            if f[fk] < 12:
                raise ValueError(f"{fk} must be >= 12")
        for k in (
            "margin_left_cm",
            "margin_right_cm",
            "margin_top_cm",
            "margin_bottom_cm",
        ):
            if f[k] <= 0:
                raise ValueError(f"{k} must be > 0")
        if f["page_width_cm"] <= f["margin_left_cm"] + f["margin_right_cm"]:
            raise ValueError("left and right margins exceed page width")
        if f["page_height_cm"] <= f["margin_top_cm"] + f["margin_bottom_cm"]:
            raise ValueError("top and bottom margins exceed page height")
        if int(f["page_number_from"]) < 1:
            raise ValueError("page_number_from must be >= 1")
        rule = str(f["body_line_spacing_rule"]).strip().lower()
        if rule not in ("multiple", "single"):
            raise ValueError("body_line_spacing_rule must be 'multiple' or 'single'")
        f["body_line_spacing_rule"] = rule
        return cls(**{k: f[k] for k in cls.__dataclass_fields__})

    @classmethod
    def merge_with_defaults(
        cls,
        overrides: Mapping[str, Any] | None,
        *,
        page_number_from: int | None = None,
    ) -> TypographySettings:
        base = cls()
        if page_number_from is not None:
            base = replace(base, page_number_from=page_number_from)
        if not overrides:
            return base
        flat = base.to_flat()
        flat.update(dict(overrides))
        if page_number_from is not None and "page_number_from" not in overrides:
            flat["page_number_from"] = page_number_from
        return cls.from_flat(flat)
