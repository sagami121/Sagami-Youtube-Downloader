from PySide6.QtWidgets import QLineEdit, QStyle

class FocusClearLineEdit(QLineEdit):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        icon = self.style().standardIcon(QStyle.StandardPixmap.SP_LineEditClearButton)
        self._clear_action = self.addAction(icon, QLineEdit.ActionPosition.TrailingPosition)
        self._clear_action.triggered.connect(self.clear)
        self._clear_action.setVisible(False)
        self.textChanged.connect(self._update_clear_action)

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self._update_clear_action()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self._update_clear_action()

    def _update_clear_action(self):
        self._clear_action.setVisible(self.hasFocus() and bool(self.text()))
