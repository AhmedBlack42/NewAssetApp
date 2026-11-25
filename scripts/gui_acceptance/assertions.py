from __future__ import annotations


def assert_visible(widget, label: str) -> None:
    if widget is None:
        raise AssertionError(f"{label}: widget is missing")
    if not widget.isVisible():
        raise AssertionError(f"{label}: widget is not visible")


def assert_in_window(window, widget, label: str) -> None:
    if widget is None:
        raise AssertionError(f"{label}: widget is missing")
    rect = widget.mapTo(window, widget.rect().topLeft())
    point_rect = widget.rect().translated(rect)
    if not window.rect().contains(point_rect):
        raise AssertionError(f"{label}: widget is outside the window")
