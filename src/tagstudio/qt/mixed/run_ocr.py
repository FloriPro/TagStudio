import time
from collections.abc import Callable
from typing import TYPE_CHECKING, override

import numpy as np
import structlog
from PIL import Image
from PySide6 import QtGui
from PySide6.QtCore import Qt, QThread
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from tagstudio.core.library.alchemy.library import Library

if TYPE_CHECKING:
    from tagstudio.qt.ts_qt import QtDriver

logger = structlog.get_logger(__name__)


class OcrRunmodalview(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("OCR Run")
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setMinimumSize(400, 300)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMinimizeButtonHint)

        self.__root_layout = QVBoxLayout(self)
        self.setContentsMargins(6, 6, 6, 6)

        self.__title_widget = QLabel("OCR Run")
        self.__title_widget.setObjectName("title")
        self.__title_widget.setWordWrap(True)
        self.__title_widget.setStyleSheet("font-weight:bold;font-size:14px;padding-top: 6px")
        self.__title_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.__desc_widget = QLabel()
        self.__desc_widget.setObjectName("descriptionLabel")
        self.__desc_widget.setWordWrap(True)
        self.__desc_widget.setText(
            """Uses the selected OCR to extract text from all images
            They will be stored in a new created OCR field.
            This may take a while depending on the number of images and their sizes.
            Images with already existing OCR data will be skipped.""",
        )
        self.__desc_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # OCR selection
        self.__ocr_selection_widget = QWidget()
        self.__ocr_selection_layout = QHBoxLayout(self.__ocr_selection_widget)
        self.__ocr_selection_layout.setContentsMargins(0, 0, 0, 0)
        self.__ocr_selection_layout.setSpacing(6)

        # process bar
        self.__progress_bar = QProgressBar()
        self.__progress_bar.setMinimum(0)
        self.__progress_bar.setMaximum(-1)
        self.__progress_bar.setValue(0)
        self.__progress_bar.setTextVisible(True)
        self.__progress_bar.setDisabled(True)
        self._set_progress(0)
        self.__progress_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # start button
        self.__start_button = QPushButton("Start OCR")
        self.__start_button.setObjectName("startButton")
        self.__start_button.clicked.connect(self._start_ocr_process)

        self.__stop_button = QPushButton("Stop OCR")
        self.__stop_button.setObjectName("stopButton")
        self.__stop_button.clicked.connect(self._run_stop)
        self.__stop_button.setDisabled(True)

        self.__root_layout.addWidget(self.__title_widget)
        self.__root_layout.addWidget(self.__desc_widget)
        self.__root_layout.addSpacing(12)
        self.__root_layout.addWidget(self.__ocr_selection_widget)
        self.__root_layout.addSpacing(12)
        self.__root_layout.addWidget(self.__progress_bar)
        self.__root_layout.addSpacing(12)
        self.__root_layout.addWidget(self.__start_button)
        self.__root_layout.addWidget(self.__stop_button)
        self.__root_layout.addSpacing(12)

        ## add event listeners

    def _set_ocr_available(self, ocr_names: list[type["OCRRunner"]]):
        self._selectedOcr = ocr_names[0] if len(ocr_names) > 0 else None
        for ocr in ocr_names:
            btn = self.__create_ocr_button(ocr)
            self.__ocr_selection_layout.addWidget(btn)

    def __create_ocr_button(self, ocr: type["OCRRunner"]) -> QPushButton:
        btn = QPushButton(ocr.name)
        btn.setCheckable(True)
        btn.setChecked(ocr == self._selectedOcr)

        def on_click(checked: bool):
            if checked:
                self._selectedOcr = ocr
                # uncheck other buttons
                for i in range(self.__ocr_selection_layout.count()):
                    w: QWidget = self.__ocr_selection_layout.itemAt(i).widget()
                    if not isinstance(w, QPushButton):
                        continue
                    if w != btn:
                        # noinspection PyUnresolvedReferences
                        w.setChecked(False)
            else:
                # prevent unchecking
                btn.setChecked(True)

        btn.clicked.connect(on_click)
        return btn

    def _set_progress(self, value: int, eta_str: str | None = None):
        self.__progress_bar.setValue(value)
        percent = (
            (value / self.__progress_bar.maximum()) * 100
            if self.__progress_bar.maximum() > 0
            else 0
        )

        if (
            eta_str
            and value > 0
            and self.__progress_bar.maximum() > 0
            and value < self.__progress_bar.maximum()
        ):
            self.__progress_bar.setFormat(
                f"{value} / {self.__progress_bar.maximum()} ({percent:.2f}%)  {eta_str}"
            )
        else:
            self.__progress_bar.setFormat(
                f"{value} / {self.__progress_bar.maximum()} ({percent:.2f}%)"
            )

    def _set_max_progress(self, value: int):
        self.__progress_bar.setMaximum(value)

    def _start_ocr_process(self):
        raise NotImplementedError("OCR process function implemented yet.")

    def _run_stop(self):
        raise NotImplementedError("OCR stop function implemented yet.")

    def _no_ocr_installed(self):
        self.error_no_ocr = QLabel()
        self.error_no_ocr.setObjectName("errorNoTesseract")
        self.error_no_ocr.setWordWrap(True)
        self.error_no_ocr.setText(
            """
            TBD
            """
        )
        self.error_no_ocr.setTextFormat(Qt.TextFormat.RichText)
        self.error_no_ocr.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self.error_no_ocr.setOpenExternalLinks(True)
        self.error_no_ocr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_no_ocr.setStyleSheet("color: red; font-weight: bold;")
        self.__start_button.setDisabled(True)

        self.__root_layout.addWidget(self.error_no_ocr)

    def _start(self):
        self.__progress_bar.setDisabled(False)
        self.__start_button.setDisabled(True)
        self.__stop_button.setDisabled(False)
        for i in range(self.__ocr_selection_layout.count()):
            w: QWidget = self.__ocr_selection_layout.itemAt(i).widget()
            w.setDisabled(True)
        self.__desc_widget.setText("OCR process is running... Please wait.")

    def _stop(self):
        self.__progress_bar.setDisabled(True)
        self.__start_button.setDisabled(False)
        self.__stop_button.setDisabled(True)
        for i in range(self.__ocr_selection_layout.count()):
            w: QWidget = self.__ocr_selection_layout.itemAt(i).widget()
            w.setDisabled(False)

    def _finished(self):
        self.__desc_widget.setText("OCR process finished.")
        self._stop()


class OcrRunmodal(OcrRunmodalview):
    def __init__(self, library: "Library", driver: "QtDriver"):
        super().__init__()
        self.library = library
        self.driver = driver
        self.__ocrRunners: list[type[OCRRunner]] = [
            EasyOcrWorker,
            TesseractWorker,
        ]
        self._set_ocr_available(self.__ocrRunners)

    def _start_ocr_process(self):
        if not self.library:
            logger.error("No library loaded. Cannot run OCR.")
            return
        if self.library.storage_path is None:
            logger.error("Library storage path is None. Cannot run OCR.")
            return

        # get all images without ocr data
        entries = self.library.get_all_entries_without_ocr()
        self.total_images = len(entries)
        self._set_max_progress(self.total_images)
        self._progress_start_time = None
        self._progress_last_value = 0
        self._progress_last_time = None
        self._set_progress(0, None)
        logger.debug(f"Starting Thread OCR process for {self.total_images} images.")
        self._start()

        if self._selectedOcr is None:
            logger.error("No OCR method selected. Cannot run OCR.")
            return
        # self.selectedOcr is a class type, with the () we create an instance of it
        self.ocr_thread = self._selectedOcr()
        self.ocr_thread.set_data(entries, self.__progress_callback, self.library)
        self.ocr_thread.start()
        self.ocr_thread.finished.connect(self._on_ocr_finished)

    def __progress_callback(self, value):
        # ETA calculation in model
        now = time.time()
        if value == 0 or self.total_images == 0:
            self._progress_start_time = now
            self._progress_last_value = value
            self._progress_last_time = now
            eta_str = None
        else:
            if self._progress_start_time is None:
                self._progress_start_time = now
            elapsed = now - self._progress_start_time
            if value > 0 and value < self.total_images:
                avg_time_per_item = elapsed / value
                remaining = self.total_images - value
                eta_seconds = int(avg_time_per_item * remaining)
                eta_min, eta_sec = divmod(eta_seconds, 60)
                eta_str = f"ETA: {eta_min}m {eta_sec}s"
            else:
                eta_str = None
        self._set_progress(value, eta_str)

    def _run_stop(self):
        if (
            hasattr(self, "ocr_thread")
            and (self.ocr_thread is not None)
            and self.ocr_thread.isRunning()
        ):
            logger.debug("Stopping OCR process as per user request.")
            self.ocr_thread.do_terminate = True

    def _on_ocr_finished(self):
        logger.debug("OCR process finished.")
        self._finished()
        self.ocr_thread = None

    @override
    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        logger.debug("Close event triggered for OCR Run Modal.")
        # If OCR thread exists and is running, terminate and wait for it
        self._run_stop()


class OCRRunner(QThread):
    name = "Unnamed OCR"
    library: "Library"
    entries: list
    update_progress_callback: Callable[[int], None]
    do_terminate: bool

    def set_data(self, entries, update_progress_callback, library: "Library"):
        self.library = library
        self.entries = entries
        self.update_progress_callback = update_progress_callback
        self.do_terminate = False


class TesseractWorker(OCRRunner):
    name = "Tesseract OCR"

    def __init__(self):
        super().__init__()

    def run(self):
        import pytesseract

        for i, entry in enumerate(self.entries):
            if self.do_terminate:
                logger.debug("OCR process terminated by user.")
                break
            entry_id = entry.id
            entry_path = self.library.library_dir / entry.path
            logger.debug(f"Running OCR for entry {entry_id} at path {entry_path}")

            img = Image.open(entry_path)
            ocr_text = pytesseract.image_to_string(img)

            logger.debug(f"OCR text for entry {entry_id}: {ocr_text}")
            self.update_progress_callback(i + 1)

            # save ocr text to entry
            """
                def add_field_to_entry(
                    self,
                    entry_id: int,
                    *,
                    field: ValueType | None = None,
                    field_id: FieldID | str | None = None,
                    value: str | datetime | None = None,
                ) -> bool:
            """
            if ocr_text is not None:
                self.library.add_field_to_entry(entry_id, field_id="OCR_TEXT", value=ocr_text)


class EasyOcrWorker(OCRRunner):
    name = "EasyOCR OCR"

    def __init__(self):
        super().__init__()

    def run(self):
        import easyocr

        self.reader = easyocr.Reader(["en"], gpu=True)
        for i, entry in enumerate(self.entries):
            if self.do_terminate:
                logger.debug("OCR process terminated by user.")
                break
            entry_id = entry.id
            entry_path = self.library.library_dir / entry.path
            logger.debug(f"Running OCR for entry {entry_id} at path {entry_path}")

            ocr_text = self.do_text(entry_path)
            logger.debug(f"OCR text for entry {entry_id}: {ocr_text}")
            self.update_progress_callback(i + 1)

            # save ocr text to entry
            """
                def add_field_to_entry(
                    self,
                    entry_id: int,
                    *,
                    field: ValueType | None = None,
                    field_id: FieldID | str | None = None,
                    value: str | datetime | None = None,
                ) -> bool:
            """
            if ocr_text is not None:
                self.library.add_field_to_entry(entry_id, field_id="OCR_TEXT", value=ocr_text)

    def do_text(self, entry_path: str):
        entry_path = str(entry_path)

        pil_image = Image.open(entry_path).convert("RGB")

        # scale down, so that the smaller side is max 1024 pixels
        max_size = 1024
        width, height = pil_image.size
        if min(width, height) > max_size:
            if width < height:
                new_width = max_size
                new_height = int((max_size / width) * height)
            else:
                new_height = max_size
                new_width = int((max_size / height) * width)

            pil_image = pil_image.resize((new_width, new_height), Image.Resampling.BICUBIC)

        numpy_image_array = np.array(pil_image)

        logger.debug(f"Performing OCR on image of size: {numpy_image_array.shape}")

        try:
            result = self.reader.readtext(numpy_image_array, detail=0, paragraph=True)
        except Exception as e:
            logger.error(f"OCR failed for image {entry_path} with error: {e}")
            return None
        out_text = "\n".join(result)
        return out_text


def test():
    import os

    import easyocr

    image_folder = r"C:\Users\flori\Pictures\OCRTestImages"
    test_files = os.listdir(image_folder)
    for file in test_files:
        if file.endswith(".txt"):
            os.remove(os.path.join(image_folder, file))

    reader = easyocr.Reader(["en"], gpu=True)
    worker = EasyOcrWorker()
    worker.reader = reader

    for file in test_files:
        if not (
            file.lower().endswith(".png")
            or file.lower().endswith(".jpg")
            or file.lower().endswith(".jpeg")
            or file.lower().endswith(".bmp")
        ):
            continue
        file_path = os.path.join(image_folder, file)
        logger.info(f"Processing file: {file_path}")
        text = worker.do_text(file_path)
        if text is None:
            logger.error(f"OCR failed for file: {file_path}")
            continue
        with open(f"{file_path}.txt", "w", encoding="utf-8") as f:
            f.write(text)
        logger.error(f"OCR text saved to: {file_path}.txt")
