import urwid


class Selectable(urwid.WidgetWrap):
    """A selectable text row that emits 'activate' on Enter."""

    signals = ["activate"]

    def __init__(self, markup):
        self.marker = urwid.Text("  ")
        self.text = urwid.Text(markup)
        cols = urwid.Columns([
            (2, self.marker),
            ("weight", 1, self.text)
        ], dividechars=0)
        w = urwid.AttrMap(cols,
            {
                None:       "selectable",
                "bold":     "sel_bold",
                "value":    "sel_value",
                "unset":    "sel_unset",
                "success":  "sel_success",
                "error":    "sel_error",
                "warning":  "sel_warning",
                "label":    "sel_label",
            },
            {
                None:       "focus",
                "bold":     "bold_focus",
                "value":    "value_focus",
                "unset":    "unset_focus",
                "success":  "success_focus",
                "error":    "error_focus",
                "warning":  "warning_focus",
                "label":    "label_focus",
            }
        )
        super().__init__(w)

    def render(self, size, focus=False):
        self.marker.set_text("> " if focus else "  ")
        return super().render(size, focus)

    def selectable(self):
        return True

    def keypress(self, size, key):
        if key == "enter":
            self._emit("activate")
            return None
        return key


class SubmitEdit(urwid.Edit):
    """Edit widget that emits 'activate' when Enter is pressed."""

    signals = ["activate", "change", "postchange"]

    def keypress(self, size, key):
        if key == "enter":
            self._emit("activate")
            return None
        return super().keypress(size, key)


class MenuItem(urwid.WidgetWrap):
    """Main menu item with > focus indicator and inline value."""

    signals = ["activate"]

    def __init__(self, label, value=""):
        self.marker = urwid.Text("  ")
        if value:
            text = urwid.Text([f"{label:<16}", ("value", value)])
        else:
            text = urwid.Text([f"{label:<16}", ("unset", "not set")])
        cols = urwid.Columns([
            (2, self.marker),
            ("weight", 1, text)
        ], dividechars=0)
        w = urwid.AttrMap(cols,
            {
                None:      "selectable",
                "value":   "sel_value",
                "unset":   "sel_unset",
            },
            {
                None:      "focus",
                "bold":    "bold_focus",
                "value":   "value_focus",
                "unset":   "unset_focus",
            }
        )
        super().__init__(w)

    def render(self, size, focus=False):
        self.marker.set_text("> " if focus else "  ")
        return super().render(size, focus)

    def selectable(self):
        return True

    def keypress(self, size, key):
        if key == "enter":
            self._emit("activate")
            return None
        return key
