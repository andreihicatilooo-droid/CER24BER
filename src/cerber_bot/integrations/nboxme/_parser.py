"""Внутренний HTML-парсер nboxme."""

from __future__ import annotations

from html.parser import HTMLParser

from .constants import BASE_URL
from .models import NboxFile, NboxPage


class _PageParser(HTMLParser):
    """Разбирает HTML страницы результата nbox.me."""

    _NAV_PATHS = {"/", "/about", "/faq", "/contact", "/terms", "/privacy", "/upload"}
    _NAV_WORDS = {"about", "faq", "contact", "terms", "privacy", "upload"}

    def __init__(self) -> None:
        super().__init__()
        self._links:    list[tuple[str, str]] = []
        self._img_srcs: list[str]             = []
        self._in_a:     bool                  = False
        self._c_href:   str                   = ""
        self._c_text:   str                   = ""

    def _abs(self, href: str) -> str:
        """Преобразует относительный URL в абсолютный."""
        if href.startswith("/") and not href.startswith("//"):
            return BASE_URL + href
        return href

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        d = dict(attrs)
        if tag == "a" and "href" in d and d["href"]:
            self._c_href = self._abs(d["href"])
            self._c_text = ""
            self._in_a   = True
        if tag == "img" and "src" in d and d["src"]:
            src = self._abs(d["src"])
            if BASE_URL in src:
                self._img_srcs.append(src)

    def handle_data(self, data: str) -> None:
        if self._in_a:
            self._c_text += data.strip()

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or not self._in_a:
            return

        href, text = self._c_href, self._c_text.strip()
        self._in_a   = False
        self._c_href = ""
        self._c_text = ""

        if not href.startswith("http"):
            return

        if "/cdn-cgi/" in href or "email-protection" in href:
            return

        path = href.replace(BASE_URL, "").split("?")[0]
        if path in self._NAV_PATHS:
            return
        if any(w in href.lower() for w in self._NAV_WORDS):
            return

        self._links.append((href, text))

    def build_page(self, page_url: str) -> NboxPage:
        """Строит объект ``NboxPage`` из собранных ссылок."""
        del_links  = [(h, t) for h, t in self._links if "delete" in h.lower()]
        file_links = [(h, t) for h, t in self._links if (h, t) not in del_links]

        seen:  set[str]       = set()
        files: list[NboxFile] = []

        for href, text in file_links:
            if href in seen:
                continue
            seen.add(href)

            name = text or href.rstrip("/").split("/")[-1]
            segs = [s for s in href.rstrip("/").split("/") if len(s) > 3]

            del_url = next(
                (dh for dh, _ in del_links if segs and any(s in dh for s in segs)),
                None,
            )
            thumb = next(
                (src for src in self._img_srcs if segs and any(s in src for s in segs)),
                None,
            )
            files.append(NboxFile(name=name, url=href, delete_url=del_url, thumbnail_url=thumb))

        if not files:
            for href, text in self._links:
                if href not in seen:
                    seen.add(href)
                    files.append(NboxFile(
                        name=text or href.rstrip("/").split("/")[-1],
                        url=href,
                    ))

        return NboxPage(page_url=page_url, files=files)
