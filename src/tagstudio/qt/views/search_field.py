from dataclasses import dataclass
from typing import Literal, cast

import structlog
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QWidget, QLineEdit, QSizePolicy, QLabel
from PySide6.QtCore import Signal, QSize, Qt

from tagstudio.core.query_lang.ast import AST
from tagstudio.core.query_lang.parser import Parser

from PySide6.QtWidgets import QHBoxLayout

logger = structlog.get_logger(__name__)


class SearchInputType:
    color: QColor


@dataclass(frozen=True)
class LiteralInput(SearchInputType):
    value: str
    color = QColor.fromRgb(0x32A852)


@dataclass(frozen=True)
class AssignmentInput(SearchInputType):
    key: str
    value: str
    color = QColor.fromRgb(0x3273A8)


@dataclass(frozen=True)
class OperationInput(SearchInputType):
    operation: Literal["AND", "OR", "NOT"]
    operands: list["BetterSearchField"]
    color = QColor.fromRgb(0xA83232)


@dataclass(frozen=True)
class SearchFieldToken:
    value: str
    type: Literal["string", "quoted_string"]


PRECEDENCE = [
    "NOT",
    "AND",
    "OR",
]


class BetterSearchFieldView(QWidget):
    textChanged: Signal = Signal(str)
    returnPressed: Signal = Signal()

    operation: SearchInputType | None = None  # "AND" | "OR" | None

    def __init__(self, parent=None, data: SearchInputType | None = None, focus: bool = False):
        super().__init__(parent)

        self.setMinimumSize(QSize(50, 40))
        # Allow height to expand when needed
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.MinimumExpanding)

        self.setLayout(QHBoxLayout(self))
        self.layout().setContentsMargins(6, 6, 6, 6)
        self.layout().setSpacing(6)

        # Container for the actual view with proper height expansion
        self.actual_view_container = QWidget(self)
        self.actual_view_container.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.MinimumExpanding
        )
        self.actual_view = QHBoxLayout(self.actual_view_container)
        self.actual_view.setContentsMargins(0, 0, 0, 0)
        self.actual_view.setSpacing(6)
        self.actual_view.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.layout().addWidget(self.actual_view_container)

        # Input field - initially hidden, shown on demand
        self.inputField = QLineEdit(self)
        self.inputField.setMinimumSize(QSize(10, 32))
        self.inputField.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.inputField.setStyleSheet("""
            QLineEdit {
                border: 1px solid #999;
                border-radius: 4px;
                padding: 4px 8px;
                background-color: white;
                color: black;
            }
            QLineEdit:focus {
                border: 2px solid #0078d4;
            }
        """)
        self.inputField.textChanged.connect(self.textChanged)
        self.inputField.returnPressed.connect(self.returnPressed)
        # _text_changed connection is handled in subclass
        self.inputField.hide()  # Hide by default
        self.layout().addWidget(self.inputField)

        self.focus_when_shown = focus
        self._updateStyle()

        if data is not None:
            self.operation = data
            self.display()
        else:
            # Show input field initially if no data
            self.inputField.show()

    def _updateStyle(self):
        """Update the widget style including background color"""
        if self.operation is not None:
            color = self.operation.color
            # Lighten the color for better visibility
            bg_color = f"rgba({color.red()}, {color.green()}, {color.blue()}, 0.2)"
            border_color = f"rgb({color.red()}, {color.green()}, {color.blue()})"
            self.setStyleSheet(f"""
                QWidget {{
                    border: 2px solid {border_color};
                    border-radius: 6px;
                    background-color: {bg_color};
                }}
            """)
        else:
            self.setStyleSheet("""
                QWidget {
                    border: 2px solid #ccc;
                    border-radius: 6px;
                    background-color: #f8f8f8;
                }
            """)

    def mousePressEvent(self, event):
        """Show input field when clicking on the widget"""
        super().mousePressEvent(event)
        if not self.inputField.isVisible():
            self.inputField.show()
            self.inputField.setFocus()

    def focusOutEvent(self, event):
        """Hide input field when it loses focus and is empty"""
        super().focusOutEvent(event)
        if self.inputField.isVisible() and not self.inputField.text().strip():
            self.inputField.hide()

    def showEvent(self, event):
        super().showEvent(event)
        if self.focus_when_shown:
            self.inputField.show()
            self.inputField.setFocus()
            self.focus_when_shown = False

    def display(self):
        if self.operation is None:
            # No operation to display, just update style
            self._updateStyle()
            return
        self.clear()

        # Recreate widgets from operation data to avoid deleted widget issues
        match self.operation:
            case LiteralInput(value=value):
                label = QLabel(value, self.actual_view_container)
                label.setMinimumHeight(28)
                label.setStyleSheet("""
                    QLabel {
                        padding: 6px 12px;
                        border: 2px solid #2d8a3d;
                        border-radius: 4px;
                        background-color: #e8f5e9;
                        color: #1b5e20;
                        font-weight: 600;
                    }
                """)
                label.setCursor(Qt.CursorShape.PointingHandCursor)
                self.actual_view.addWidget(label)
            case AssignmentInput(key=key, value=value):
                # Show as clickable labels
                key_label = QLabel(key, self.actual_view_container)
                key_label.setMinimumHeight(28)
                key_label.setStyleSheet("""
                    QLabel {
                        padding: 6px 12px;
                        border: 2px solid #0078d4;
                        border-radius: 4px;
                        background-color: #e3f2fd;
                        color: #01579b;
                        font-weight: 600;
                    }
                """)
                key_label.setCursor(Qt.CursorShape.PointingHandCursor)

                colon_label = QLabel(":", self.actual_view_container)
                colon_label.setStyleSheet(
                    "padding: 0 4px; font-weight: bold; font-size: 16px; color: black;"
                )

                value_label = QLabel(value, self.actual_view_container)
                value_label.setMinimumHeight(28)
                value_label.setStyleSheet("""
                    QLabel {
                        padding: 6px 12px;
                        border: 2px solid #0078d4;
                        border-radius: 4px;
                        background-color: #e3f2fd;
                        color: #01579b;
                        font-weight: 600;
                    }
                """)
                value_label.setCursor(Qt.CursorShape.PointingHandCursor)

                self.actual_view.addWidget(key_label)
                self.actual_view.addWidget(colon_label)
                self.actual_view.addWidget(value_label)
            case OperationInput(operation=op, operands=operands):
                # Recreate child widgets from their stored data
                if op == "NOT":
                    # NOT always shows the keyword before its single operand
                    not_label = QLabel("NOT", self.actual_view_container)
                    not_label.setMinimumHeight(28)
                    not_label.setStyleSheet("""
                        QLabel {
                            padding: 6px 10px;
                            font-weight: bold;
                            font-size: 12px;
                            color: white;
                            background-color: #d32f2f;
                            border: 2px solid #b71c1c;
                            border-radius: 3px;
                        }
                    """)
                    self.actual_view.addWidget(not_label)
                    # NOT can only have one operand
                    if len(operands) > 0:
                        self.actual_view.addWidget(operands[0])
                else:
                    # AND/OR operations show separator between operands
                    for i, child_field in enumerate(operands):
                        if i > 0:
                            # Add operation separator between operands
                            sep_label = QLabel(op, self.actual_view_container)
                            sep_label.setMinimumHeight(28)
                            sep_label.setStyleSheet("""
                                QLabel {
                                    padding: 6px 10px;
                                    font-weight: bold;
                                    font-size: 12px;
                                    color: black;
                                    background-color: #fff59d;
                                    border: 2px solid #f9a825;
                                    border-radius: 3px;
                                }
                            """)
                            self.actual_view.addWidget(sep_label)

                        self.actual_view.addWidget(child_field)
            case _:
                logger.error("Unsupported SearchInputType", operation=self.operation)

        # Update background color via stylesheet
        self._updateStyle()

        # Update geometry to ensure proper size expansion
        self.updateGeometry()
        parent = self.parent()
        if parent and isinstance(parent, BetterSearchFieldView):
            parent.updateGeometry()

    def _text_changed(self, text: str):
        raise NotImplementedError()

    def setText(self, text: str):
        # Set the text in the search field
        pass

    def clear(self):
        # clear the actual_view widgets only
        while self.actual_view.count():
            item = self.actual_view.takeAt(0)
            widget = item.widget()
            if widget is not None and not isinstance(widget, BetterSearchField):
                widget.deleteLater()

    def text(self) -> str:
        # Return the current text in the search field
        return self.inputField.text()


class BetterSearchField(BetterSearchFieldView):
    def __init__(self, parent=None, data: SearchInputType | None = None, focus: bool = False):
        super().__init__(parent=parent, data=data, focus=focus)
        # Connect _text_changed in subclass where it's actually implemented
        self.inputField.textChanged.connect(self._text_changed)

    def _text_changed(self, text: str):
        # this doesn't need to parse the ast, to create the view, because this is for live inputting, and should just feel good to type in
        logger.debug("Search field text changed", text=text)
        # split by spaces and quoted strings (make a list of SearchFieldToken)
        tokens: list[SearchFieldToken] = self.parse_text_to_tokens(text)
        ends_with_space = len(text) > 0 and text[-1].isspace()
        logger.debug("Parsed tokens", tokens=tokens, ends_with_space=ends_with_space)

        if len(tokens) == 0:
            return
        current_token_upper = tokens[0].value.upper()
        if ends_with_space and len(tokens) == 1 and current_token_upper not in PRECEDENCE:
            # if len(self.content) == 0 and self.operation is None:
            if self.operation is None:
                # create a literal input
                self.clear()
                self.operation = OperationInput(
                    operation="AND",
                    operands=[
                        #    LiteralInput(tokens[0].value),
                        BetterSearchField(parent=self, data=LiteralInput(tokens[0].value)),
                    ],
                )
                self.display()
                self.inputField.clear()
                return
            # elif len(self.content) == 0 and isinstance(self.operation, LiteralInput):
            elif isinstance(self.operation, LiteralInput):
                # create an AND operation with the existing literal and the new one
                self.operation = OperationInput(
                    operation="AND",
                    operands=[
                        # self.operation,
                        # LiteralInput(tokens[0].value),
                        BetterSearchField(parent=self, data=self.operation),
                        BetterSearchField(parent=self, data=LiteralInput(tokens[0].value)),
                    ],
                )
                self.display()
                self.inputField.clear()
                return
            elif isinstance(self.operation, OperationInput):
                self.operation.operands.append(
                    # LiteralInput(tokens[0].value)
                    BetterSearchField(parent=self, data=LiteralInput(tokens[0].value))
                )
                self.display()
                self.inputField.clear()
                return
        elif ends_with_space and len(tokens) == 1 and current_token_upper in PRECEDENCE:
            if isinstance(self.operation, OperationInput):
                # if self is an operation check what if self, of the operation has precedence
                if PRECEDENCE.index(current_token_upper) > PRECEDENCE.index(
                    self.operation.operation
                ):
                    # create a new operation with self as operand
                    self.operation = OperationInput(
                        operation=cast(Literal["AND", "OR", "NOT"], current_token_upper),
                        operands=[BetterSearchField(parent=self, data=self.operation)],
                    )
                    self.display()
                    self.inputField.clear()
                    return
                else:
                    # add the operation to self
                    if current_token_upper == "NOT":
                        # add new operation - NOT can only have one operand
                        self.operation.operands.append(
                            BetterSearchField(
                                parent=self,
                                data=OperationInput(
                                    operation="NOT",
                                    operands=[],
                                ),
                                focus=True,
                            )
                        )
                    else:
                        # take the last operand and make a new operation with it
                        if len(self.operation.operands) == 0:
                            logger.error("No operands to apply operation to")
                            return
                        last_operand = self.operation.operands.pop()
                        new_operation = OperationInput(
                            operation=cast(Literal["AND", "OR"], current_token_upper),
                            operands=[last_operand],
                        )
                        self.operation.operands.append(
                            BetterSearchField(parent=self, data=new_operation, focus=True)
                        )
                    self.display()
                    self.inputField.clear()
                    return

    def parse_text_to_tokens(self, text: str) -> list[SearchFieldToken]:
        tokens: list[SearchFieldToken] = []
        current_token = ""
        in_quotes = False
        quote_char = ""
        i = 0
        while i < len(text):
            char = text[i]
            if in_quotes:
                if char == quote_char:
                    in_quotes = False
                    tokens.append(SearchFieldToken(current_token, "quoted_string"))
                    current_token = ""
                else:
                    current_token += char
            else:
                if char in ('"', "'"):
                    if current_token:
                        tokens.append(SearchFieldToken(current_token, "string"))
                        current_token = ""
                    in_quotes = True
                    quote_char = char
                elif char.isspace():
                    if current_token:
                        tokens.append(SearchFieldToken(current_token, "string"))
                        current_token = ""
                else:
                    current_token += char
            i += 1
        if current_token:
            tokens.append(SearchFieldToken(current_token, "string"))
        return tokens


def localTest():
    parser = Parser("a and a or b")
    dat: AST = parser.parse()
    logger.info("Parsed AST", ast=dat)


if __name__ == "__main__":
    localTest()
