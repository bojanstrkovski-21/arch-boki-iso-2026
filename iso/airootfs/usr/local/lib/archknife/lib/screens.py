import re
import subprocess

import urwid

from .widgets import Selectable, SubmitEdit
from . import utils


# ── Helpers ────────────────────────────────────────────────────────────

def _screen(title, items):
    """Wrap a title + item list into a ListBox body."""
    widgets = [
        urwid.Text(("title", f"\n  {title}\n")),
        urwid.Divider(),
    ] + items
    return urwid.ListBox(urwid.SimpleFocusListWalker(widgets))


def _back_button(app):
    w = Selectable(("value", "  Back"))
    urwid.connect_signal(w, "activate", lambda _: app.show_main())
    return w


# ── Network ────────────────────────────────────────────────────────────

def network(app):
    online, connections = utils.get_net_status()

    items = []
    status = ("success", "  Connected") if online else ("error", "  Offline")
    items.append(urwid.Text(status))
    items.append(urwid.Divider())

    if connections:
        for name, type_, dev in connections:
            items.append(urwid.Text(f"  {dev} \u2014 {name} ({type_})"))
        items.append(urwid.Divider())

    wifi_btn = Selectable("  Connect to wifi")
    urwid.connect_signal(wifi_btn, "activate", lambda _: _wifi_scan(app))
    items.append(wifi_btn)

    nmtui_btn = Selectable("  Launch nmtui (full network manager)")
    urwid.connect_signal(nmtui_btn, "activate", lambda _: _launch_nmtui(app))
    items.append(nmtui_btn)

    items.append(urwid.Divider())
    items.append(_back_button(app))

    app.show_screen(_screen("Network", items))


def _launch_nmtui(app):
    """Suspend urwid, run nmtui, then refresh."""
    app.loop.stop()
    subprocess.run(["nmtui"])
    app.loop.start()
    network(app)


def _wifi_scan(app):
    """Show scanning message, scan, then show results."""
    # Show scanning screen
    app.show_screen(_screen("Wifi Networks", [
        urwid.Text(("warning", "  Scanning...")),
    ]))
    app.loop.draw_screen()

    networks = utils.scan_wifi()

    if not networks:
        items = [
            urwid.Text(("error", "  No wifi networks found.")),
            urwid.Text(("warning", "  Check that your wifi adapter is recognized.")),
            urwid.Divider(),
        ]
        back = Selectable(("unset", "  Back"))
        urwid.connect_signal(back, "activate", lambda _: network(app))
        items.append(back)
        app.show_screen(_screen("Wifi Networks", items))
        return

    items = []
    for ssid, signal, security in networks:
        # Signal bars
        if signal >= 75:
            bars = ("success", "\u2587\u2587\u2587\u2587")
        elif signal >= 50:
            bars = ("success", "\u2587\u2587\u2587\u2591")
        elif signal >= 25:
            bars = ("warning", "\u2587\u2587\u2591\u2591")
        else:
            bars = ("error", "\u2587\u2591\u2591\u2591")

        lock = " [secured]" if security and security != "--" else ""
        markup = [
            f"  {ssid:<30}",
            bars,
            ("label", lock),
        ]
        w = Selectable(markup)
        urwid.connect_signal(
            w, "activate",
            lambda _, s=ssid, sec=security: _wifi_pick(app, s, sec),
        )
        items.append(w)

    items.append(urwid.Divider())

    rescan = Selectable("  Rescan")
    urwid.connect_signal(rescan, "activate", lambda _: _wifi_scan(app))
    items.append(rescan)

    back = Selectable(("value", "  Back"))
    urwid.connect_signal(back, "activate", lambda _: network(app))
    items.append(back)

    app.show_screen(_screen("Wifi Networks", items))


def _wifi_pick(app, ssid, security):
    """Handle picking a wifi network — prompt for password if secured."""
    if not security or security == "--":
        _wifi_do_connect(app, ssid)
        return

    # Password prompt
    items = []
    items.append(urwid.Text([f"  Network: ", ("value", ssid)]))
    items.append(urwid.Divider())

    pass_edit = urwid.Edit("  Password: ", mask="*")
    items.append(pass_edit)
    items.append(urwid.Divider())

    status_text = urwid.Text("")
    items.append(status_text)

    def do_connect(_):
        password = pass_edit.edit_text
        if not password:
            status_text.set_text(("error", "  Password cannot be empty"))
            return
        _wifi_do_connect(app, ssid, password)

    connect_btn = Selectable("  Connect")
    urwid.connect_signal(connect_btn, "activate", do_connect)
    items.append(connect_btn)

    items.append(urwid.Divider())
    back = Selectable(("value", "  Back"))
    urwid.connect_signal(back, "activate", lambda _: _wifi_scan(app))
    items.append(back)

    app.show_screen(_screen("Wifi — Connect", items))


def _wifi_do_connect(app, ssid, password=None):
    """Attempt connection and show result."""
    app.show_screen(_screen("Wifi — Connect", [
        urwid.Text(("warning", f"  Connecting to {ssid}...")),
    ]))
    app.loop.draw_screen()

    success, message = utils.wifi_connect(ssid, password)

    items = []
    if success:
        items.append(urwid.Text(("success", f"  {message}")))
    else:
        items.append(urwid.Text(("error", f"  {message}")))

    items.append(urwid.Divider())
    done = Selectable(("value", "  Back to network"))
    urwid.connect_signal(done, "activate", lambda _: network(app))
    items.append(done)

    app.show_screen(_screen("Wifi — Connect", items))


# ── Filesystem ─────────────────────────────────────────────────────────

def filesystem(app):
    items = []

    btrfs_desc = (
        "  Subvolumes: @  @home  @root  @snapshots  @var_log  @var_cache  @var_tmp\n"
        "  Includes Timeshift + grub-btrfs for bootable snapshot rollback"
    )

    w = Selectable("  btrfs")
    urwid.connect_signal(w, "activate",
                         lambda _: _set_fs(app, "btrfs"))
    items.append(w)
    items.append(urwid.Text(("label", btrfs_desc)))
    items.append(urwid.Divider())

    w = Selectable("  ext4")
    urwid.connect_signal(w, "activate",
                         lambda _: _set_fs(app, "ext4"))
    items.append(w)
    items.append(urwid.Text(("label", "  Simple, reliable, no snapshots")))
    items.append(urwid.Divider())

    w = Selectable("  xfs")
    urwid.connect_signal(w, "activate",
                         lambda _: _set_fs(app, "xfs"))
    items.append(w)
    items.append(urwid.Text(("label", "  High performance, no snapshots")))
    items.append(urwid.Divider())

    w = Selectable("  ext4 + LUKS encryption")
    urwid.connect_signal(w, "activate",
                         lambda _: _set_fs(app, "ext4", encrypt=True))
    items.append(w)
    items.append(urwid.Text(("label", "  Full disk encryption, password at boot")))
    items.append(urwid.Divider())

    w = Selectable("  xfs + LUKS encryption")
    urwid.connect_signal(w, "activate",
                         lambda _: _set_fs(app, "xfs", encrypt=True))
    items.append(w)
    items.append(urwid.Text(("label", "  Full disk encryption, password at boot")))

    items.append(urwid.Divider())
    items.append(_back_button(app))

    app.show_screen(_screen("Filesystem", items))


def _set_fs(app, fs, encrypt=False):
    app.config.filesystem = fs
    app.config.encrypt = encrypt
    if encrypt:
        _luks_passphrase(app)
    else:
        app.config.luks_pass = ""
        app.show_main()


def _luks_passphrase(app):
    """Prompt for LUKS encryption passphrase."""
    items = []
    items.append(urwid.Text(("label",
                              "  This passphrase will be required every time you boot.")))
    items.append(urwid.Divider())

    pass_edit = urwid.Edit("  Passphrase: ", mask="*")
    pass_confirm = urwid.Edit("  Confirm:    ", mask="*")
    error_text = urwid.Text("")

    items.extend([pass_edit, pass_confirm, error_text])
    items.append(urwid.Divider())

    def accept(_):
        p = pass_edit.edit_text
        if not p:
            error_text.set_text(("error", "  Passphrase cannot be empty"))
            return
        if p != pass_confirm.edit_text:
            error_text.set_text(("error", "  Passphrases don't match"))
            return
        app.config.luks_pass = p
        app.show_main()

    confirm = Selectable("  Accept")
    urwid.connect_signal(confirm, "activate", accept)
    items.append(confirm)

    items.append(urwid.Divider())
    back = Selectable(("value", "  Back"))
    urwid.connect_signal(back, "activate", lambda _: filesystem(app))
    items.append(back)

    app.show_screen(_screen("LUKS Encryption", items))


# ── Keyboard ───────────────────────────────────────────────────────────

def keyboard(app):
    common = [
        "us", "gb", "de", "fr", "es", "it", "pt", "br",
        "ru", "pl", "se", "no", "fi", "dk", "ch", "jp",
    ]

    items = []
    for k in common:
        w = Selectable(f"  {k}")
        urwid.connect_signal(w, "activate",
                             lambda _, v=k: _set(app, "keymap", v))
        items.append(w)

    items.append(urwid.Divider())
    items.append(urwid.Text(("label", "  Or type a layout name:")))
    edit = urwid.Edit("  > ")
    items.append(edit)

    accept = Selectable("  Accept")
    urwid.connect_signal(accept, "activate",
                         lambda _: _set(app, "keymap", edit.edit_text or "us"))
    items.append(accept)

    items.append(urwid.Divider())
    items.append(_back_button(app))

    app.show_screen(_screen("Keyboard Layout", items))


# ── Timezone ───────────────────────────────────────────────────────────

def timezone(app):
    all_zones = utils.get_timezones()
    detected = utils.detect_timezone()

    items = []

    if detected:
        items.append(urwid.Text([("label", "  Detected: "), ("value", detected)]))
        w = Selectable(("success", f"  Accept ({detected})"))
        urwid.connect_signal(w, "activate",
                             lambda _: _set(app, "timezone", detected))
        items.append(w)
        items.append(urwid.Divider())

    items.append(urwid.Text(("label", "  Type to search (e.g., chicago, london):")))

    edit = urwid.Edit("  > ")
    results_walker = urwid.SimpleFocusListWalker([])
    results_box = urwid.BoxAdapter(urwid.ListBox(results_walker), 12)

    def on_change(widget, text):
        results_walker.clear()
        if len(text) < 2:
            return
        pattern = text.lower()
        matches = [tz for tz in all_zones if pattern in tz.lower()][:15]
        for tz in matches:
            w = Selectable(f"    {tz}")
            urwid.connect_signal(w, "activate",
                                 lambda _, v=tz: _set(app, "timezone", v))
            results_walker.append(w)

    urwid.connect_signal(edit, "change", on_change)

    items.append(edit)
    items.append(results_box)
    items.append(urwid.Divider())
    items.append(_back_button(app))

    app.show_screen(_screen("Timezone", items))


# ── Locale ─────────────────────────────────────────────────────────────

def locale(app):
    common = [
        "en_US.UTF-8", "en_GB.UTF-8", "de_DE.UTF-8", "fr_FR.UTF-8",
        "es_ES.UTF-8", "it_IT.UTF-8", "pt_BR.UTF-8", "ru_RU.UTF-8",
        "pl_PL.UTF-8", "ja_JP.UTF-8",
    ]

    items = []
    for loc in common:
        w = Selectable(f"  {loc}")
        urwid.connect_signal(w, "activate",
                             lambda _, v=loc: _set(app, "locale", v))
        items.append(w)

    items.append(urwid.Divider())
    items.append(urwid.Text(("label", "  Or type a locale (e.g., nl_NL.UTF-8):")))
    edit = urwid.Edit("  > ")
    items.append(edit)

    accept = Selectable("  Accept")
    urwid.connect_signal(accept, "activate",
                         lambda _: _set_locale(app, edit.edit_text))
    items.append(accept)

    items.append(urwid.Divider())
    items.append(_back_button(app))

    app.show_screen(_screen("Locale", items))


def _set_locale(app, value):
    if not value:
        value = "en_US.UTF-8"
    if re.match(r"^[a-z]{2}_[A-Z]{2}$", value):
        value += ".UTF-8"
    app.config.locale = value
    app.show_main()


# ── Disk ───────────────────────────────────────────────────────────────

def disk(app):
    disks = utils.get_disks()

    items = []
    if not disks:
        items.append(urwid.Text(("error", "  No disks found")))
    else:
        for dev, size, model in disks:
            label = f"  {dev:<14}{size:<10}{model}"
            w = Selectable(("value", label))
            urwid.connect_signal(w, "activate",
                                 lambda _, v=dev: _set(app, "disk", v))
            items.append(w)

    items.append(urwid.Divider())
    items.append(_back_button(app))

    app.show_screen(
        _screen("Disk Selection", items),
        footer_text="  \u2191\u2193 navigate  Enter select  WARNING: selected disk will be erased",
    )


# ── Hostname ───────────────────────────────────────────────────────────

def hostname(app):
    items = []
    items.append(urwid.Text(("label",
                              "  Letters, numbers, hyphens. Must start with a letter.")))
    items.append(urwid.Divider())

    edit = SubmitEdit("  Hostname: ", app.config.hostname or "archboki")
    error_text = urwid.Text("")
    items.append(edit)
    items.append(error_text)
    items.append(urwid.Divider())

    def accept(_):
        val = edit.edit_text
        if re.match(r"^[a-zA-Z][a-zA-Z0-9-]*$", val):
            app.config.hostname = val
            app.show_main()
        else:
            error_text.set_text(("error", "  Invalid hostname"))

    urwid.connect_signal(edit, "activate", accept)

    confirm = Selectable("  Accept")
    urwid.connect_signal(confirm, "activate", accept)
    items.append(confirm)

    items.append(urwid.Divider())
    items.append(_back_button(app))

    app.show_screen(_screen("Hostname", items))


# ── User ───────────────────────────────────────────────────────────────

def user(app):
    items = []
    items.append(urwid.Text(("label",
                              "  Lowercase letters, numbers, hyphens, underscores.")))
    items.append(urwid.Divider())

    username_edit = urwid.Edit("  Username: ", app.config.username or "")
    pass_edit = urwid.Edit("  Password: ", mask="*")
    pass_confirm = urwid.Edit("  Confirm:  ", mask="*")

    items.extend([username_edit, pass_edit, pass_confirm])
    items.append(urwid.Divider())

    items.append(urwid.Text(("label",
                              "  Root password (leave blank to disable root login):")))
    root_edit = urwid.Edit("  Root password: ", mask="*")
    root_confirm = urwid.Edit("  Confirm:       ", mask="*")
    items.extend([root_edit, root_confirm])

    error_text = urwid.Text("")
    items.append(error_text)
    items.append(urwid.Divider())

    def accept(_):
        uname = username_edit.edit_text
        if not re.match(r"^[a-z][a-z0-9_-]*$", uname):
            error_text.set_text(("error", "  Invalid username"))
            return
        if not pass_edit.edit_text:
            error_text.set_text(("error", "  Password cannot be empty"))
            return
        if pass_edit.edit_text != pass_confirm.edit_text:
            error_text.set_text(("error", "  User passwords don't match"))
            return
        if root_edit.edit_text and root_edit.edit_text != root_confirm.edit_text:
            error_text.set_text(("error", "  Root passwords don't match"))
            return

        app.config.username = uname
        app.config.user_pass = pass_edit.edit_text
        app.config.root_pass = root_edit.edit_text
        app.show_main()

    confirm = Selectable("  Accept")
    urwid.connect_signal(confirm, "activate", accept)
    items.append(confirm)

    items.append(urwid.Divider())
    items.append(_back_button(app))

    app.show_screen(_screen("User Account", items))


# ── SSHD ───────────────────────────────────────────────────────────────

def sshd(app):
    items = []
    current = "enabled" if app.config.sshd else "disabled"
    items.append(urwid.Text([("label", "  Currently: "), ("value", current)]))
    items.append(urwid.Divider())

    on = Selectable("  Enable")
    urwid.connect_signal(on, "activate",
                         lambda _: _set(app, "sshd", True))
    items.append(on)
    items.append(urwid.Text(("label", "  Install and enable openssh-server")))
    items.append(urwid.Divider())

    off = Selectable("  Disable")
    urwid.connect_signal(off, "activate",
                         lambda _: _set(app, "sshd", False))
    items.append(off)
    items.append(urwid.Text(("label", "  No SSH access")))

    items.append(urwid.Divider())
    items.append(_back_button(app))

    app.show_screen(_screen("SSH Server", items))


# ── Summary / Install ─────────────────────────────────────────────────

def summary(app):
    c = app.config

    disk_size = ""
    r = utils.run(f"lsblk -dnbo SIZE {c.disk}")
    if r.returncode == 0 and r.stdout.strip():
        gb = int(r.stdout.strip()) / 1024 ** 3
        disk_size = f" ({gb:.1f} GB)"

    fs_display = c.filesystem
    if c.encrypt:
        fs_display += " + LUKS"

    items = []
    repos_active = []
    if c.enable_chaotic:
        repos_active.append("chaotic-aur")
    if c.enable_nemesis:
        repos_active.append("nemesis")
    if c.enable_boki:
        repos_active.append("boki")

    rows = [
        ("Boot mode",  c.boot_mode.upper()),
        ("Disk",       f"{c.disk}{disk_size}"),
        ("Filesystem", fs_display),
        ("Encryption", "LUKS" if c.encrypt else "none"),
        ("Desktop/WM", ", ".join(c.desktops) if c.desktops else "none"),
        ("Keyboard",   c.keymap),
        ("Timezone",   c.timezone),
        ("Locale",     c.locale),
        ("Hostname",   c.hostname),
        ("User",       c.username),
        ("Root login", "yes" if c.root_pass else "disabled"),
        ("SSHD",       "enabled" if c.sshd else "disabled"),
        ("Swap",       "zram (50% of RAM)"),
        ("Extra repos", ", ".join(repos_active) if repos_active else "none"),
        ("Method",     c.install_method),
    ]
    for lbl, val in rows:
        items.append(urwid.Text([("label", f"  {lbl:<16}"), ("value", val)]))

    items.append(urwid.Divider())
    items.append(urwid.Text(
        ("warning", f"  WARNING: ALL data on {c.disk}{disk_size} will be destroyed!")
    ))
    items.append(urwid.Divider())

    install_btn = Selectable(("error", "  Begin installation"))
    urwid.connect_signal(install_btn, "activate", lambda _: _begin_install(app))
    items.append(install_btn)

    items.append(urwid.Divider())
    items.append(_back_button(app))

    app.show_screen(_screen("Installation Summary", items))


def _begin_install(app):
    app.install_requested = True
    raise urwid.ExitMainLoop()


# ── Shell ──────────────────────────────────────────────────────────────

def drop_to_shell(app):
    """Drop to a shell — chroot into target if mounted, otherwise live shell."""
    import os
    mnt = "/mnt/archknife"

    app.loop.stop()

    if os.path.isdir(f"{mnt}/etc"):
        print(f"\n  \033[0;36mTarget system mounted at {mnt} — chrooting in.\033[0m")
        print("  \033[0;32mType 'exit' to return to archknife.\033[0m\n")
        subprocess.run(["chroot", mnt, "/bin/bash"])
    else:
        print("\n  \033[0;36mNo active install — dropping to live shell.\033[0m")
        print("  \033[0;32mType 'exit' to return to archknife.\033[0m\n")
        subprocess.run(["/bin/bash"])

    app.loop.start()
    app.show_main()


# ── Chroot Recovery ────────────────────────────────────────────────────

def chroot_recovery(app):
    """Pick a partition to mount and chroot into."""
    # List partitions with filesystem info
    r = utils.run("lsblk -lnpo NAME,SIZE,FSTYPE,LABEL,MOUNTPOINT")
    partitions = []
    for line in r.stdout.strip().splitlines():
        parts = line.split(None, 4)
        if len(parts) < 3:
            continue
        dev, size, fstype = parts[0], parts[1], parts[2]
        if not fstype or fstype in ("vfat", "swap"):
            continue
        if any(x in dev for x in ("loop", "sr", "rom", "zram")):
            continue
        label = parts[3] if len(parts) > 3 else ""
        mountpoint = parts[4] if len(parts) > 4 else ""
        if mountpoint:
            continue  # skip already-mounted
        partitions.append((dev, size, fstype, label))

    items = []
    if not partitions:
        items.append(urwid.Text(("error", "  No unmounted Linux partitions found")))
    else:
        items.append(urwid.Text(("label", "  Select a root partition to chroot into:")))
        items.append(urwid.Divider())
        for dev, size, fstype, label in partitions:
            display = f"  {dev:<16}{size:<10}{fstype:<8}{label}"
            w = Selectable(display)
            urwid.connect_signal(
                w, "activate",
                lambda _, d=dev, fs=fstype: _do_chroot(app, d, fs),
            )
            items.append(w)

    items.append(urwid.Divider())
    items.append(_back_button(app))

    app.show_screen(_screen("Chroot Recovery", items))


def _do_chroot(app, device, fstype):
    """Mount the partition, bind-mount system dirs, drop to shell."""
    import os

    mnt = "/mnt/chroot-recovery"

    app.loop.stop()

    print(f"\n  Mounting {device} at {mnt}...")
    os.makedirs(mnt, exist_ok=True)

    # Mount root — handle btrfs subvolumes
    if fstype == "btrfs":
        r = utils.run(f"mount -o subvol=@ {device} {mnt}")
        if r.returncode != 0:
            # No @ subvolume, mount normally
            utils.run(f"mount {device} {mnt}")
        # Mount other subvolumes if they exist
        for subvol, mountpoint in [
            ("@home", "/home"),
            ("@var_log", "/var/log"),
            ("@var_cache", "/var/cache"),
            ("@var_tmp", "/var/tmp"),
        ]:
            target = f"{mnt}{mountpoint}"
            if os.path.isdir(target):
                utils.run(f"mount -o subvol={subvol} {device} {target}")
    else:
        utils.run(f"mount {device} {mnt}")

    if not os.path.isdir(f"{mnt}/etc"):
        print(f"  \033[0;31mDoesn't look like a root filesystem.\033[0m")
        utils.run(f"umount -lf {mnt}")
        input("  Press Enter...")
        app.loop.start()
        chroot_recovery(app)
        return

    # Mount EFI if present
    if os.path.isdir(f"{mnt}/boot/efi"):
        # Find the EFI partition on the same disk
        r = utils.run(f"lsblk -ndo PKNAME {device}")
        disk = f"/dev/{r.stdout.strip()}"
        r = utils.run(f"lsblk -lnpo NAME,FSTYPE {disk}")
        for line in r.stdout.strip().splitlines():
            p = line.split()
            if len(p) >= 2 and p[1] == "vfat":
                utils.run(f"mount {p[0]} {mnt}/boot/efi")
                break

    # Bind-mount system filesystems
    for src, dst in [
        ("/dev", f"{mnt}/dev"),
        ("/dev/pts", f"{mnt}/dev/pts"),
    ]:
        utils.run(f"mount --bind {src} {dst}")
    utils.run(f"mount -t proc proc {mnt}/proc")
    utils.run(f"mount -t sysfs sys {mnt}/sys")
    if os.path.isdir("/sys/firmware/efi/efivars"):
        utils.run(f"mount --bind /sys/firmware/efi/efivars {mnt}/sys/firmware/efi/efivars")

    # Copy DNS
    if os.path.isfile("/etc/resolv.conf"):
        import shutil
        shutil.copy2("/etc/resolv.conf", f"{mnt}/etc/resolv.conf")

    print(f"\n  \033[0;32mChroot ready. Type 'exit' to return.\033[0m\n")
    subprocess.run(f"chroot {mnt} /bin/bash", shell=True)

    # Cleanup
    print(f"\n  Unmounting...")
    for mp in [
        f"{mnt}/sys/firmware/efi/efivars",
        f"{mnt}/dev/pts",
        f"{mnt}/dev",
        f"{mnt}/proc",
        f"{mnt}/sys",
        f"{mnt}/boot/efi",
    ]:
        subprocess.run(f"umount -lf {mp}", shell=True, capture_output=True)

    if fstype == "btrfs":
        for _, mountpoint in [
            ("@var_tmp", "/var/tmp"),
            ("@var_cache", "/var/cache"),
            ("@var_log", "/var/log"),
            ("@home", "/home"),
        ]:
            subprocess.run(f"umount -lf {mnt}{mountpoint}",
                           shell=True, capture_output=True)

    subprocess.run(f"umount -lf {mnt}", shell=True, capture_output=True)
    print(f"  \033[0;32mDone.\033[0m\n")
    input("  Press Enter...")

    app.loop.start()
    app.show_main()


# ── Desktop / WM chooser ──────────────────────────────────────────────

DESKTOP_GROUPS = [
    ("Desktop Environments", [
        ("xfce4",    "XFCE4",    "Lightweight, classic, stable"),
        ("cinnamon", "Cinnamon", "Modern, Windows-like feel"),
    ]),
    ("Tiling Window Managers", [
        ("awesome", "awesome", "Popular, well documented"),
        ("bspwm", "bspwm", "Keyboard driven, scriptable"),
        ("i3",    "i3",    "Popular, well documented"),
    ]),
    ("Floating Window Managers", [
        ("openbox", "Openbox", "Minimal, highly configurable"),
    ]),
]


def desktop(app, focus=0):
    items = []
    items.append(urwid.Text(("label",
        "  Select one or more desktops / window managers.\n"
        "  Enter toggles selection. Confirm when done.\n")))

    for group_label, entries in DESKTOP_GROUPS:
        items.append(urwid.AttrMap(
            urwid.Text(f"  ── {group_label} "),
            "title",
        ))
        for key, label, desc in entries:
            selected = key in app.config.desktops
            tick = ("success", "  [x]") if selected else ("unset", "  [ ]")
            row = Selectable([tick, f" {label:<12}", ("label", desc)])
            urwid.connect_signal(row, "activate",
                                 lambda _, k=key: _toggle_desktop(app, k))
            items.append(row)
        items.append(urwid.Divider())

    confirm = Selectable("  Confirm selection")
    urwid.connect_signal(confirm, "activate", lambda _: app.show_main())
    items.append(confirm)

    items.append(urwid.Divider())
    items.append(_back_button(app))
    body = _screen("Desktop / Window Manager", items)
    app.show_screen(body)
    if focus:
        try:
            body.set_focus(focus)
        except (IndexError, ValueError):
            pass


def _toggle_desktop(app, key):
    # Save focus position so the cursor doesn't jump back to top
    focus = 0
    try:
        _, focus = app.frame.body.get_focus()
    except Exception:
        pass
    if key in app.config.desktops:
        app.config.desktops.remove(key)
    else:
        app.config.desktops.append(key)
    desktop(app, focus)


# ── Extra repos ────────────────────────────────────────────────────────

def repos(app):
    items = []
    items.append(urwid.Text(("label",
        "  Select which extra repos to enable on the installed system.\n"
        "  Chaotic-AUR is recommended — it provides pre-built AUR packages.\n")))
    items.append(urwid.Divider())


    # Show only real official Arch repos, then custom repos
    repo_opts = [
        ("enable_multilib", "multilib", "Official 32-bit library support (recommended)"),
        ("enable_multilib_testing", "multilib-testing", "32-bit testing repo (Arch official)"),
        ("enable_core_testing", "core-testing", "Core package testing repo (Arch official)"),
        ("enable_extra_testing", "extra-testing", "Extra package testing repo (Arch official)"),
        ("enable_chaotic", "Chaotic-AUR", "Pre-built AUR packages (recommended)"),
        ("enable_nemesis", "Nemesis repo", "Erik Dubois' repo (ArcoLinux tools)"),
        ("enable_boki", "Boki repos", "shtrkce-repo + shtrkce_repo_xl"),
    ]

    # Ensure only multilib is enabled by default, all others off
    if not hasattr(app.config, 'enable_multilib'):
        app.config.enable_multilib = True
    for attr, _, _ in repo_opts:
        if attr != 'enable_multilib' and hasattr(app.config, attr):
            setattr(app.config, attr, False)

    for attr, label, desc in repo_opts:
        enabled = getattr(app.config, attr, False)
        if attr == 'enable_multilib':
            enabled = True  # Always enabled
        toggle_label = ("success", "  [x]") if enabled else ("unset", "  [ ]")
        row = Selectable([toggle_label, f" {label:<18}", ("label", desc)])
        if attr != 'enable_multilib':
            urwid.connect_signal(row, "activate",
                                 lambda _, a=attr: _toggle_repo(app, a))
        items.append(row)
        items.append(urwid.Divider())

    items.append(_back_button(app))
    app.show_screen(_screen("Extra Repositories", items))


def _toggle_repo(app, attr):
    setattr(app.config, attr, not getattr(app.config, attr))
    repos(app)


# ── Generic setter ─────────────────────────────────────────────────────

def _set(app, attr, value):
    setattr(app.config, attr, value)
    app.show_main()
