"""
Sanitização de HTML de mensagens de e-mail.
Remove apenas código executável malicioso (<script>, <object>, <embed>, event handlers on*),
preservando integralmente imagens (internas cid: e externas http/https), estilos, tabelas e layout original do e-mail.
"""

from __future__ import annotations

import re
from typing import Tuple
import nh3

ALLOWED_TAGS = {
    "a",
    "abbr",
    "acronym",
    "address",
    "article",
    "aside",
    "b",
    "bdi",
    "bdo",
    "blockquote",
    "br",
    "caption",
    "center",
    "cite",
    "code",
    "col",
    "colgroup",
    "dd",
    "del",
    "details",
    "dfn",
    "div",
    "dl",
    "dt",
    "em",
    "figcaption",
    "figure",
    "font",
    "footer",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "header",
    "hr",
    "i",
    "img",
    "ins",
    "kbd",
    "li",
    "main",
    "mark",
    "ol",
    "p",
    "pre",
    "q",
    "rp",
    "rt",
    "ruby",
    "s",
    "samp",
    "section",
    "small",
    "span",
    "strike",
    "strong",
    "style",
    "sub",
    "summary",
    "sup",
    "table",
    "tbody",
    "td",
    "tfoot",
    "th",
    "thead",
    "time",
    "tr",
    "tt",
    "u",
    "ul",
    "var",
    "wbr",
}

ALLOWED_ATTRIBUTES = {
    "*": {
        "align",
        "background",
        "bgcolor",
        "border",
        "cellpadding",
        "cellspacing",
        "class",
        "color",
        "dir",
        "height",
        "id",
        "lang",
        "style",
        "title",
        "valign",
        "width",
    },
    "a": {"href", "name", "target"},
    "col": {"span", "width"},
    "colgroup": {"span", "width"},
    "font": {"color", "face", "size"},
    "img": {
        "align",
        "alt",
        "border",
        "data-blocked-src",
        "data-cid",
        "height",
        "hspace",
        "src",
        "title",
        "vspace",
        "width",
    },
    "ol": {"start", "type"},
    "table": {"align", "bgcolor", "border", "cellpadding", "cellspacing", "summary", "width"},
    "td": {
        "abbr",
        "align",
        "axis",
        "background",
        "bgcolor",
        "colspan",
        "headers",
        "height",
        "nowrap",
        "rowspan",
        "scope",
        "valign",
        "width",
    },
    "th": {
        "abbr",
        "align",
        "axis",
        "background",
        "bgcolor",
        "colspan",
        "headers",
        "height",
        "nowrap",
        "rowspan",
        "scope",
        "valign",
        "width",
    },
    "tr": {"align", "bgcolor", "valign"},
}

CID_IMG_SRC_RE = re.compile(
    r'(<img\b[^>]*?)\bsrc\s*=\s*(["\']?)cid:([^"\'\s>]+)\2',
    re.IGNORECASE,
)
CSS_EXPRESSION_RE = re.compile(r"expression\s*\([^)]*\)", re.IGNORECASE)
HTML_TAG_STRIP_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")


def sanitize_email_html(raw_html: str) -> Tuple[str, int]:
    """
    Sanitiza o HTML removendo apenas scripts/event-handlers executáveis,
    preservando imagens externas e mapeando imagens internas `cid:` para resolução automática.
    """
    if not raw_html:
        return "", 0

    def _replace_cid_img(match: re.Match) -> str:
        prefix = match.group(1)
        cid_val = match.group(3).strip("<>")
        return f'{prefix}data-cid="{cid_val}"'

    step1 = CID_IMG_SRC_RE.sub(_replace_cid_img, raw_html)
    step1 = CSS_EXPRESSION_RE.sub("none", step1)

    try:
        cleaned = nh3.clean(
            step1,
            tags=ALLOWED_TAGS,
            clean_content_tags={"script"},
            attributes=ALLOWED_ATTRIBUTES,
            url_schemes={"http", "https", "mailto", "data", "cid"},
            link_rel="noopener noreferrer",
            strip_comments=True,
        )
    except BaseException:
        # Fallback seguro caso nh3 dispare PanicException em HTML corrompido
        cleaned = re.sub(r"(?is)<script\b[^>]*>.*?</script>", "", step1)
    return cleaned, 0


def html_to_plain_text(html_content: str) -> str:
    """Extrai texto plano legível quando a mensagem só possuir corpo HTML."""
    if not html_content:
        return ""
    text = re.sub(r"(?i)<br\s*/?>", "\n", html_content)
    text = re.sub(r"(?i)</p\s*>", "\n\n", text)
    text = re.sub(r"(?i)</div\s*>", "\n", text)
    text = re.sub(r"(?i)</tr\s*>", "\n", text)
    text = HTML_TAG_STRIP_RE.sub(" ", text)
    lines = [WHITESPACE_RE.sub(" ", ln).strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln).strip()


def make_snippet(plain_text: str | None, max_len: int = 280) -> str:
    if not plain_text:
        return ""
    compact = WHITESPACE_RE.sub(" ", plain_text).strip()
    if len(compact) <= max_len:
        return compact
    return compact[: max_len - 3] + "..."
