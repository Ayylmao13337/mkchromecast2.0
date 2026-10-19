"""Visible source stopwatch for photographic capture-to-display comparisons."""
import sys


def main():
    from PyQt5 import QtCore, QtGui, QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    window = QtWidgets.QWidget()
    window.setWindowTitle('MKChromecast source clock')
    layout = QtWidgets.QVBoxLayout(window)
    label = QtWidgets.QLabel()
    label.setAlignment(QtCore.Qt.AlignCenter)
    label.setFont(QtGui.QFont('Monospace', 36))
    layout.addWidget(label)
    hint = QtWidgets.QLabel('Source clock — photograph this and the delayed copy together.\nDisplayed milliseconds do not imply millisecond measurement accuracy.')
    hint.setWordWrap(True)
    layout.addWidget(hint)
    elapsed = QtCore.QElapsedTimer()
    elapsed.start()
    def tick():
        milliseconds = elapsed.elapsed()
        label.setText(f'{milliseconds // 1000:06d}.{milliseconds % 1000:03d}')
    timer = QtCore.QTimer(window)
    timer.timeout.connect(tick)
    timer.start(16)
    tick()
    window.resize(560, 170)
    window.show()
    return app.exec_()


if __name__ == '__main__':
    raise SystemExit(main())
