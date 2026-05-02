import urwid

from .config import Config
from .widgets import Selectable, MenuItem
from . import screens

PALETTE = [
    # base
    ("",              "light gray",  "black"),
    ("header",        "light gray",  "dark gray"),
    ("footer",        "light gray",  "dark gray"),
    ("title",         "light cyan",  "black"),
    # plain text attrs (black bg)
    ("value",         "light gray",  "black"),
    ("unset",         "light gray",  "black"),
    ("label",         "light gray",  "black"),
    ("success",       "light green", "black"),
    ("error",         "light red",   "black"),
    ("warning",       "yellow",      "black"),
    ("bold",          "light gray",  "black"),
    # selectable unfocused (black bg)
    ("selectable",    "light gray",  "black"),
    ("sel_bold",      "light gray",  "black"),
    ("sel_value",     "light gray",  "black"),
    ("sel_unset",     "light gray",  "black"),
    ("sel_label",     "light gray",  "black"),
    ("sel_success",   "light green", "black"),
    ("sel_error",     "light red",   "black"),
    ("sel_warning",   "yellow",      "black"),
    # selectable focused (dark gray bg)
    ("focus",         "light gray",  "dark gray"),
    ("bold_focus",    "light gray",  "dark gray"),
    ("value_focus",   "light gray",  "dark gray"),
    ("unset_focus",   "light gray",  "dark gray"),
    ("label_focus",   "light gray",  "dark gray"),
    ("success_focus", "light green", "dark gray"),
    ("error_focus",   "light red",   "dark gray"),
    ("warning_focus", "yellow",      "dark gray"),
]


class App:
    def __init__(self, config: Config, script_dir: str):
        self.config = config
        self.script_dir = script_dir
        self.install_requested = False
        self._in_main = True
        self._menu_focus = 0

        self.frame = urwid.Frame(
            urwid.SolidFill(),
            header=self._make_header(),
            footer=self._make_footer(),
        )
        self.loop = urwid.MainLoop(
            self.frame,
            PALETTE,
            unhandled_input=self._input,
            input_filter=self._filter_input,
        )
        self.show_main()

    def _filter_input(self, keys, raw):
        out = []
        for key in keys:
            if key == "tab":
                out.append("down")
            elif key == "shift tab":
                out.append("up")
            else:
                out.append(key)
        return out

    def _make_header(self):
        text = (f"  archknife  Arch Linux Installer"
                f"          {self.config.boot_mode.upper()}"
                f" | {self.config.install_method}")
        return urwid.AttrMap(urwid.Text(text), "header")

    def _make_footer(self, text="  Tab/\u2191\u2193 navigate  Enter select  Esc back  q quit"):
        return urwid.AttrMap(urwid.Text(text), "footer")

    def _input(self, key):
        if key == "esc":
            if self._in_main:
                raise urwid.ExitMainLoop()
            self.show_main()
        elif key in ("q", "Q") and self._in_main:
            raise urwid.ExitMainLoop()

    def show_main(self):
        if not self._in_main:
            self._menu_focus += 1
        else:
            self._menu_focus = 0
        self._in_main = True

        from . import utils
        online, _ = utils.get_net_status()
        net_val = "connected" if online else "offline"

        fs_val = self.config.filesystem
        if fs_val and self.config.encrypt:
            fs_val += " + LUKS"

        items = []
        menu_entries = [
            ("Network",      net_val,                          lambda: screens.network(self)),
            ("Keyboard",     self.config.keymap,               lambda: screens.keyboard(self)),
            ("Timezone",     self.config.timezone,             lambda: screens.timezone(self)),
            ("Locale",       self.config.locale,               lambda: screens.locale(self)),
            ("Disk",         self.config.disk,                 lambda: screens.disk(self)),
            ("Filesystem",   fs_val,                           lambda: screens.filesystem(self)),
            ("Desktop/WM",   ", ".join(self.config.desktops) if self.config.desktops else "",  lambda: screens.desktop(self)),
            ("Hostname",     self.config.hostname,             lambda: screens.hostname(self)),
            ("User account", self.config.username,             lambda: screens.user(self)),
            ("SSHD",         "enabled" if self.config.sshd else "disabled",
                                                               lambda: screens.sshd(self)),
            ("Extra repos",  "",                               lambda: screens.repos(self)),
        ]

        for i, (label, val, callback) in enumerate(menu_entries):
            w = MenuItem(label, val)
            urwid.connect_signal(w, "activate",
                                 lambda _, cb=callback, idx=i: self._menu_activate(cb, idx))
            items.append(w)

        items.append(urwid.Divider())

        if self.config.ready():
            w = Selectable(("success", "  Install"))
            urwid.connect_signal(w, "activate", lambda _: screens.summary(self))
        else:
            w = urwid.Text(("unset", "  Install  (complete all steps first)"))
        items.append(w)

        w = Selectable("  Shell")
        urwid.connect_signal(w, "activate", lambda _: screens.drop_to_shell(self))
        items.append(w)

        w = Selectable("  Chroot recovery")
        urwid.connect_signal(w, "activate", lambda _: screens.chroot_recovery(self))
        items.append(w)

        w = Selectable("  Abort")
        urwid.connect_signal(w, "activate", lambda _: self._exit())
        items.append(w)

        menu = urwid.ListBox(urwid.SimpleFocusListWalker(items))

        # ── Info panel ──
        repos_active = []
        if self.config.enable_chaotic:
            repos_active.append("chaotic")
        if self.config.enable_nemesis:
            repos_active.append("nemesis")
        if self.config.enable_boki:
            repos_active.append("boki")
        repos_val = ", ".join(repos_active) if repos_active else "none"

        info_rows = []
        for lbl, val in [
            ("Boot",       self.config.boot_mode.upper()),
            ("Method",     self.config.install_method),
            ("Disk",       self.config.disk),
            ("Filesystem", fs_val),
            ("Desktop/WM", ", ".join(self.config.desktops) if self.config.desktops else ""),
            ("Keyboard",   self.config.keymap),
            ("Timezone",   self.config.timezone),
            ("Locale",     self.config.locale),
            ("Hostname",   self.config.hostname),
            ("User",       self.config.username),
            ("SSHD",       "enabled" if self.config.sshd else "disabled"),
            ("Repos",      repos_val),
            ("Swap",       "zram (50% RAM)"),
        ]:
            v = val or ""
            style = "value" if val else "unset"
            info_rows.append(
                urwid.Text([("label", f" {lbl:<13}"), (style, v)])
            )

        info_pile = urwid.Pile(info_rows)
        info_fill = urwid.Filler(info_pile, valign="top")
        info_box = urwid.LineBox(info_fill, title="Info", title_align="left")

        columns = urwid.Columns([
            ("weight", 3, menu),
            ("weight", 2, info_box),
        ], dividechars=1)

        self.frame.body = columns
        self.frame.footer = self._make_footer()

        num_menu = len(menu_entries)
        if self._menu_focus >= num_menu:
            self._menu_focus = num_menu - 1
        try:
            menu.set_focus(self._menu_focus)
        except (IndexError, ValueError):
            pass

    def show_screen(self, widget, footer_text=None):
        self._in_main = False
        self.frame.body = widget
        if footer_text:
            self.frame.footer = self._make_footer(footer_text)
        else:
            self.frame.footer = self._make_footer(
                "  Tab/\u2191\u2193 navigate  Enter select  Esc back"
            )
        # Move focus to first selectable item
        if hasattr(widget, 'set_focus'):
            for i, w in enumerate(widget.body):
                if hasattr(w, 'selectable') and w.selectable():
                    try:
                        widget.set_focus(i)
                    except (IndexError, ValueError):
                        pass
                    break

    def _menu_activate(self, callback, index):
        self._menu_focus = index
        callback()

    def _exit(self):
        raise urwid.ExitMainLoop()

    def run(self):
        self.loop.run()
        return self.install_requested
