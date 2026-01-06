import structlog
from PySide6.QtCore import QMimeData, QPointF, QStringListModel, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QDrag, QMouseEvent, QPainter, QPixmap
from PySide6.QtWidgets import (
    QCompleter,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from tagstudio.core.query_lang.parser import Parser

logger = structlog.get_logger(__name__)


def all_operations():
    return [
        AndOperationDesc,
        OrOperationDesc,
        NotOperationDesc,
        RootOperation,
        PropertyOperationDesc,
    ]


def get_nth_item(layout: QLayout, needed_object_name: str | list[str], n: int) -> QWidget | None:
    """Get the nth item with the given object name from the layout."""
    if isinstance(needed_object_name, str):
        needed_object_name = [needed_object_name]
    count = 0
    for i in range(layout.count()):
        widget = layout.itemAt(i).widget()
        if widget is not None and widget.objectName() in needed_object_name:
            if count == n:
                return widget
            count += 1
    return None


class OperationDesc:
    in_preview = True
    max_inputs = 0
    min_inputs = 0
    show_text = True
    text = "ERROR"
    identifier = "ERROR"
    color = QColor(255, 0, 255)
    allow_recursion = True

    operations: list["OperationDesc | UserInput"] = []
    widget: "OperationView | None" = None
    parent_widget: "OperationView | None" = None

    def __init__(self, operations=None) -> None:
        # these are the inputs to this operation
        if operations is None:
            operations = []

        self.operations = operations
        if len(operations) < self.min_inputs:
            for _ in range(self.min_inputs - len(operations)):
                self.operations.append(UserInput())

    def get_widget(self, preview=False, parent=None, parent_view=None) -> "OperationView":
        if parent_view is not None:
            self.parent_widget = parent_view
        if self.widget is None:
            self.widget = OperationView(operation_desc=self, preview=preview, parent=parent)
        if self.widget.parent() != parent and parent is not None:
            logger.debug("Reparenting widget", old_parent=self.widget.parent(), new_parent=parent)
            self.widget.setParent(parent)
        return self.widget

    def to_text(self):
        op_texts = [op.to_text() for op in self.operations]
        clean_ops = [op for op in op_texts if op is not None]
        if len(clean_ops) == 0:
            return None
        # return f"( {self.identifier.join(
        #    ' ' + op.to_text() + ' ' for op in self.operations if op.to_text() is not None
        # )} )"
        if len(clean_ops) == 1:
            return clean_ops[0]
        return "( " + f" {self.identifier} ".join(clean_ops) + " )"


class AndOperationDesc(OperationDesc):
    in_preview = True
    max_inputs = -1  # No maximum
    min_inputs = 2
    show_text = True
    text = "AND"
    identifier = "and"
    color = QColor("#16B528")


class OrOperationDesc(OperationDesc):
    in_preview = True
    max_inputs = -1  # No maximum
    min_inputs = 2
    show_text = True
    text = "OR"
    identifier = "or"
    color = QColor("#FF8C00")


class NotOperationDesc(OperationDesc):
    in_preview = True
    max_inputs = 1
    min_inputs = 1
    show_text = True
    text = "NOT"
    color = QColor("#C81E1E")

    def to_text(self):
        t = self.operations[0].to_text()
        if t is None:
            return None
        return "( not " + t + " )"


class PropertyOperationDesc(OperationDesc):
    in_preview = True
    max_inputs = 2
    min_inputs = 2
    show_text = False
    color = QColor("#1E90FF")
    allow_recursion = False

    def to_text(self):
        if len(self.operations) != 2:
            return None
        t1 = self.operations[0].to_text()
        t2 = self.operations[1].to_text()
        if t1 is None or t2 is None:
            return None
        return f"{t1}:{t2}"


class RootOperation(OperationDesc):
    in_preview = False
    max_inputs = -1  # No maximum
    min_inputs = 1
    show_text = False
    text = "ROOT"
    identifier = ""
    color = QColor("#323232")


class UserInput:
    value: str = ""

    def __init__(self, value: str = ""):
        self.value = value

    def to_text(self):
        if self.value.strip() == "":
            return None
        v = self.value.strip()
        if v.startswith('"') and v.endswith('"'):
            v = v[1:-1]
        if " " in v:
            return f'"{v}"'
        return v


class UserInputLineEdit(QLineEdit):
    my_completer: QCompleter
    completer_string_list: QStringListModel

    def __init__(
        self,
        placeholder: QLabel,
        user_input: UserInput,
        index: int,
        parent: "OperationView",
    ):
        super().__init__(parent.content)
        self.parent_operation_view = parent
        self.placeholder = placeholder
        self.user_input = user_input
        self.index = index

        og_text = user_input.value
        self.setText(og_text)
        self.setMinimumSize(50, 20)
        self.setProperty("type", "UserInputLineEdit")

        # make line_edit not use up all available space, but be only as wide as its content
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.adjustSize()

        self.finished_input = False

        self.editingFinished.connect(self.finish_input)
        self.returnPressed.connect(self.return_pressed)
        self.textChanged.connect(self.text_updated)

        self.init_suggestions()
        self.update_suggestions()

    def finish_input(self):
        if self.finished_input:
            return
        self.finished_input = True
        self.user_input.value = self.text()
        new_placeholder = self.parent_operation_view.none_operation()
        new_placeholder.setText(self.user_input.value)
        self.placeholder = new_placeholder
        self.parent_operation_view.content_layout.replaceWidget(self, new_placeholder)
        self.setParent(None)
        self.deleteLater()

    def update_line_width(self):
        self.setFixedWidth(
            max(
                self.fontMetrics().horizontalAdvance(self.text()) + 10,
                50,
            )
        )

    def text_updated(self, new_text: str):
        self.update_line_width()
        self.adjustSize()
        self.user_input.value = new_text
        self.parent_operation_view.check_filled_positions()
        self.update_suggestions()

    def dragEnterEvent(self, event):  # noqa: N802
        # if a operationView is dragged into this input,
        # finish input and replace with operationView

        self.finish_input()
        OperationView.dragEnterEvent(self.parent_operation_view, event)

    def focusOutEvent(self, event):  # noqa: N802
        self.finish_input()

    def keyPressEvent(self, key_event):  # noqa: N802
        if key_event.key() == Qt.Key.Key_Escape:
            self.finish_input()
        elif (
            (key_event.key() == Qt.Key.Key_Space and self.text().count('"') != 1)
            or (self.text().count('"') == 1 and key_event.key() == Qt.Key.Key_QuoteDbl)
            or (key_event.key() == Qt.Key.Key_Colon and self.text().count('"') != 1)
        ):
            if key_event.key() == Qt.Key.Key_QuoteDbl:
                self.insert('"')

            lower_input = self.text().strip().lower()
            if key_event.key() == Qt.Key.Key_Colon:
                lower_input += ":"
            if lower_input == self.parent_operation_view.operation_desc.text.lower():
                # ignore this input, as it matches the operation name
                self.setText("")
                return

            self.finish_input_with_space(lower_input)
        elif key_event.key() == Qt.Key.Key_Backspace:
            if self.text() == "":
                # move focus to previous input if exists
                self.finish_input()
                self.parent_operation_view.focus_previous_input(self.placeholder)
            else:
                QLineEdit.keyPressEvent(self, key_event)
        else:
            QLineEdit.keyPressEvent(self, key_event)

    def finish_input_with_space(self, lower_input: str):
        # if it matches an operation name, create the operation in this position
        # if the new operation is in [or, and] and an input / operation before this
        # input exists, move it into the new operation as first input,
        # and delete it from current position
        if (
            lower_input in ["and", "or", "not"] or lower_input.endswith(":")
        ) and self.parent_operation_view.operation_desc.allow_recursion:
            new_op_desc: OperationDesc
            if lower_input == "and":
                new_op_desc = AndOperationDesc()
            elif lower_input == "or":
                new_op_desc = OrOperationDesc()
            elif lower_input == "not":
                new_op_desc = NotOperationDesc()
            elif lower_input.endswith(":"):
                new_op_desc = PropertyOperationDesc([UserInput(lower_input[:-1]), UserInput()])
            else:
                logger.error("Unknown operation input", input=lower_input)
                return

            # insert new operation at current position
            self.parent_operation_view.operation_desc.operations[self.index] = new_op_desc
            new_op_view = new_op_desc.get_widget(
                parent=self.parent(), parent_view=self.parent_operation_view
            )

            # check for existing operation/input before this one
            has_prev_op = False
            if self.index > 0 and lower_input in ["and", "or"]:
                has_prev_op = True
                prev_op = self.parent_operation_view.operation_desc.operations[self.index - 1]
                if len(new_op_desc.operations) == 0:
                    new_op_desc.operations.append(prev_op)
                else:
                    new_op_desc.operations[0] = prev_op
                logger.debug(
                    "Moving previous operation into new operation",
                    prev_op=prev_op,
                    new_op_desc=new_op_desc,
                )

                # remove from current position and add to new operation
                self.parent_operation_view.operation_desc.operations.pop(self.index - 1)

                # remove widget from layout
                # prev_widget = self.parent_operation_view.content_layout.itemAt(
                #    self.index
                #    + (1 if self.parent_operation_view.operation_desc.show_text else 0)
                #    - 1
                # ).widget()
                prev_widget = get_nth_item(
                    self.parent_operation_view.content_layout,
                    ["OperationView", "input_placeholder"],
                    self.index - 1,
                )
                if isinstance(prev_op, OperationDesc) and prev_widget != prev_op.get_widget():
                    logger.error(
                        "prev_widget got from index is not prev_op.get_widget()",
                        prev_widget=prev_widget,
                        prev_op_get_widget=prev_op.get_widget(),
                    )
                if prev_widget is not None:
                    if self.parent_operation_view.content_layout.indexOf(prev_widget) == -1:
                        logger.error(
                            "Previous widget to move not found in layout",
                            index=self.index - 1,
                            index_in_layout=self.index
                            + (1 if self.parent_operation_view.operation_desc.show_text else 0)
                            - 1,
                        )
                    self.parent_operation_view.content_layout.removeWidget(prev_widget)
                    prev_widget.setParent(None)

                    # new_op_view.content_layout.itemAt(
                    #    1 if new_op_desc.show_text else 0
                    # ).widget().setParent(None)
                    # new_op_view.content_layout.itemAt(
                    #    1 if new_op_desc.show_text else 0
                    # ).widget().deleteLater()
                    to_del = get_nth_item(
                        new_op_view.content_layout,
                        ["OperationView", "input_placeholder"],
                        0,
                    )
                    new_op_view.content_layout.replaceWidget(
                        to_del,
                        prev_widget,
                    )
                    if to_del is not None:
                        new_op_view.content_layout.removeWidget(to_del)
                        to_del.setParent(None)
                        to_del.deleteLater()
                    else:
                        logger.error(
                            "Could not find placeholder to delete in new operation view",
                            new_op_view=new_op_view,
                        )

                    # new_op_view.content_layout.insertWidget(
                    #    1 if new_op_desc.show_text else 0, prev_widget
                    # )
                    prev_widget.setParent(new_op_view.content)
                    if isinstance(prev_op, OperationDesc):
                        prev_op.parent_widget = new_op_view

                    logger.debug(
                        "Moved previous widget into new operation",
                        index=self.index - 1,
                        index_in_layout=self.index
                        + (1 if self.parent_operation_view.operation_desc.show_text else 0)
                        - 1,
                    )
                else:
                    logger.error(
                        "Previous widget to move not found",
                        index=self.index - 1,
                        index_in_layout=self.index
                        + (1 if self.parent_operation_view.operation_desc.show_text else 0)
                        - 1,
                    )
                self.index -= 1  # adjust index due to pop

            # if PropertyOperationDesc, no previous op handling needed
            if lower_input.endswith(":"):
                has_prev_op = True

            self.parent_operation_view.content_layout.replaceWidget(self, new_op_view)
            self.setParent(None)
            self.deleteLater()
            self.parent_operation_view.check_filled_positions()
            if has_prev_op:
                # focus the new operation's second input
                new_op_view.focus_next_input(
                    # new_op_view.content_layout.itemAt(1 if new_op_desc.show_text else 0).widget()
                    get_nth_item(
                        new_op_view.content_layout,
                        ["OperationView", "input_placeholder"],
                        0,
                    )
                )
            else:
                new_op_view.focus_next_input(None)
            return

        self.finish_input()
        self.parent_operation_view.focus_next_input(self.placeholder)

    def showEvent(self, event):  # noqa: N802
        self.update_line_width()
        self.setFocus()
        self.selectAll()

    def return_pressed(self):
        self.finish_input()
        self.parent_operation_view.propagate_return_pressed()

    def update_suggestions(self):
        # Use QCompleter for native suggestions
        start_suggestions = [
            "mediatype:",
            "filetype:",
            "path:",
            "tag:",
            "tag_id:",
            "special:untagged",
        ]

        start_suggestions = [s for s in start_suggestions if s.startswith(self.text())]

        if self.text().startswith("tag:"):
            start_suggestions += [
                f'tag:"{tag}"'
                for tag in ["rock", "pop", "jazz", "classical", "electronic"]
                if f'tag:"{tag}"'.startswith(self.text())
            ]
        if self.text().startswith("tag_id:"):
            start_suggestions += [self.text() + str(i) for i in range(0, 10)]

        self.completer_string_list.setStringList(start_suggestions)

    def init_suggestions(self):
        self.completer_string_list = QStringListModel()
        self.my_completer = QCompleter(self.completer_string_list, self)
        self.my_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.my_completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.setCompleter(self.my_completer)

        rec = self.rect()
        # expand the rect downwards to show more suggestions
        rec.setHeight(rec.height() + 100)
        rec.setWidth(rec.width() + 100)
        self.my_completer.setCompletionPrefix("")
        self.my_completer.complete(rec)


class OperationView(QWidget):
    operation_desc: OperationDesc

    def __init__(self, operation_desc: OperationDesc, preview: bool, parent=None):
        super().__init__(parent)
        self.operation_desc = operation_desc
        self.operation_desc.widget = self
        self.preview = preview
        self.setObjectName("OperationView")

        # drag and drop support
        self.setAcceptDrops(not preview)

        # do not unnecessarily expand to fill available space
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)

        # Outer layout (no styling here)
        outer_layout = QHBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        # Inner widget that actually gets the green background
        self.content = QWidget(self)

        # self.content_layout = QHBoxLayout(self.content)
        self.content_layout = QHBoxLayout(self.content)
        self.content_layout.setContentsMargins(8, 4, 8, 4)
        self.content_layout.setSpacing(6)

        self.set_style_transparent(False)
        self.content.setProperty("type", "OperationViewContent")
        self.setProperty("type", "OperationView")

        outer_layout.addWidget(self.content)

        self.render_operation()

    def render_operation(self):
        if self.operation_desc.show_text:
            label = QLabel(self.operation_desc.text, self.content)
            label.setProperty("type", "OperationLabel")
            self.content_layout.addWidget(label)

        for op in self.operation_desc.operations:
            if not isinstance(op, UserInput):
                op_view = op.get_widget(parent=self.content, parent_view=self)
                self.content_layout.addWidget(op_view)
            else:
                placeholder = self.none_operation()
                placeholder.setText(op.value)
                self.content_layout.addWidget(placeholder)

    def none_operation(self):
        placeholder = QLabel(self.content)
        placeholder.setFixedSize(50, 20)
        placeholder.setObjectName("input_placeholder")

        # when the text changes, adjust size to fit content
        def adjust_size_to_content():
            placeholder.setFixedWidth(
                max(
                    placeholder.fontMetrics().horizontalAdvance(placeholder.text()) + 10,
                    50,
                )
            )
            placeholder.adjustSize()

        def set_text(text: str):
            QLabel.setText(placeholder, text)
            adjust_size_to_content()

        placeholder.setText = set_text
        placeholder.setText("")

        # onclick event, make, that the user can input value
        # (see UserInput() object, set value there).

        # Get index in operations list by finding placeholder in content_layout
        # and mapping to operations list
        def handle_input_click(click_event: QMouseEvent):
            click_event.accept()
            nonlocal placeholder

            holder = placeholder.parent().parent()
            if not isinstance(holder, OperationView):
                logger.error("Placeholder's grandparent is not OperationView", parent=holder)
                return

            index = holder.content_layout.indexOf(placeholder)
            if holder.operation_desc.show_text:
                index -= 1  # Adjust for label
            if index < 0 or index >= len(holder.operation_desc.operations):
                logger.error(
                    "Clicked placeholder index out of bounds",
                    index=index,
                    text_adjusted=holder.operation_desc.show_text,
                )
                return
            user_input = holder.operation_desc.operations[index]
            if not isinstance(user_input, UserInput):
                logger.error("Clicked placeholder does not correspond to UserInput", index=index)
                return

            # Create an qLineEdit over the placeholder, and when enter is pressed or focus is lost,
            # set the value and remove the qLineEdit
            line_edit = UserInputLineEdit(placeholder, user_input, index, holder)

            holder.content_layout.replaceWidget(placeholder, line_edit)
            placeholder.setParent(None)
            placeholder.deleteLater()

        if not self.preview:
            placeholder.mousePressEvent = handle_input_click

        return placeholder

    def focus_next_input(self, current_element: QWidget | None) -> bool:
        """Focus the next input placeholder after the current_element.

        if it could not be found, return False. Otherwise, return True.
        """
        logger.debug("Focusing next input", current_element=current_element)
        if current_element is None:
            # current_index = 0 if self.operation_desc.show_text else -1
            current_index = self.content_layout.indexOf(
                get_nth_item(
                    self.content_layout,
                    ["OperationView", "input_placeholder"],
                    0,
                )
            )
        else:
            current_index = self.content_layout.indexOf(current_element)

            if current_index == -1:
                logger.error(
                    "Current element not found in content layout",
                    element=current_element,
                )
                return False

        for i in range(current_index + 1, self.content_layout.count()):
            widget = self.content_layout.itemAt(i).widget()
            logger.debug("Searching for next input", index=i, widget=widget)

            # if it's a placeholder, focus it
            if widget is not None and widget.objectName() == "input_placeholder":
                widget.mousePressEvent(
                    QMouseEvent(
                        QMouseEvent.Type.MouseButtonPress,
                        QPointF(0, 0),
                        Qt.MouseButton.LeftButton,
                        Qt.MouseButton.LeftButton,
                        Qt.KeyboardModifier.NoModifier,
                    )
                )
                logger.debug("Focused next input", index=i)
                return True

            # if it's an operation, try to focus its first input recursively
            elif widget is not None and isinstance(widget, OperationView):
                if widget.focus_next_input(None):
                    return True

        # if no match found, check parent
        if self.operation_desc.parent_widget is not None and isinstance(
            self.operation_desc.parent_widget, OperationView
        ):
            logger.debug("No next input found, checking parent operation view")
            return self.operation_desc.parent_widget.focus_next_input(self)
        logger.debug(
            "Am at top-level, no next input found",
            parent=self.operation_desc.parent_widget,
        )
        return False

    def focus_previous_input(self, current_element: QWidget | None) -> bool:
        """Focus the previous input placeholder before the current_element.

        if it could not be found, return False. Otherwise, return True.
        """
        logger.debug("Focusing previous input", current_element=current_element)
        if current_element is None:
            current_index = self.content_layout.count()
        else:
            current_index = self.content_layout.indexOf(current_element)

            if current_index == -1:
                logger.error(
                    "Current element not found in content layout",
                    element=current_element,
                )
                return False

        for i in range(current_index - 1, -1, -1):
            widget = self.content_layout.itemAt(i).widget()

            # if it's a placeholder, focus it
            if (
                widget is not None
                # and isinstance(widget, QLabel)
                and widget.objectName() == "input_placeholder"
            ):
                widget.mousePressEvent(
                    QMouseEvent(
                        QMouseEvent.Type.MouseButtonPress,
                        QPointF(0, 0),
                        Qt.MouseButton.LeftButton,
                        Qt.MouseButton.LeftButton,
                        Qt.KeyboardModifier.NoModifier,
                    )
                )
                return True

            # if it's an operation, try to focus its last input recursively
            elif widget is not None and isinstance(widget, OperationView):
                if widget.focus_previous_input(None):
                    return True

        # if no match found, check parent
        if self.operation_desc.parent_widget is not None and isinstance(
            self.operation_desc.parent_widget, OperationView
        ):
            logger.debug("No previous input found, checking parent operation view")
            return self.operation_desc.parent_widget.focus_previous_input(self)
        logger.debug(
            "Am at top-level, no previous input found",
            parent=self.operation_desc.parent_widget,
        )
        return False

    def mouseMoveEvent(self, event):  # noqa: N802
        if event.buttons() == Qt.MouseButton.LeftButton:
            self.start_drag()

    def get_pix_map(self) -> QPixmap:
        logger.debug("Generating pixmap for drag preview")
        pix = self.grab()
        dpr = getattr(self, "devicePixelRatioF", lambda: 1.0)()
        border_radius = 6  # magic number from stylesheet
        radius = border_radius * dpr

        mask = QPixmap(pix.size())
        mask.fill(Qt.GlobalColor.transparent)

        painter = QPainter(mask)
        painter.setBrush(Qt.GlobalColor.white)
        painter.drawRoundedRect(pix.rect(), radius, radius)
        painter.end()

        pix.setMask(mask.createMaskFromColor(Qt.GlobalColor.transparent, Qt.MaskMode.MaskInColor))
        return pix

    def start_drag(self):
        drag = QDrag(self)
        mime_data = QMimeData()
        drag.setMimeData(mime_data)

        pix_map = self.get_pix_map()

        drag.setPixmap(pix_map)

        # to set hotspot, calculate cursor position relative to widget
        cursor_pos = QCursor.pos()
        widget_pos = self.mapToGlobal(self.rect().topLeft())
        relative_pos = cursor_pos - widget_pos
        drag.setHotSpot(relative_pos)

        # make self gray out while dragging
        if not self.preview:
            self.set_style_transparent(True)

        drag.exec(Qt.DropAction.MoveAction)
        self.set_style_transparent(False)

    def set_style_transparent(self, transparent: bool):
        self.content.setStyleSheet(
            f"""
            QWidget[type='OperationViewContent'] {{
                background-color: rgba(
                    {self.operation_desc.color.red()},
                    {self.operation_desc.color.green()},
                    {self.operation_desc.color.blue()},
                    {128 if transparent else 255}
                );
                border-radius: 6px;
            }}
            """
        )

        for i in range(self.content_layout.count()):
            widget = self.content_layout.itemAt(i).widget()
            if widget is not None and isinstance(widget, OperationView):
                widget.set_style_transparent(transparent)

    def dragEnterEvent(self, event):  # noqa: N802
        if not self.operation_desc.allow_recursion:
            event.setDropAction(Qt.DropAction.IgnoreAction)
        else:
            event.setDropAction(Qt.DropAction.MoveAction)
        event.accept()

    def dropEvent(self, event):  # noqa: N802
        if not self.operation_desc.allow_recursion:
            event.setDropAction(Qt.DropAction.IgnoreAction)
            event.accept()
            return
        event.accept()

        source_widget = event.source()
        if source_widget is None or not isinstance(source_widget, OperationView):
            return

        source_operation = source_widget.operation_desc

        if source_operation.get_widget() != source_widget:
            logger.error("Source widget does not match operation's widget")
            return

        # v3: get the drop position, the user hovered over
        if not self.content.geometry().contains(self.content.mapFromGlobal(QCursor.pos())):
            logger.error("Drop position is outside content area")
            return
        drop_placeholder = self.content.childAt(self.content.mapFromGlobal(QCursor.pos()))
        if drop_placeholder is None:
            logger.error("to Drop placeholder not found [a]")
            return
        drop_index = self.content_layout.indexOf(drop_placeholder)
        if drop_index == -1:
            logger.error("to Drop index not found [b] (child has disabled drag/drop?)")
            return
        if self.operation_desc.show_text:
            drop_index -= 1  # Adjust for label
        if drop_index < 0:
            logger.error("to Drop index negative after adjustment [c]")
            return
        logger.info("to Drop index found", dropIndex=drop_index)

        ### check for circular references
        ancestor = self.operation_desc
        while ancestor is not None:
            if ancestor == source_operation:
                logger.error("Cannot drop operation into one of its descendants")
                return
            ancestor = (
                ancestor.parent_widget.operation_desc
                if (ancestor.parent_widget and isinstance(ancestor.parent_widget, OperationView))
                else None
            )

        ### remove from source
        if not source_widget.preview:
            source_operation_holder = source_operation.parent_widget
            soi = source_operation_holder.operation_desc.operations.index(source_operation)
            if soi == -1:
                logger.error("Source operation not found in parent's operations")
                return

            source_operation_holder.operation_desc.operations[soi] = UserInput()
            none_op = source_operation_holder.none_operation()
            source_operation_holder.content_layout.replaceWidget(source_widget, none_op)

            source_operation.get_widget().setParent(None)
        else:
            # In preview mode, clone the operation
            source_operation = type(source_operation)()
            logger.info("Cloning operation for drop", operation=source_operation)

        source_operation.get_widget(parent=self.content, parent_view=self)

        # v3: and insert on drop position.
        self.content_layout.replaceWidget(
            drop_placeholder, source_operation.get_widget(parent=self.content, parent_view=self)
        )
        drop_placeholder.setParent(None)
        drop_placeholder.deleteLater()
        self.operation_desc.operations[drop_index] = source_operation

        self.check_filled_positions()
        if not source_widget.preview:
            source_operation_holder = source_operation.parent_widget
            source_operation_holder.check_filled_positions()

    def check_filled_positions(self):
        # After insertion, if all positions are filled, but operationDesc.max_inputs is not reached,
        # create a new one at the end
        if (
            self.operation_desc.max_inputs == -1
            or len(self.operation_desc.operations) < self.operation_desc.max_inputs
        ) and (
            not any(
                (isinstance(op, UserInput) and op.value.strip() == "")
                for op in self.operation_desc.operations
            )
        ):
            self.operation_desc.operations.append(UserInput())
            self.content_layout.addWidget(self.none_operation())

        # After deletion, while last two positions are empty, and
        # operationDesc.min_inputs is not reached, remove the last one
        while (
            len(self.operation_desc.operations) >= 2
            and (len(self.operation_desc.operations) > self.operation_desc.min_inputs)
            and (
                self.operation_desc.operations[-1] is None
                or (
                    isinstance(self.operation_desc.operations[-1], UserInput)
                    and self.operation_desc.operations[-1].value.strip() == ""
                )
            )
            and (
                self.operation_desc.operations[-2] is None
                or (
                    isinstance(self.operation_desc.operations[-2], UserInput)
                    and self.operation_desc.operations[-2].value.strip() == ""
                )
            )
        ):
            # remove last one
            logger.debug("Removing last empty operation/input")
            self.operation_desc.operations.pop()
            last_widget = self.content_layout.itemAt(self.content_layout.count() - 1).widget()
            if last_widget is not None:
                self.content_layout.removeWidget(last_widget)
                last_widget.setParent(None)
                last_widget.deleteLater()
            else:
                logger.error("Last widget to remove not found")

    def propagate_return_pressed(self):
        if self.operation_desc.parent_widget is not None and isinstance(
            self.operation_desc.parent_widget, OperationView
        ):
            self.operation_desc.parent_widget.propagate_return_pressed()
        else:
            # at top-level, emit returnPressed signal
            parent_widget = self.parent()
            if isinstance(parent_widget, BetterSearchField):
                parent_widget.returnPressed.emit()

    def __repr__(self):
        return (
            f"<OperationView {self.operation_desc.text} children "
            f"{len(self.operation_desc.operations)} at {hex(id(self))}>"
        )


class SearchFieldPreviews(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, on=True)
        self.setProperty("type", "SearchFieldPreviews")

        self.setLayout(QHBoxLayout(self))
        self.setLayout(self.layout())

        self.setAcceptDrops(True)

        # Add operation previews
        for operation in all_operations():
            if not operation.in_preview:
                continue
            op_view = operation().get_widget(preview=True, parent=self, parent_view=self)
            self.layout().addWidget(op_view)

        # Add trashcan overlay (hidden by default)
        self.trashcan_overlay = QLabel(self)
        self.trashcan_overlay.setObjectName("trashcan_overlay")
        self.trashcan_overlay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.trashcan_overlay.setStyleSheet("background: rgba(255,0,0,0.4); border-radius: 6px;")
        self.trashcan_overlay.setVisible(False)
        self.trashcan_overlay.raise_()

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        # Overlay covers everything
        self.trashcan_overlay.setGeometry(self.rect())

    def dragEnterEvent(self, event):  # noqa: N802
        self.trashcan_overlay.setVisible(True)
        self.trashcan_overlay.setGeometry(self.rect())
        event.accept()

    def dragLeaveEvent(self, event):  # noqa: N802
        self.trashcan_overlay.setVisible(False)
        event.accept()

    def dropEvent(self, event):  # noqa: N802
        event.accept()
        self.trashcan_overlay.setVisible(False)

        # delete the dropped widget, as if this is also a trash can
        source_widget = event.source()
        if source_widget is None or not isinstance(source_widget, OperationView):
            logger.warn("Dropped source is not an OperationView")
            return

        source_operation = source_widget.operation_desc

        if source_operation.get_widget() != source_widget:
            logger.error("Source widget does not match operation's widget")
            return

        if isinstance(source_operation, RootOperation):
            logger.warn("Cannot delete RootOperation")
            return

        if source_operation.parent_widget != self:
            # delete the source_operation's widget
            source_operation.parent_widget.content_layout.replaceWidget(
                source_widget, source_operation.parent_widget.none_operation()
            )
            source_widget.setParent(None)
            source_widget.deleteLater()

            # delete the source_operation from the parent
            source_operation.parent_widget.operation_desc.operations[
                source_operation.parent_widget.operation_desc.operations.index(source_operation)
            ] = UserInput()

            source_operation.parent_widget.check_filled_positions()


class BetterSearchField(QWidget):
    textChanged: Signal = Signal(str)  # noqa: N815
    returnPressed: Signal = Signal()  # noqa: N815

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.setLayout(QVBoxLayout(self))
        self.setLayout(self.layout())

        self.setStyleSheet(
            """
        QLineEdit[type="UserInputLineEdit"] {
            background-color: white;
            color: black;
            border: 2px dashed gray;
            border-radius: 4px;
            padding: 0px;
            margin: 0px;
        }
        #input_placeholder {
            background-color: white;
            color: black;
            border: 2px dashed gray;
            border-radius: 4px;
            padding: 0px;
            margin: 0px;
        }
        QLabel[type="OperationLabel"] {
            color: white;
        }
        
        QWidget[type="SearchFieldPreviews"]{
            border-radius: 6px;
            background-color: #222222;
        }
        """
        )
        self.root_operation_view = RootOperation().get_widget(
            preview=False, parent=self, parent_view=self
        )
        self.layout().addWidget(self.root_operation_view)
        self.layout().addWidget(SearchFieldPreviews(self))

    def setText(self, text: str):  # noqa: N802
        # Set the text in the search field
        logger.warning("setText not implemented yet", text=text)

        # do nothing if text is the same
        if text == self.text():
            return
        pass

    def text(self) -> str:
        # Get the current text from the search field
        t = self.root_operation_view.operation_desc.to_text()
        logger.debug("Getting text from search field", text=t)
        if t is None:
            return ""

        parser = Parser(t)
        logger.info("Parsed text from search field", parsed=parser.parse())

        return t
