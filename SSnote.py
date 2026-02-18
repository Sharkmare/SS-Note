#!/usr/bin/env python3
"""SS13 paper pencode editor with live preview.

This is a small Qt (PySide6) app that keeps an input window (plaintext) and a
preview window (rendered HTML) in sync. It supports a subset of SS13-like
pencode tags and provides quick formatting actions via toolbar + shortcuts.

Requirements:
  pip install PySide6 PySide6-Addons

Run:
  python SSnote.py

Shortcuts (selection-aware):
  Ctrl+B / Ctrl+I / Ctrl+U       [b]/[i]/[u]
  Ctrl+E                         [center][/center]
  Ctrl+1 / Ctrl+2 / Ctrl+3       [h1]/[h2]/[h3]
  Ctrl+Shift+L                   [large][/large]
  Ctrl+Shift+M                   [small][/small]         (pen mode)
  Ctrl+Enter                     [br]
  Ctrl+Shift+Enter               [hr]                    (pen mode)
  Ctrl+T                         [tab]
  Ctrl+F                         [field]
  Ctrl+Shift+T                   [table] template        (pen mode)
  Ctrl+Shift+G                   [grid] template         (pen mode)
  Ctrl+Shift+U                   [list] template         (pen mode)
  Ctrl+Alt+T / Ctrl+Alt+D        [time] / [date]
  Ctrl+Alt+S / Ctrl+Alt+G        [station] / [sign]
"""

from __future__ import annotations

import datetime
import html
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from PySide6 import QtCore, QtGui, QtWidgets

try:
    from PySide6.QtWebEngineWidgets import QWebEngineView  # type: ignore
except ImportError:  # pragma: no cover - depends on optional Qt component
    QWebEngineView = None  # type: ignore


@dataclass(frozen=True)
class PaperConfig:
    station_name: str = "NSS Example"
    default_font: str = "Verdana"
    sign_font: str = "Times New Roman"
    crayon_font: str = "Comic Sans MS"
    pen_color: str = "black"


def encode_byondish_html(text: str) -> str:
    escaped = html.escape(text, quote=True)
    return escaped.replace("'", "&#39;")


def station_time_text(now: Optional[datetime.datetime] = None) -> str:
    return (now or datetime.datetime.now()).strftime("%H:%M")


def station_date_text(now: Optional[datetime.datetime] = None) -> str:
    return (now or datetime.datetime.now()).strftime("%Y-%m-%d")


def resolved_signature(signature: Optional[str], user_name: Optional[str]) -> str:
    if signature and signature.strip():
        return signature.strip()
    if user_name and user_name.strip():
        return user_name.strip()
    return "Anonymous"


def _replace_in_order(text: str, replacements: list[tuple[str, str]]) -> str:
    for needle, repl in replacements:
        text = text.replace(needle, repl)
    return text


def render_pencode_to_html(
    raw_text: str,
    *,
    paper_config: PaperConfig,
    user_name: Optional[str] = None,
    signature: Optional[str] = None,
    is_crayon: bool = False,
    now: Optional[datetime.datetime] = None,
) -> tuple[str, int]:
    """Convert pencode-like markup into an HTML snippet.

    Returns (html_snippet, field_count).
    """
    now = now or datetime.datetime.now()

    html_text = encode_byondish_html(raw_text)
    # BYOND-style pencode treats raw newlines as no-ops; only [br] creates a break.
    # Strip common newline/paragraph-separator characters so they do not render as spaces.
    html_text = (
        html_text.replace("\r\n", "")
        .replace("\n", "")
        .replace("\r", "")
        .replace("\u2028", "")
        .replace("\u2029", "")
    )

    common_replacements: list[tuple[str, str]] = [
        ("[center]", "<center>"),
        ("[/center]", "</center>"),
        ("[br]", "<BR>"),
        ("[b]", "<B>"),
        ("[/b]", "</B>"),
        ("[i]", "<I>"),
        ("[/i]", "</I>"),
        ("[u]", "<U>"),
        ("[/u]", "</U>"),
        ("[time]", station_time_text(now)),
        ("[date]", station_date_text(now)),
        ("[station]", paper_config.station_name),
        ("[large]", '<font size="4">'),
        ("[/large]", "</font>"),
        ("[field]", '<span class="paper_field"></span>'),
        ("[h1]", "<H1>"),
        ("[/h1]", "</H1>"),
        ("[h2]", "<H2>"),
        ("[/h2]", "</H2>"),
        ("[h3]", "<H3>"),
        ("[/h3]", "</H3>"),
        ("[tab]", "&nbsp;" * 6),
    ]
    html_text = _replace_in_order(html_text, common_replacements)

    if "[sign]" in html_text:
        signature_text = encode_byondish_html(resolved_signature(signature, user_name))
        signature_html = f'<font face="{paper_config.sign_font}"><i>{signature_text}</i></font>'
        html_text = html_text.replace("[sign]", signature_html)

    if is_crayon:
        restricted_tokens = [
            "[*]", "[hr]", "[small]", "[/small]", "[list]", "[/list]",
            "[table]", "[/table]", "[row]", "[cell]", "[/cell]", "[/row]",
            "[logo]", "[sglogo]",
        ]
        for token in restricted_tokens:
            html_text = html_text.replace(token, "")
        html_text = (
            f'<font face="{paper_config.crayon_font}" color={paper_config.pen_color}>'
            f'<b>{html_text}</b></font>'
        )
    else:
        pen_only_replacements: list[tuple[str, str]] = [
            ("[*]", "<li>"),
            ("[hr]", "<HR>"),
            ("[small]", '<font size="1">'),
            ("[/small]", "</font>"),
            ("[list]", "<ul>"),
            ("[/list]", "</ul>"),
            ("[table]", "<table border=1 cellspacing=0 cellpadding=3 style='border: 1px solid black;'>"),
            ("[/table]", "</td></tr></table>"),
            ("[grid]", "<table>"),
            ("[/grid]", "</td></tr></table>"),
            ("[row]", "</td><tr>"),
            ("[/row]", ""),
            ("[cell]", "<td>"),
            ("[/cell]", ""),
            # Logos (kept as unresolved \ref paths like in DM)
            ("[logo]", "<img src=\\ref['html/images/ntlogo.png']>"),
            ("[sglogo]", "<img src=\\ref['html/images/sglogo.png']>"),
            ("[trlogo]", "<img src=\\ref['html/images/trader.png']>"),
            ("[pclogo]", "<img src=\\ref['html/images/pclogo.png']>"),
        ]
        html_text = _replace_in_order(html_text, pen_only_replacements)
        html_text = f'<font face="{paper_config.default_font}" color={paper_config.pen_color}>{html_text}</font>'

    field_count = html_text.count('<span class="paper_field">')
    return html_text, field_count


def wrap_in_document(snippet: str) -> str:
    return (
        "<!doctype html>\n"
        "<html>\n<head>\n<meta charset='utf-8'>\n"
        "<style>\n"
        "  body{ margin:12px; }\n"
        "  .paper_field{ display:inline-block; min-width:140px; min-height:1.2em; "
        "               border-bottom:1px dotted #888; vertical-align:baseline; }\n"
        "</style>\n"
        "</head>\n<body>\n"
        f"{snippet}\n"
        "</body>\n</html>\n"
    )


class PreviewWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Paper Preview")

        if QWebEngineView is not None:
            self._backend_name = "WebEngine"
            self._view = QWebEngineView()
        else:
            self._backend_name = "QTextBrowser"
            text_browser = QtWidgets.QTextBrowser()
            text_browser.setOpenExternalLinks(True)
            self._view = text_browser

        self.setCentralWidget(self._view)
        self._status_bar = self.statusBar()
        if self._backend_name != "WebEngine":
            self._status_bar.showMessage("Qt WebEngine not available: using QTextBrowser fallback.")

    def set_rendered_html(self, html_document: str, *, field_count: int) -> None:
        self._view.setHtml(html_document)
        self._status_bar.showMessage(f"Fields: {field_count} | Backend: {self._backend_name}")


class InputWindow(QtWidgets.QMainWindow):
    def __init__(self, preview_window: PreviewWindow, *, paper_config: PaperConfig, source_path: Path) -> None:
        super().__init__()
        self._preview_window = preview_window
        self._paper_config = paper_config
        self._source_path = source_path

        self.setWindowTitle("Paper Input (Plaintext)")
        self._editor = QtWidgets.QPlainTextEdit()
        self._editor.setTabStopDistance(4 * QtGui.QFontMetrics(self._editor.font()).horizontalAdvance(" "))
        self.setCentralWidget(self._editor)

        self._render_debounce_timer = QtCore.QTimer(self)
        self._render_debounce_timer.setSingleShot(True)
        self._render_debounce_timer.setInterval(60)
        self._render_debounce_timer.timeout.connect(self._render_preview)
        self._editor.textChanged.connect(self._schedule_preview_render)

        self._is_crayon = False
        self._user_name: Optional[str] = None
        self._signature: Optional[str] = None

        self._build_formatting_toolbar_and_shortcuts()
        self._build_menu()
        self._load_initial_text()
        self._render_preview()

    def _schedule_preview_render(self) -> None:
        self._render_debounce_timer.start()

    def _render_preview(self) -> None:
        raw_text = self._editor.toPlainText()
        snippet, field_count = render_pencode_to_html(
            raw_text,
            paper_config=self._paper_config,
            user_name=self._user_name,
            signature=self._signature,
            is_crayon=self._is_crayon,
            now=datetime.datetime.now(),
        )
        self._preview_window.set_rendered_html(wrap_in_document(snippet), field_count=field_count)

    def _insert_text(self, text: str) -> None:
        text_cursor = self._editor.textCursor()
        text_cursor.insertText(text)
        self._editor.setTextCursor(text_cursor)

    def _wrap_selection(self, opening_tag: str, closing_tag: str) -> None:
        text_cursor = self._editor.textCursor()
        if text_cursor.hasSelection():
            selected_text = text_cursor.selectedText().replace("\u2029", "\n")
            text_cursor.insertText(f"{opening_tag}{selected_text}{closing_tag}")
            self._editor.setTextCursor(text_cursor)
            return

        text_cursor.insertText(opening_tag + closing_tag)
        text_cursor.setPosition(text_cursor.position() - len(closing_tag))
        self._editor.setTextCursor(text_cursor)

    def _insert_template(self, template: str, *, cursor_marker: str = "<<CURSOR>>") -> None:
        text_cursor = self._editor.textCursor()
        marker_index = template.find(cursor_marker)
        template_text = template.replace(cursor_marker, "")
        text_cursor.insertText(template_text)

        if marker_index >= 0:
            end_pos = text_cursor.position()
            new_pos = end_pos - (len(template_text) - marker_index)
            text_cursor.setPosition(new_pos)
            self._editor.setTextCursor(text_cursor)

    def _create_action(
        self,
        *,
        label: str,
        tooltip: str,
        handler: Callable[[], None],
        shortcut: Optional[str] = None,
        add_to_toolbar: Optional[QtWidgets.QToolBar] = None,
    ) -> QtGui.QAction:
        action = QtGui.QAction(label, self)
        action.setToolTip(tooltip)
        action.triggered.connect(handler)

        if shortcut:
            action.setShortcut(QtGui.QKeySequence(shortcut))
            action.setShortcutContext(QtCore.Qt.ShortcutContext.ApplicationShortcut)

        self.addAction(action)
        if add_to_toolbar is not None:
            add_to_toolbar.addAction(action)

        return action

    def _build_formatting_toolbar_and_shortcuts(self) -> None:
        toolbar = QtWidgets.QToolBar("Formatting", self)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        self._create_action(
            label="B",
            tooltip="Bold (Ctrl+B)",
            handler=lambda: self._wrap_selection("[b]", "[/b]"),
            shortcut="Ctrl+B",
            add_to_toolbar=toolbar,
        )
        self._create_action(
            label="I",
            tooltip="Italic (Ctrl+I)",
            handler=lambda: self._wrap_selection("[i]", "[/i]"),
            shortcut="Ctrl+I",
            add_to_toolbar=toolbar,
        )
        self._create_action(
            label="U",
            tooltip="Underline (Ctrl+U)",
            handler=lambda: self._wrap_selection("[u]", "[/u]"),
            shortcut="Ctrl+U",
            add_to_toolbar=toolbar,
        )
        self._create_action(
            label="Center",
            tooltip="Center (Ctrl+E)",
            handler=lambda: self._wrap_selection("[center]", "[/center]"),
            shortcut="Ctrl+E",
            add_to_toolbar=toolbar,
        )
        toolbar.addSeparator()

        self._create_action(
            label="H1",
            tooltip="Heading 1 (Ctrl+1)",
            handler=lambda: self._wrap_selection("[h1]", "[/h1]"),
            shortcut="Ctrl+1",
            add_to_toolbar=toolbar,
        )
        self._create_action(
            label="H2",
            tooltip="Heading 2 (Ctrl+2)",
            handler=lambda: self._wrap_selection("[h2]", "[/h2]"),
            shortcut="Ctrl+2",
            add_to_toolbar=toolbar,
        )
        self._create_action(
            label="H3",
            tooltip="Heading 3 (Ctrl+3)",
            handler=lambda: self._wrap_selection("[h3]", "[/h3]"),
            shortcut="Ctrl+3",
            add_to_toolbar=toolbar,
        )
        toolbar.addSeparator()

        self._create_action(
            label="Large",
            tooltip="Large text (Ctrl+Shift+L)",
            handler=lambda: self._wrap_selection("[large]", "[/large]"),
            shortcut="Ctrl+Shift+L",
            add_to_toolbar=toolbar,
        )
        self._create_action(
            label="Small",
            tooltip="Small text (Ctrl+Shift+M) (pen mode)",
            handler=lambda: self._wrap_selection("[small]", "[/small]"),
            shortcut="Ctrl+Shift+M",
            add_to_toolbar=toolbar,
        )
        toolbar.addSeparator()

        self._create_action(
            label="BR",
            tooltip="Line break (Ctrl+Enter)",
            handler=lambda: self._insert_text("[br]"),
            shortcut="Ctrl+Enter",
            add_to_toolbar=toolbar,
        )
        self._create_action(
            label="HR",
            tooltip="Horizontal rule (Ctrl+Shift+Enter) (pen mode)",
            handler=lambda: self._insert_text("[hr]"),
            shortcut="Ctrl+Shift+Enter",
            add_to_toolbar=toolbar,
        )
        self._create_action(
            label="Tab",
            tooltip="Insert tab (Ctrl+T)",
            handler=lambda: self._insert_text("[tab]"),
            shortcut="Ctrl+T",
            add_to_toolbar=toolbar,
        )
        self._create_action(
            label="Field",
            tooltip="Insert field (Ctrl+F)",
            handler=lambda: self._insert_text("[field]"),
            shortcut="Ctrl+F",
            add_to_toolbar=toolbar,
        )
        toolbar.addSeparator()

        self._create_action(
            label="Time",
            tooltip="Insert station time (Ctrl+Alt+T)",
            handler=lambda: self._insert_text("[time]"),
            shortcut="Ctrl+Alt+T",
            add_to_toolbar=toolbar,
        )
        self._create_action(
            label="Date",
            tooltip="Insert station date (Ctrl+Alt+D)",
            handler=lambda: self._insert_text("[date]"),
            shortcut="Ctrl+Alt+D",
            add_to_toolbar=toolbar,
        )
        self._create_action(
            label="Station",
            tooltip="Insert station name (Ctrl+Alt+S)",
            handler=lambda: self._insert_text("[station]"),
            shortcut="Ctrl+Alt+S",
            add_to_toolbar=toolbar,
        )
        self._create_action(
            label="Sign",
            tooltip="Insert signature (Ctrl+Alt+G)",
            handler=lambda: self._insert_text("[sign]"),
            shortcut="Ctrl+Alt+G",
            add_to_toolbar=toolbar,
        )
        toolbar.addSeparator()

        self._create_action(
            label="List",
            tooltip="Insert list template (Ctrl+Shift+U) (pen mode)",
            handler=lambda: self._insert_template("[list]\n[*] <<CURSOR>>\n[/list]\n"),
            shortcut="Ctrl+Shift+U",
            add_to_toolbar=toolbar,
        )
        self._create_action(
            label="Table",
            tooltip="Insert table template (Ctrl+Shift+T) (pen mode)",
            handler=lambda: self._insert_template(
                "[table]\n"
                "[row]\n"
                "[cell]<<CURSOR>>[/cell]\n"
                "[cell][/cell]\n"
                "[/row]\n"
                "[/table]\n"
            ),
            shortcut="Ctrl+Shift+T",
            add_to_toolbar=toolbar,
        )
        self._create_action(
            label="Grid",
            tooltip="Insert grid template (Ctrl+Shift+G) (pen mode)",
            handler=lambda: self._insert_template(
                "[grid]\n"
                "[row]\n"
                "[cell]<<CURSOR>>[/cell]\n"
                "[cell][/cell]\n"
                "[/row]\n"
                "[/grid]\n"
            ),
            shortcut="Ctrl+Shift+G",
            add_to_toolbar=toolbar,
        )
        toolbar.addSeparator()

        self._create_action(
            label="NT Logo",
            tooltip="Insert [logo] (pen mode)",
            handler=lambda: self._insert_text("[logo]"),
            add_to_toolbar=toolbar,
        )
        self._create_action(
            label="SG Logo",
            tooltip="Insert [sglogo] (pen mode)",
            handler=lambda: self._insert_text("[sglogo]"),
            add_to_toolbar=toolbar,
        )
        self._create_action(
            label="TR Logo",
            tooltip="Insert [trlogo] (pen mode)",
            handler=lambda: self._insert_text("[trlogo]"),
            add_to_toolbar=toolbar,
        )
        self._create_action(
            label="PC Logo",
            tooltip="Insert [pclogo] (pen mode)",
            handler=lambda: self._insert_text("[pclogo]"),
            add_to_toolbar=toolbar,
        )

    def _build_menu(self) -> None:
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("File")
        open_action = self._create_action(label="Open…", tooltip="Open note", handler=self.open_file, shortcut="Ctrl+O")
        save_action = self._create_action(label="Save", tooltip="Save note", handler=self.save_file, shortcut="Ctrl+S")
        save_as_action = self._create_action(
            label="Save As…", tooltip="Save note as…", handler=self.save_file_as, shortcut="Ctrl+Shift+S"
        )
        quit_action = self._create_action(label="Quit", tooltip="Quit", handler=QtWidgets.QApplication.quit, shortcut="Ctrl+Q")

        file_menu.addAction(open_action)
        file_menu.addAction(save_action)
        file_menu.addAction(save_as_action)
        file_menu.addSeparator()
        file_menu.addAction(quit_action)

        options_menu = menu_bar.addMenu("Options")
        self._crayon_mode_action = QtGui.QAction("Crayon mode", self)
        self._crayon_mode_action.setCheckable(True)
        self._crayon_mode_action.triggered.connect(self.toggle_crayon_mode)
        options_menu.addAction(self._crayon_mode_action)

        meta_menu = menu_bar.addMenu("Meta")
        set_user_action = self._create_action(label="Set user name…", tooltip="Set user name", handler=self.set_user_name)
        set_signature_action = self._create_action(label="Set signature…", tooltip="Set signature", handler=self.set_signature)
        meta_menu.addAction(set_user_action)
        meta_menu.addAction(set_signature_action)

    def _load_initial_text(self) -> None:
        if not self._source_path.exists():
            return

        try:
            self._editor.setPlainText(self._source_path.read_text(encoding="utf-8", errors="replace"))
            self.statusBar().showMessage(f"Loaded: {self._source_path}")
        except OSError as exc:
            self.statusBar().showMessage(f"Failed to load {self._source_path}: {exc}")

    def toggle_crayon_mode(self) -> None:
        self._is_crayon = bool(self._crayon_mode_action.isChecked())
        self._render_preview()

    def set_user_name(self) -> None:
        text, ok = QtWidgets.QInputDialog.getText(
            self, "User name", "User name (used if no signature is set):"
        )
        if ok:
            self._user_name = text.strip() or None
            self._render_preview()

    def set_signature(self) -> None:
        text, ok = QtWidgets.QInputDialog.getText(self, "Signature", "Signature (used for [sign]):")
        if ok:
            self._signature = text.strip() or None
            self._render_preview()

    def open_file(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Open plaintext note",
            str(self._source_path.parent),
            "Notes (*.ssnote *.txt);;All Files (*)",
        )
        if not path:
            return

        selected_path = Path(path)
        try:
            self._editor.setPlainText(selected_path.read_text(encoding="utf-8", errors="replace"))
            self._source_path = selected_path
            self.statusBar().showMessage(f"Loaded: {selected_path}")
            self._render_preview()
        except OSError as exc:
            QtWidgets.QMessageBox.critical(self, "Open failed", str(exc))

    def save_file(self) -> None:
        try:
            self._source_path.write_text(self._editor.toPlainText(), encoding="utf-8")
            self.statusBar().showMessage(f"Saved: {self._source_path}")
        except OSError as exc:
            QtWidgets.QMessageBox.critical(self, "Save failed", str(exc))

    def save_file_as(self) -> None:
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Save note as",
            str(self._source_path),
            "Notes (*.ssnote *.txt);;All Files (*)",
        )
        if not path:
            return
        self._source_path = Path(path)
        self.save_file()


def main() -> int:
    app = QtWidgets.QApplication(sys.argv)

    paper_config = PaperConfig(
        station_name="NSS Example",
        default_font="Verdana",
        sign_font="Times New Roman",
        crayon_font="Comic Sans MS",
        pen_color="black",
    )

    preview_window = PreviewWindow()
    input_window = InputWindow(preview_window, paper_config=paper_config, source_path=Path("PaperTest.ssnote"))

    screen = app.primaryScreen()
    if screen:
        available = screen.availableGeometry()
        window_width = max(900, available.width() // 2)
        window_height = max(700, int(available.height() * 0.8))
        left_x = available.x() + (available.width() - (2 * window_width)) // 2
        top_y = available.y() + (available.height() - window_height) // 2
        input_window.setGeometry(left_x, top_y, window_width, window_height)
        preview_window.setGeometry(left_x + window_width, top_y, window_width, window_height)

    input_window.show()
    preview_window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
