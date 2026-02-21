#!/usr/bin/env python3
"""Groq GUI chat client — popup window with streaming and markdown rendering."""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from groq import Groq
from PySide6.QtCore import Qt, QEvent, QTimer, Signal, QThread, QUrl, QObject, ClassInfo, Slot
from PySide6.QtDBus import QDBusAbstractAdaptor, QDBusConnection
from PySide6.QtGui import QAction, QCursor, QIcon, QKeySequence, QColor
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QTextEdit, QPushButton, QLabel, QSystemTrayIcon, QMenu, QMessageBox,
    QComboBox, QSizePolicy,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineSettings
import markdown as md_lib

load_dotenv()

# ── Config persistence ────────────────────────────────────────────────────────

CONFIG_DIR = Path.home() / ".config" / "groq-chat"
CONFIG_PATH = CONFIG_DIR / "config.json"
CONVERSATIONS_DIR = CONFIG_DIR / "conversations"
DEFAULT_W, DEFAULT_H = 740, 660
WIDGET_MARGINS = 8


def load_config() -> dict:
    """Load full configuration including window size, model, and system prompt."""
    try:
        return json.loads(CONFIG_PATH.read_text())
    except Exception:
        return {"width": DEFAULT_W, "height": DEFAULT_H}


def save_config(config: dict) -> None:
    """Save configuration to disk."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, indent=2))


def load_window_size() -> tuple[int, int]:
    """Load saved window dimensions."""
    config = load_config()
    return int(config.get("width", DEFAULT_W)), int(config.get("height", DEFAULT_H))


def save_window_size(w: int, h: int) -> None:
    """Save window dimensions to config."""
    try:
        config = load_config()
    except Exception:
        config = {}
    config.update({"width": w, "height": h})
    save_config(config)


def save_conversation(messages: list[dict], filename: Optional[str] = None) -> None:
    """Save conversation history to a JSON file."""
    CONVERSATIONS_DIR.mkdir(parents=True, exist_ok=True)
    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"conversation_{timestamp}.json"
    filepath = CONVERSATIONS_DIR / filename
    filepath.write_text(json.dumps(messages, indent=2))


def load_conversation(filename: str) -> list[dict]:
    """Load conversation history from a JSON file."""
    filepath = CONVERSATIONS_DIR / filename
    return json.loads(filepath.read_text())


DEFAULT_MODEL = "llama-3.3-70b-versatile"

# Fallback models if API call fails
FALLBACK_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "meta-llama/llama-4-maverick-17b-128e-instruct",
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "moonshotai/kimi-k2-instruct-0905",
    "qwen/qwen3-32b",
    "openai/gpt-oss-120b",
    "gemma2-9b-it",
]


def fetch_available_models(client: Groq) -> list[str]:
    """Fetch available models from Groq API."""
    try:
        models_response = client.models.list()
        # Filter for chat models and sort by ID
        chat_models = [
            model.id
            for model in models_response.data
            if hasattr(model, 'id')
        ]
        return sorted(chat_models) if chat_models else FALLBACK_MODELS
    except Exception as e:
        print(f"Failed to fetch models from API: {e}, using fallback list", file=sys.stderr)
        return FALLBACK_MODELS


# ── HTML page template ────────────────────────────────────────────────────────

PAGE_HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<link rel="stylesheet"
  href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/tokyo-night-dark.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body {
  background: #1e1e2e;
  color: #cdd6f4;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
  font-size: 14px;
  line-height: 1.65;
  height: 100%;
}
#chat {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.message {
  border-radius: 10px;
  padding: 12px 16px;
  max-width: 100%;
  word-break: break-word;
}
.user {
  background: #2a2a3d;
  border-left: 3px solid #89b4fa;
  margin-left: 32px;
}
.assistant {
  background: #181825;
  border-left: 3px solid #a6e3a1;
  margin-right: 32px;
}
.role-label {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  margin-bottom: 6px;
  opacity: 0.55;
}
.user .role-label { color: #89b4fa; }
.assistant .role-label { color: #a6e3a1; }
.content p { margin: 0 0 8px; }
.content p:last-child { margin-bottom: 0; }
.content h1,.content h2,.content h3,.content h4 {
  margin: 12px 0 6px; font-weight: 600; color: #cba6f7;
}
.content ul,.content ol { margin: 6px 0 6px 20px; }
.content li { margin-bottom: 2px; }
.content a { color: #89dceb; }
.content strong { color: #f5c2e7; }
.content em { color: #fab387; }
.content code {
  background: #11111b;
  border-radius: 4px;
  padding: 1px 5px;
  font-family: "JetBrains Mono", "Fira Code", "Cascadia Code", monospace;
  font-size: 13px;
  color: #cba6f7;
}
.code-block-wrapper {
  position: relative;
  margin: 10px 0;
}
.code-block-wrapper .copy-btn {
  position: absolute;
  top: 8px;
  right: 8px;
  background: #313244;
  color: #cdd6f4;
  border: none;
  border-radius: 4px;
  padding: 4px 8px;
  font-size: 11px;
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.2s, background 0.2s;
}
.code-block-wrapper:hover .copy-btn {
  opacity: 1;
}
.code-block-wrapper .copy-btn:hover {
  background: #45475a;
}
.code-block-wrapper .copy-btn:active {
  background: #89b4fa;
  color: #1e1e2e;
}
.content pre {
  background: #11111b;
  border-radius: 8px;
  padding: 14px;
  overflow-x: auto;
  margin: 0;
  border: 1px solid #313244;
}
.content pre code {
  background: none;
  padding: 0;
  color: inherit;
  font-size: 13px;
  border-radius: 0;
}
.content table {
  border-collapse: collapse;
  margin: 8px 0;
  width: 100%;
}
.content th, .content td {
  border: 1px solid #45475a;
  padding: 6px 12px;
  text-align: left;
}
.content th { background: #313244; }
.content blockquote {
  border-left: 3px solid #6c7086;
  padding-left: 12px;
  margin: 8px 0;
  color: #a6adc8;
}
.cursor {
  display: inline-block;
  width: 2px;
  height: 1em;
  background: #a6e3a1;
  vertical-align: text-bottom;
  animation: blink 1s step-end infinite;
  margin-left: 1px;
}
@keyframes blink { 50% { opacity: 0; } }
/* Custom scrollbar */
::-webkit-scrollbar {
  width: 12px;
}
::-webkit-scrollbar-track {
  background: #181825;
}
::-webkit-scrollbar-thumb {
  background: #45475a;
  border-radius: 6px;
}
::-webkit-scrollbar-thumb:hover {
  background: #585b70;
}
</style>
</head>
<body>
<div id="chat"></div>
<script>
let msgCounter = 0;

function escapeHtml(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function copyToClipboard(text) {
  // Create a temporary textarea element
  const textarea = document.createElement('textarea');
  textarea.value = text;
  textarea.style.position = 'fixed';
  textarea.style.opacity = '0';
  document.body.appendChild(textarea);
  textarea.select();

  try {
    document.execCommand('copy');
    return true;
  } catch (err) {
    console.error('Failed to copy:', err);
    return false;
  } finally {
    document.body.removeChild(textarea);
  }
}

function wrapCodeBlocks(container) {
  container.querySelectorAll('pre').forEach(pre => {
    if (pre.parentElement.classList.contains('code-block-wrapper')) return;
    const wrapper = document.createElement('div');
    wrapper.className = 'code-block-wrapper';
    pre.parentNode.insertBefore(wrapper, pre);
    wrapper.appendChild(pre);

    const copyBtn = document.createElement('button');
    copyBtn.className = 'copy-btn';
    copyBtn.textContent = 'Copy';
    copyBtn.onclick = function() {
      const code = pre.querySelector('code') || pre;
      if (copyToClipboard(code.textContent)) {
        copyBtn.textContent = 'Copied!';
        setTimeout(() => { copyBtn.textContent = 'Copy'; }, 2000);
      } else {
        copyBtn.textContent = 'Failed';
        setTimeout(() => { copyBtn.textContent = 'Copy'; }, 2000);
      }
    };
    wrapper.appendChild(copyBtn);
  });
}

function addMessage(id, role, htmlContent, showCursor) {
  let el = document.createElement('div');
  el.id = id;
  el.className = 'message ' + role;
  el.innerHTML =
    '<div class="role-label">' + role + '</div>' +
    '<div class="content">' + htmlContent + (showCursor ? '<span class="cursor"></span>' : '') + '</div>';
  document.getElementById('chat').appendChild(el);
  el.scrollIntoView({behavior: 'instant', block: 'end'});
  wrapCodeBlocks(el);
}

function updateMessage(id, htmlContent, showCursor) {
  let el = document.getElementById(id);
  if (!el) return;
  el.querySelector('.content').innerHTML =
    htmlContent + (showCursor ? '<span class="cursor"></span>' : '');
  el.scrollIntoView({behavior: 'instant', block: 'end'});
  el.querySelectorAll('pre code').forEach(b => { hljs.highlightElement(b); });
  wrapCodeBlocks(el);
}

function clearChat() {
  document.getElementById('chat').innerHTML = '';
}
</script>
</body>
</html>
"""


def render_markdown(text: str) -> str:
    """Convert markdown text to HTML."""
    return md_lib.markdown(
        text,
        extensions=["fenced_code", "codehilite", "tables", "nl2br", "sane_lists"],
        extension_configs={
            "codehilite": {"css_class": "highlight", "guess_lang": False},
        },
    )


def js_string(s: str) -> str:
    """Escape a string for safe embedding in a JS template literal."""
    return (
        s.replace("\\", "\\\\")
         .replace("`", "\\`")
         .replace("${", "\\${")
         .replace("</", "<\\/")
    )


# ── Worker thread ─────────────────────────────────────────────────────────────

class StreamWorker(QThread):
    token = Signal(str)
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, client: Groq, messages: list, model: str):
        super().__init__()
        self.client = client
        self.messages = messages
        self.model = model

    def run(self):
        try:
            full_text = ""
            stream = self.client.chat.completions.create(
                messages=self.messages,
                model=self.model,
                stream=True,
            )
            for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    full_text += delta
                    self.token.emit(delta)
            self.finished.emit(full_text)
        except Exception as e:
            self.error.emit(str(e))


# ── Main window ───────────────────────────────────────────────────────────────

APP_STYLE = """
QMainWindow, QWidget#root {
    background-color: #1e1e2e;
    border-radius: 12px;
}
QWidget#footer {
    background-color: #1e1e2e;
    border-top: 1px solid #313244;
}
QWidget#header {
    background-color: #181825;
    border-top-left-radius: 12px;
    border-top-right-radius: 12px;
}
QTextEdit {
    background-color: #2a2a3d;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 8px;
    padding: 8px 10px;
    font-size: 14px;
    selection-background-color: #89b4fa;
    selection-color: #1e1e2e;
}
QTextEdit:focus { border-color: #89b4fa; }
QPushButton#sendBtn {
    background-color: #89b4fa;
    color: #1e1e2e;
    border: none;
    border-radius: 8px;
    font-weight: 700;
    font-size: 20px;
}
QPushButton#sendBtn:hover { background-color: #b4d0ff; }
QPushButton#sendBtn:disabled { background-color: #45475a; color: #6c7086; }
QPushButton#clearBtn {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 0px;
    font-size: 19px;
    min-width: 28px;
    min-height: 28px;
}
QPushButton#clearBtn:hover { background-color: #45475a; }
QComboBox {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 0px 8px;
    font-size: 12px;
    min-height: 28px;
}
QComboBox::drop-down { border: none; width: 20px; }
QComboBox::down-arrow { width: 10px; }
QComboBox QAbstractItemView {
    background-color: #313244;
    color: #cdd6f4;
    selection-background-color: #89b4fa;
    selection-color: #1e1e2e;
    border: 1px solid #45475a;
}
QLabel#title {
    color: #cdd6f4;
    font-weight: 600;
    font-size: 15px;
    padding-left: 4px;
}
QLabel#hotkey-hint {
    color: #6c7086;
    font-size: 11px;
}
"""


class ChatWindow(QMainWindow):
    # Signals used to safely trigger window actions from any thread
    toggle_signal = Signal()
    show_signal = Signal()
    hide_signal = Signal()

    def __init__(self, client: Groq, model: str, system_prompt: Optional[str] = None, available_models: Optional[list[str]] = None):
        super().__init__()
        self.client = client
        self.current_model = model
        self.system_prompt = system_prompt
        self.messages: list[dict] = []
        self.available_models = available_models or FALLBACK_MODELS

        self._worker: Optional[StreamWorker] = None
        self._stream_buf = ""
        self._current_msg_id: Optional[str] = None
        self._current_stream_text = ""
        self._flush_timer = QTimer()
        self._flush_timer.setInterval(80)
        self._flush_timer.timeout.connect(self._flush_stream)
        self._page_ready = False

        self.toggle_signal.connect(self.toggle)
        self.show_signal.connect(self._bring_to_front)
        self.hide_signal.connect(self.hide)
        self._setup_ui()

        # Install global event filter for keyboard focus management
        self.installEventFilter(self)

    # ── UI setup ──────────────────────────────────────────────────────────────

    def _setup_ui(self):
        self.setWindowTitle("Groq Chat")
        w, h = load_window_size()
        self.resize(w, h)
        self.setMinimumSize(420, 340)
        self.setStyleSheet(APP_STYLE)
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
        )
        # Enable transparency for rounded corners
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._center_on_screen()

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        self._root = root

        # 3×3 grid: resize strips occupy the 8 outer cells, content fills center.
        grid = QGridLayout(root)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(0)

        def strip(left=False, top=False, right=False, bottom=False, cursor=None):
            return _ResizeStrip(self, (left, top, right, bottom), cursor)

        # Corners
        tl = strip(left=True,  top=True,                    cursor=Qt.CursorShape.SizeFDiagCursor)
        tr = strip(            top=True,  right=True,        cursor=Qt.CursorShape.SizeBDiagCursor)
        br = strip(                       right=True, bottom=True, cursor=Qt.CursorShape.SizeFDiagCursor)
        bl = strip(left=True,                         bottom=True, cursor=Qt.CursorShape.SizeBDiagCursor)
        # Edges
        t  = strip(            top=True,                    cursor=Qt.CursorShape.SizeVerCursor)
        b  = strip(                                  bottom=True, cursor=Qt.CursorShape.SizeVerCursor)
        l  = strip(left=True,                               cursor=Qt.CursorShape.SizeHorCursor)
        r  = strip(                       right=True,        cursor=Qt.CursorShape.SizeHorCursor)

        for corner in (tl, tr, br, bl):
            corner.setFixedSize(WIDGET_MARGINS, WIDGET_MARGINS)
        for edge in (t, b):
            edge.setFixedHeight(WIDGET_MARGINS)
        for edge in (l, r):
            edge.setFixedWidth(WIDGET_MARGINS)

        grid.addWidget(tl, 0, 0); grid.addWidget(t,  0, 1); grid.addWidget(tr, 0, 2)
        grid.addWidget(l,  1, 0);                            grid.addWidget(r,  1, 2)
        grid.addWidget(bl, 2, 0); grid.addWidget(b,  2, 1); grid.addWidget(br, 2, 2)

        # Center content widget
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        self._header = self._build_header()
        content_layout.addWidget(self._header)

        # Add separator line between header and content
        separator = QWidget()
        separator.setObjectName("separator")
        separator.setFixedHeight(1)
        separator.setStyleSheet("background-color: #313244;")
        content_layout.addWidget(separator)

        self._view = QWebEngineView()
        self._view.settings().setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
        )
        self._view.setHtml(PAGE_HTML)
        self._view.loadFinished.connect(self._on_page_ready)
        content_layout.addWidget(self._view, 1)

        content_layout.addWidget(self._build_footer())

        grid.addWidget(content, 1, 1)
        grid.setColumnStretch(1, 1)
        grid.setRowStretch(1, 1)

    def _build_header(self) -> QWidget:
        header = _DraggableHeader()
        header.setObjectName("header")
        row = QHBoxLayout(header)
        row.setContentsMargins(0, 0, 0, WIDGET_MARGINS)
        row.setSpacing(WIDGET_MARGINS)

        title = QLabel("Groq Chat")
        title.setObjectName("title")
        row.addWidget(title)

        row.addStretch()

        self._model_combo = QComboBox()
        for m in self.available_models:
            self._model_combo.addItem(m)
        idx = self.available_models.index(self.current_model) if self.current_model in self.available_models else 0
        self._model_combo.setCurrentIndex(idx)
        self._model_combo.currentTextChanged.connect(self._on_model_change)
        row.addWidget(self._model_combo)

        clear_btn = QPushButton("🗑")
        clear_btn.setObjectName("clearBtn")
        clear_btn.setToolTip("Clear conversation")
        clear_btn.clicked.connect(self._clear_chat)
        row.addWidget(clear_btn)

        return header

    def _build_footer(self) -> QWidget:
        footer = QWidget()
        footer.setObjectName("footer")
        row = QHBoxLayout(footer)
        row.setContentsMargins(0, WIDGET_MARGINS, 0, 0)
        row.setSpacing(WIDGET_MARGINS)

        self._input = QTextEdit()
        self._input.setPlaceholderText("Message… (Enter to send, Shift+Enter for newline)")
        self._input.setFixedHeight(72)
        self._input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._input.installEventFilter(self)
        row.addWidget(self._input, 1)

        return footer

    # ── Event handling ────────────────────────────────────────────────────────

    def changeEvent(self, event):
        """Hide window when it loses focus (user clicks outside)."""
        if event.type() == QEvent.Type.ActivationChange and not self.isActiveWindow():
            self.hide()
        super().changeEvent(event)

    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent

        # Handle Enter key in input box
        if obj is self._input and event.type() == QEvent.Type.KeyPress:
            if (event.key() == Qt.Key.Key_Return
                    and not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier)):
                self._send()
                return True

        # Global keyboard event filter for the main window
        if obj is self and event.type() == QEvent.Type.KeyPress:
            # Escape key hides window from anywhere
            if event.key() == Qt.Key.Key_Escape:
                self.hide()
                return True

            # Redirect printable characters to input box
            # Only if input box doesn't have focus and we're not in a text widget
            if not self._input.hasFocus():
                focused = QApplication.focusWidget()
                # Don't redirect if user is typing in another text widget
                if not isinstance(focused, QTextEdit):
                    text = event.text()
                    # Check if this is a printable character (not a modifier/control key)
                    if text and text.isprintable() and not event.modifiers() & (
                        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier
                    ):
                        self._input.setFocus()
                        self._input.insertPlainText(text)
                        return True

        return super().eventFilter(obj, event)

    def keyPressEvent(self, event):
        # Escape handling is now in eventFilter for global coverage
        super().keyPressEvent(event)

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_page_ready(self, ok: bool):
        self._page_ready = ok

    def _on_model_change(self, model: str):
        self.current_model = model

    def _clear_chat(self):
        self.messages = []
        self._run_js("clearChat()")

    def _send(self):
        if self._worker and self._worker.isRunning():
            return
        text = self._input.toPlainText().strip()
        if not text:
            return

        self._input.clear()

        # Show user message
        msg_id = f"msg-{len(self.messages)}"
        self.messages.append({"role": "user", "content": text})
        import html as html_lib
        user_html = html_lib.escape(text).replace("\n", "<br>")
        self._run_js(f"addMessage(`{js_string(msg_id)}`, `user`, `{js_string(user_html)}`, false)")

        # Placeholder for assistant
        self._current_msg_id = f"msg-{len(self.messages)}"
        self._current_stream_text = ""
        self.messages.append({"role": "assistant", "content": ""})
        self._run_js(
            f"addMessage(`{js_string(self._current_msg_id)}`, `assistant`, ``, true)"
        )

        # Build API messages
        api_messages = []
        if self.system_prompt:
            api_messages.append({"role": "system", "content": self.system_prompt})
        # exclude the empty placeholder at the end
        api_messages.extend(
            {"role": m["role"], "content": m["content"]}
            for m in self.messages[:-1]
        )

        self._worker = StreamWorker(self.client, api_messages, self.current_model)
        self._worker.token.connect(self._on_token)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._flush_timer.start()
        self._worker.start()

    def _on_token(self, token: str):
        self._stream_buf += token

    def _flush_stream(self):
        if not self._stream_buf:
            return
        self._current_stream_text += self._stream_buf
        self._stream_buf = ""
        # Show raw text while streaming (fast, no markdown parse lag)
        import html as html_lib
        preview = html_lib.escape(self._current_stream_text).replace("\n", "<br>")
        self._run_js(
            f"updateMessage(`{js_string(self._current_msg_id)}`, `{js_string(preview)}`, true)"
        )

    def _on_finished(self, full_text: str):
        self._flush_timer.stop()
        self._stream_buf = ""
        self._current_stream_text = full_text
        self.messages[-1]["content"] = full_text

        # Final render: full markdown
        rendered = render_markdown(full_text)
        self._run_js(
            f"updateMessage(`{js_string(self._current_msg_id)}`, `{js_string(rendered)}`, false)"
        )
        self._input.setFocus()

    def _on_error(self, error: str):
        self._flush_timer.stop()
        self._stream_buf = ""

        # Remove the empty assistant message and the user message from history
        if len(self.messages) >= 2:
            self.messages.pop()  # remove empty assistant
            self.messages.pop()  # remove user message

        # Display user-friendly error message
        import html as html_lib
        error_msg = error
        if "rate_limit" in error.lower() or "429" in error:
            error_msg = "Rate limit exceeded. Please wait a moment and try again."
        elif "authentication" in error.lower() or "401" in error:
            error_msg = "Authentication failed. Please check your API key."
        elif "timeout" in error.lower():
            error_msg = "Request timed out. Please try again."

        err_html = f'<span style="color:#f38ba8">⚠️ Error: {html_lib.escape(error_msg)}</span>'
        self._run_js(
            f"updateMessage(`{js_string(self._current_msg_id)}`, `{js_string(err_html)}`, false)"
        )

        # Show popup for critical errors
        if "authentication" in error.lower() or "401" in error:
            QMessageBox.warning(
                self,
                "Authentication Error",
                "Failed to authenticate with Groq API. Please check your API key in the .env file.",
            )

    def _run_js(self, js: str):
        if self._page_ready:
            self._view.page().runJavaScript(js)

    # ── Window management ─────────────────────────────────────────────────────

    def _center_on_screen(self):
        screen = QApplication.primaryScreen().availableGeometry()
        fg = self.frameGeometry()
        self.move(
            screen.center().x() - fg.width() // 2,
            screen.center().y() - fg.height() // 2,
        )

    def toggle(self):
        if self.isVisible() and self.isActiveWindow():
            self.hide()
        else:
            self._bring_to_front()

    def _bring_to_front(self):
        self.show()
        self.raise_()
        self.activateWindow()
        self._input.setFocus()


# ── Draggable header ─────────────────────────────────────────────────────────

class _DraggableHeader(QWidget):
    """Header bar that moves the parent window when dragged."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self._drag_start = None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = (
                event.globalPosition().toPoint() - self.window().frameGeometry().topLeft()
            )
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton and self._drag_start is not None:
            self.window().move(event.globalPosition().toPoint() - self._drag_start)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_start = None
        super().mouseReleaseEvent(event)


# ── Resize strips ────────────────────────────────────────────────────────────
#
# Eight _ResizeStrip widgets sit in the outer cells of a 3×3 QGridLayout on
# root, with the actual content in the center cell.  Each strip calls
# setCursor() once — Qt automatically restores the default cursor when the
# mouse leaves the strip, so no manual cursor tracking is needed at all.
#
# During a drag Qt grabs the mouse to the pressed widget, so mouseMoveEvent
# keeps firing on the strip even after the pointer leaves its bounds.

class _ResizeStrip(QWidget):
    """Transparent edge/corner strip that handles resize drag for one edge."""

    def __init__(self, window: QMainWindow, edge: tuple, cursor_shape):
        super().__init__()
        self._win = window
        self._edge = edge  # (left, top, right, bottom)
        self._start_global = None
        self._start_size = None
        self.setCursor(QCursor(cursor_shape))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._start_global = event.globalPosition().toPoint()
            self._start_size = self._win.size()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton and self._start_global is not None:
            self._do_resize(event.globalPosition().toPoint())
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._start_global is not None:
            self._start_global = None
            save_window_size(self._win.width(), self._win.height())
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def _do_resize(self, gpos):
        win = self._win
        d = gpos - self._start_global
        left, top, right, bottom = self._edge

        new_w = self._start_size.width()
        new_h = self._start_size.height()

        if right:  new_w = max(win.minimumWidth(),  new_w + 2 * d.x())
        elif left: new_w = max(win.minimumWidth(),  new_w - 2 * d.x())
        if bottom: new_h = max(win.minimumHeight(), new_h + 2 * d.y())
        elif top:  new_h = max(win.minimumHeight(), new_h - 2 * d.y())

        screen = QApplication.primaryScreen().availableGeometry()
        win.setGeometry(
            screen.center().x() - new_w // 2,
            screen.center().y() - new_h // 2,
            new_w, new_h,
        )



# ── DBus service ─────────────────────────────────────────────────────────────

DBUS_SERVICE = "com.groqchat.App"
DBUS_PATH    = "/com/groqchat/App"


@ClassInfo({"D-Bus Interface": DBUS_SERVICE})
class ChatAdaptor(QDBusAbstractAdaptor):
    """Exports Show / Hide / Toggle over the session bus."""

    def __init__(self, window: "ChatWindow"):
        super().__init__(window)

    @Slot()
    def Show(self):
        self.parent().show_signal.emit()

    @Slot()
    def Hide(self):
        self.parent().hide_signal.emit()

    @Slot()
    def Toggle(self):
        self.parent().toggle_signal.emit()


def register_dbus_service(window: "ChatWindow") -> bool:
    bus = QDBusConnection.sessionBus()
    if not bus.isConnected():
        print("DBus session bus not available — DBus activation disabled.", file=sys.stderr)
        return False

    # Adaptor must be parented to the exported object
    ChatAdaptor(window)

    if not bus.registerService(DBUS_SERVICE):
        print(
            f"Could not register DBus service '{DBUS_SERVICE}': "
            f"{bus.lastError().message()}\n"
            "(Is another instance already running?)",
            file=sys.stderr,
        )
        return False

    bus.registerObject(
        DBUS_PATH,
        window,
        QDBusConnection.RegisterOption.ExportAdaptors,
    )
    print(f"DBus service registered: {DBUS_SERVICE}  path: {DBUS_PATH}")
    return True


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Groq GUI chat client")
    parser.add_argument("-m", "--model", default=DEFAULT_MODEL)
    parser.add_argument("-s", "--system", default=None, help="System prompt")
    parser.add_argument("--api-key", default=None)
    parser.add_argument(
        "--no-tray",
        action="store_true",
        help="Don't show system tray icon",
    )
    args = parser.parse_args()

    api_key = args.api_key or os.environ.get("GROQ_API_KEY")
    if not api_key:
        print("Error: No API key. Set GROQ_API_KEY or use --api-key.", file=sys.stderr)
        sys.exit(1)

    client = Groq(api_key=api_key)

    # Fetch available models from API
    print("Fetching available models...")
    available_models = fetch_available_models(client)
    print(f"Loaded {len(available_models)} models")

    app = QApplication(sys.argv)
    app.setApplicationName("Groq Chat")
    app.setQuitOnLastWindowClosed(False)

    window = ChatWindow(client, args.model, args.system, available_models)
    # Don't show window on startup - wait for DBus signal or tray click

    # DBus
    register_dbus_service(window)

    # System tray
    if not args.no_tray:
        tray_icon = QIcon.fromTheme("dialog-question")
        if tray_icon.isNull():
            # Fallback: create a simple colored icon
            from PySide6.QtGui import QPixmap, QPainter
            px = QPixmap(22, 22)
            px.fill(QColor("#89b4fa"))
            tray_icon = QIcon(px)

        tray = QSystemTrayIcon(tray_icon, app)
        tray_menu = QMenu()
        toggle_action = QAction("Toggle Chat", app)
        toggle_action.triggered.connect(window.toggle)
        tray_menu.addAction(toggle_action)
        tray_menu.addSeparator()
        quit_action = QAction("Quit", app)
        quit_action.triggered.connect(app.quit)
        tray_menu.addAction(quit_action)
        tray.setContextMenu(tray_menu)
        tray.setToolTip("Groq Chat")
        tray.activated.connect(
            lambda reason: window.toggle()
            if reason == QSystemTrayIcon.ActivationReason.Trigger
            else None
        )
        tray.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
