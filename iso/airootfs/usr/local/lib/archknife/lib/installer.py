import os
import shutil
import subprocess
import sys
import time

from .config import Config
from .utils import MNT, get_partitions, repo_in_pacman_conf

# ── Terminal colors ────────────────────────────────────────────────────
BOLD  = "\033[1m"
RED   = "\033[0;31m"
GREEN = "\033[0;32m"
CYAN  = "\033[0;36m"
NC    = "\033[0m"


def msg(text):
    print(f"\n  {CYAN}{BOLD}::{NC} {BOLD}{text}{NC}")


def ok(text):
    print(f"  {GREEN}{text}{NC}")


def die(text):
    print(f"\n  {RED}{BOLD}Error:{NC} {text}\n", file=sys.stderr)
    sys.exit(1)


def _run(cmd, check=True):
    r = subprocess.run(cmd, shell=True)
    if check and r.returncode != 0:
        die(f"Command failed: {cmd}")


def _run_quiet(cmd, check=True):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and r.returncode != 0:
        die(f"Command failed: {cmd}\n{r.stderr}")
    return r


# ── btrfs subvolume layout ─────────────────────────────────────────────
BTRFS_SUBVOLS = [
    ("@",          "/"),
    ("@home",      "/home"),
    ("@root",      "/root"),
    ("@snapshots", "/.snapshots"),
    ("@var_log",   "/var/log"),
    ("@var_cache", "/var/cache"),
    ("@var_tmp",   "/var/tmp"),
]

LUKS_NAME = "cryptroot"

# ── Desktop / WM package sets ──────────────────────────────────────────
DESKTOP_PACKAGES = {
    "awesome": [
        "acpi","acpid","avahi","awesome","base-devel","cifs-utils","cmake","curl","dbus","dialog","dunst","feh","file-roller",
        "flameshot","gvfs","gvfs-mtp","gvfs-nfs","gvfs-smb","libnotify","luacheck","luarocks","polkit-gnome","meson","mtools",
        "network-manager-applet","networkmanager","ninja","nwg-look","pamixer","pavucontrol","pipewire","pipewire-audio",
        "pkgconf","pulsemixer","smbclient","terminus-font","thunar","thunar-archive-plugin","thunar-shares-plugin","thunar-volman",
        "tumbler","unzip","vicious","wget","xbindkeys","xdg-user-dirs","xdg-user-dirs-gtk","xdotool","xfce4-power-manager",
        "xorg-server","xorg-xbacklight","xorg-xinput","rofi-categories","arch-boki-rofi-git",
        "lightdm","lightdm-slick-greeter",
    ],
    "xfce4": [
        "xfce4", "xfce4-goodies", "xfce4-screensaver", "lightdm", "lightdm-slick-greeter", "tumbler", "network-manager-applet", "gvfs", "thunar-archive-plugin", "file-roller",
        "pavucontrol", "xarchiver", "git", "firefox", "xfce4-docklike-plugin",
        "xdg-user-dirs", "xdg-user-dirs-gtk", "papirus-icon-theme",
    ],
    "cinnamon": [
        "cinnamon", "cinnamon-translations", "accountsservice", "git", "lightdm", "lightdm-slick-greeter",
        "network-manager-applet", "gvfs", "gvfs-nfs", "gvfs-smb", "iso-flag-png",
        "mintlocale",
        "nemo-file-roller", "nemo-preview", "nemo-share", "pavucontrol", "xdg-user-dirs",
        "xdg-user-dirs-gtk", "papirus-icon-theme",
    ],
    "bspwm": [
        "bspwm", "sxhkd", "rofi", "polybar", "picom",
        "lightdm", "lightdm-slick-greeter", "network-manager-applet",
        "feh", "dunst", "alacritty", "xdo",
    ],
    "i3": [
        "i3-wm", "i3status", "i3lock", "i3blocks", "xss-lock", "dmenu", "picom",
        "lightdm", "lightdm-slick-greeter", "network-manager-applet",
        "feh", "dunst", "alacritty",
    ],
    "openbox": [
        "openbox", "obconf", "tint2", "rofi", "picom",
        "lightdm", "lightdm-slick-greeter", "network-manager-applet",
        "feh", "dunst", "alacritty",
    ],
}

# Display manager to enable per desktop choice
DESKTOP_DM = {
    "xfce4":    "lightdm",
    "cinnamon": "lightdm",
    "bspwm":    "lightdm",
    "i3":       "lightdm",
    "openbox":  "lightdm",
    "awesome":  "lightdm",
}

# ── Base packages always installed ─────────────────────────────────────
BASE_PACKAGES = [
    # Core
    "base", "base-devel", "linux", "linux-firmware", "linux-headers",
    # Boot
    "grub", "efibootmgr", "os-prober",
    # System
    "sudo", "systemd", "networkmanager",
    # Filesystems
    "btrfs-progs", "xfsprogs", "dosfstools", "e2fsprogs",
    # Encryption
    "cryptsetup",
    # Zram
    "zram-generator",
    # CLI tools
    "curl", "wget", "git", "fzf", "ripgrep", "eza", "fastfetch",
    "bash-completion", "unzip", "zstd", "reflector",
    # Audio
    "pipewire", "pipewire-pulse", "wireplumber",
    # Fonts
    "ttf-font-awesome", "noto-fonts-emoji",
    # SSH
    "openssh",
    # Misc
    "nano", "vim", "btop",
    # X11 input (keyboard + mouse under any DE/WM)
    "xf86-input-libinput",
    # Polkit (required for lightdm seat management and DE auth dialogs)
    "polkit",
    # X11 session startup
    "xorg-xinit", "xorg-server", "xorg-xauth",
    # accountsservice (required by lightdm for user management)
    "accountsservice",
    # dbus (required by session startup scripts)
    "dbus",
]


# ── Repo setup helpers ─────────────────────────────────────────────────

def _setup_chaotic_aur_live():
    """Add Chaotic-AUR to the live environment so pacstrap can pull from it."""
    keyring_installed = subprocess.run(
        "pacman -Q chaotic-keyring", shell=True, capture_output=True
    ).returncode == 0

    if repo_in_pacman_conf("chaotic-aur") and keyring_installed:
        ok("Chaotic-AUR already configured on live environment")
        _run("pacman -Syy")
        return

    msg("Setting up Chaotic-AUR on live environment...")
    _run("pacman-key --recv-key 3056513887B78AEB --keyserver keyserver.ubuntu.com")
    _run("pacman-key --lsign-key 3056513887B78AEB")
    _run("pacman -U --noconfirm 'https://cdn-mirror.chaotic.cx/chaotic-aur/chaotic-keyring.pkg.tar.zst'")
    _run("pacman -U --noconfirm 'https://cdn-mirror.chaotic.cx/chaotic-aur/chaotic-mirrorlist.pkg.tar.zst'")
    if not repo_in_pacman_conf("chaotic-aur"):
        _run("echo -e '\\n[chaotic-aur]\\nInclude = /etc/pacman.d/chaotic-mirrorlist' >> /etc/pacman.conf")
    _run("pacman -Syy")
    ok("Chaotic-AUR ready on live environment")


def _write_pacman_conf_chroot(config: Config):
    """Write pacman.conf into the chroot with selected repos enabled."""
    conf_path = f"{MNT}/etc/pacman.conf"

    # Start from the live ISO's pacman.conf which already has our custom repos,
    # ILoveCandy, ParallelDownloads, Color, etc.
    live_conf = "/etc/pacman.conf"
    src = live_conf if os.path.isfile(live_conf) else conf_path
    with open(src) as f:
        content = f.read()

    # Uncomment multilib if not already active
    content = content.replace(
        "#[multilib]\n#Include = /etc/pacman.d/mirrorlist",
        "[multilib]\nInclude = /etc/pacman.d/mirrorlist",
    )

    # Chaotic-AUR
    if config.enable_chaotic and "[chaotic-aur]" not in content:
        content += "\n[chaotic-aur]\nInclude = /etc/pacman.d/chaotic-mirrorlist\n"

    # Erik's Nemesis repo
    if config.enable_nemesis and "[nemesis_repo]" not in content:
        content += (
            "\n[nemesis_repo]\n"
            "SigLevel = Never\n"
            "Server = https://erikdubois.github.io/$repo/$arch\n"
        )

    # Boki repos
    if config.enable_boki:
        if "[shtrkce-repo]" not in content:
            content += (
                "\n[shtrkce-repo]\n"
                "SigLevel = Optional TrustAll\n"
                "Server = https://bojanstrkovski-21.github.io/$repo/$arch\n"
            )
        if "[shtrkce_repo_xl]" not in content:
            content += (
                "\n[shtrkce_repo_xl]\n"
                "SigLevel = Optional TrustAll\n"
                "Server = https://gitlab.com/bojanstrkovski-21/$repo/-/raw/main/$arch\n"
            )

    with open(conf_path, "w") as f:
        f.write(content)

    ok("pacman.conf configured")


def _setup_chaotic_aur_chroot():
    """Activate Chaotic-AUR keyring in the chroot.

    chaotic-keyring and chaotic-mirrorlist are already installed by pacstrap.
    We only need to populate (sign) the Chaotic key from the installed keyring package.
    """
    msg("Configuring Chaotic-AUR keyring in installed system...")
    _run(f"arch-chroot {MNT} pacman-key --populate chaotic")
    ok("Chaotic-AUR keyring configured in installed system")


# ── Partitioning ───────────────────────────────────────────────────────

def partition_disk(config: Config):
    msg(f"Partitioning {config.disk}...")
    _run_quiet(f"wipefs -af {config.disk}")

    fs = config.filesystem
    fs_labels = {"btrfs": "btrfs", "ext4": "ext4", "xfs": "ext2"}
    fs_label = fs_labels.get(fs, "ext2")

    if config.boot_mode == "uefi":
        if config.encrypt:
            _run(f"parted -s {config.disk} "
                 f"mklabel gpt "
                 f"mkpart ESP fat32 1MiB 513MiB "
                 f"set 1 esp on "
                 f"mkpart boot ext4 513MiB 1537MiB "
                 f"mkpart root {fs_label} 1537MiB 100%")
        else:
            _run(f"parted -s {config.disk} "
                 f"mklabel gpt "
                 f"mkpart ESP fat32 1MiB 513MiB "
                 f"set 1 esp on "
                 f"mkpart root {fs_label} 513MiB 100%")
    else:
        if config.encrypt:
            _run(f"parted -s {config.disk} "
                 f"mklabel msdos "
                 f"mkpart primary ext4 1MiB 1025MiB "
                 f"set 1 boot on "
                 f"mkpart primary {fs_label} 1025MiB 100%")
        else:
            _run(f"parted -s {config.disk} "
                 f"mklabel msdos "
                 f"mkpart primary {fs_label} 1MiB 100% "
                 f"set 1 boot on")

    _run_quiet(f"partprobe {config.disk}", check=False)
    time.sleep(1)
    parts = get_partitions(config.disk)

    msg("Formatting...")
    if config.boot_mode == "uefi":
        _run(f"mkfs.fat -F32 {parts[0]}")
        if config.encrypt:
            _run(f"mkfs.ext4 -qF {parts[1]}")
            _format_root(parts[2], config)
        else:
            _format_root(parts[1], config)
    else:
        if config.encrypt:
            _run(f"mkfs.ext4 -qF {parts[0]}")
            _format_root(parts[1], config)
        else:
            _format_root(parts[0], config)

    os.makedirs(MNT, exist_ok=True)

    if config.boot_mode == "uefi":
        root_idx = 2 if config.encrypt else 1
        _mount_root(parts[root_idx], config)
        if config.encrypt:
            os.makedirs(f"{MNT}/boot", exist_ok=True)
            _run(f"mount {parts[1]} {MNT}/boot")
        os.makedirs(f"{MNT}/boot/efi", exist_ok=True)
        _run(f"mount {parts[0]} {MNT}/boot/efi")
    else:
        root_idx = 1 if config.encrypt else 0
        _mount_root(parts[root_idx], config)
        if config.encrypt:
            os.makedirs(f"{MNT}/boot", exist_ok=True)
            _run(f"mount {parts[0]} {MNT}/boot")

    ok("Partitioned and mounted")


def _format_root(part, config: Config):
    device = part
    if config.encrypt:
        msg("Setting up LUKS encryption...")
        subprocess.run(
            ["cryptsetup", "luksFormat", "--batch-mode",
             "--pbkdf", "pbkdf2", part, "-"],
            input=config.luks_pass, text=True, check=True,
        )
        subprocess.run(
            ["cryptsetup", "open", part, LUKS_NAME, "-"],
            input=config.luks_pass, text=True, check=True,
        )
        device = f"/dev/mapper/{LUKS_NAME}"
        ok("LUKS container created")

    if config.filesystem == "btrfs":
        _run(f"mkfs.btrfs -f {device}")
    elif config.filesystem == "xfs":
        _run(f"mkfs.xfs -f {device}")
    else:
        _run(f"mkfs.ext4 -qF {device}")


def _root_device(part, config: Config):
    if config.encrypt:
        return f"/dev/mapper/{LUKS_NAME}"
    return part


def _mount_root(part, config: Config):
    device = _root_device(part, config)

    if config.filesystem == "btrfs":
        _run(f"mount {device} {MNT}")
        msg("Creating btrfs subvolumes...")
        for subvol, _ in BTRFS_SUBVOLS:
            _run(f"btrfs subvolume create {MNT}/{subvol}")
        _run(f"umount {MNT}")
        _run(f"mount -o subvol=@,compress=zstd,noatime {device} {MNT}")
        for subvol, mountpoint in BTRFS_SUBVOLS:
            if subvol == "@":
                continue
            target = f"{MNT}{mountpoint}"
            os.makedirs(target, exist_ok=True)
            _run(f"mount -o subvol={subvol},compress=zstd,noatime {device} {target}")
    else:
        _run(f"mount {device} {MNT}")


# ── Base system install ────────────────────────────────────────────────

def install_base(config: Config):
    # Set up Chaotic-AUR on the live env first so pacstrap can use it
    if config.enable_chaotic:
        _setup_chaotic_aur_live()

    # Refresh mirrors before pacstrap
    msg("Refreshing Arch mirrors...")
    _run_quiet("reflector --latest 20 --sort rate --save /etc/pacman.d/mirrorlist",
               check=False)
    _run("pacman -Syy")

    # Build full package list: base + all selected desktops/WMs (deduplicated)
    pkgs = BASE_PACKAGES.copy()
    seen = set(pkgs)
    for de in config.desktops:
        for pkg in DESKTOP_PACKAGES.get(de, []):
            if pkg not in seen:
                pkgs.append(pkg)
                seen.add(pkg)

    # Timeshift for btrfs
    if config.filesystem == "btrfs":
        pkgs.append("timeshift")
        pkgs.append("grub-btrfs")
        pkgs.append("inotify-tools")

    # Chaotic keyring/mirrorlist so the installed system has them
    if config.enable_chaotic:
        pkgs += ["chaotic-keyring", "chaotic-mirrorlist"]

    de_names = ", ".join(config.desktops) if config.desktops else "no desktop"
    msg(f"Installing base system + {de_names} (this will take a while)...")
    pkg_str = " ".join(pkgs)
    _run(f"pacstrap -K {MNT} {pkg_str}")
    ok("Base system installed")


# ── System configuration ───────────────────────────────────────────────

WALLPAPER_SRC = "/usr/share/backgrounds/Wallpaper02.jpg"
WALLPAPER_DST = "/usr/share/backgrounds/Wallpaper02.jpg"
GREETER_WALLPAPER_SRC = "/usr/share/backgrounds/Wallpaper08.jpg"
GREETER_WALLPAPER_DST = "/usr/share/backgrounds/Wallpaper08.jpg"


def _setup_wallpaper(config: Config):
    """Copy wallpapers from live env and configure them per desktop."""
    dst_dir = f"{MNT}/usr/share/backgrounds"
    os.makedirs(dst_dir, exist_ok=True)

    # Copy greeter wallpaper
    if os.path.isfile(GREETER_WALLPAPER_SRC):
        shutil.copy2(GREETER_WALLPAPER_SRC, f"{MNT}{GREETER_WALLPAPER_DST}")

    if not os.path.isfile(WALLPAPER_SRC):
        return

    shutil.copy2(WALLPAPER_SRC, f"{MNT}{WALLPAPER_DST}")

    home = f"{MNT}/home/{config.username}"

    for de in config.desktops:
        if de == "xfce4":
            # Write an xfce4-desktop channel config for the user
            cfg_dir = f"{home}/.config/xfce4/xfconf/xfce-perchannel-xml"
            os.makedirs(cfg_dir, exist_ok=True)
            with open(f"{cfg_dir}/xfce4-desktop.xml", "w") as f:
                f.write(
                    '<?xml version="1.0" encoding="UTF-8"?>\n'
                    '<channel name="xfce4-desktop" version="1.0">\n'
                    '  <property name="backdrop" type="empty">\n'
                    '    <property name="screen0" type="empty">\n'
                    '      <property name="monitorVirtual-1" type="empty">\n'
                    '        <property name="workspace0" type="empty">\n'
                    f'          <property name="last-image" type="string" value="{WALLPAPER_DST}"/>\n'
                    '          <property name="image-style" type="int" value="5"/>\n'
                    '        </property>\n'
                    '      </property>\n'
                    '      <property name="monitor0" type="empty">\n'
                    '        <property name="workspace0" type="empty">\n'
                    f'          <property name="last-image" type="string" value="{WALLPAPER_DST}"/>\n'
                    '          <property name="image-style" type="int" value="5"/>\n'
                    '        </property>\n'
                    '      </property>\n'
                    '    </property>\n'
                    '  </property>\n'
                    '</channel>\n'
                )
        elif de == "cinnamon":
            # Cinnamon reads gsettings; pre-seed the dconf db
            dconf_dir = f"{home}/.config/dconf"
            os.makedirs(dconf_dir, exist_ok=True)
            profile_dir = f"{MNT}/etc/dconf/profile"
            os.makedirs(profile_dir, exist_ok=True)
            with open(f"{profile_dir}/user", "w") as f:
                f.write("user-db:user\nsystem-db:local\n")
            db_dir = f"{MNT}/etc/dconf/db/local.d"
            os.makedirs(db_dir, exist_ok=True)
            with open(f"{db_dir}/01-wallpaper", "w") as f:
                f.write(
                    "[org/cinnamon/desktop/background]\n"
                    f"picture-uri='file://{WALLPAPER_DST}'\n"
                    "picture-options='zoom'\n"
                )
            _run(f"arch-chroot {MNT} dconf update", check=False)
        elif de in ("bspwm", "i3", "openbox", "awesome"):
            # feh --bg-fill in autostart
            autostart = f"{home}/.config/autostart-wallpaper.sh"
            with open(autostart, "w") as f:
                f.write(f"#!/bin/sh\nfeh --bg-fill {WALLPAPER_DST}\n")
            os.chmod(autostart, 0o755)
            # Hook into the right autostart file per WM
            if de == "i3":
                i3_dir = f"{home}/.config/i3"
                os.makedirs(i3_dir, exist_ok=True)
                config_file = f"{i3_dir}/config"
                if os.path.isfile(config_file):
                    with open(config_file, "a") as f:
                        f.write(f"\nexec_always --no-startup-id feh --bg-fill {WALLPAPER_DST}\n")
            elif de == "bspwm":
                bspwm_dir = f"{home}/.config/bspwm"
                os.makedirs(bspwm_dir, exist_ok=True)
                with open(f"{bspwm_dir}/bspwmrc", "a") as f:
                    f.write(f"\nfeh --bg-fill {WALLPAPER_DST} &\n")
            elif de in ("openbox",):
                autostart_dir = f"{home}/.config/{de}"
                os.makedirs(autostart_dir, exist_ok=True)
                with open(f"{autostart_dir}/autostart", "a") as f:
                    f.write(f"\nfeh --bg-fill {WALLPAPER_DST} &\n")
            elif de == "awesome":
                awesome_dir = f"{home}/.config/awesome"
                os.makedirs(awesome_dir, exist_ok=True)
                rc = f"{awesome_dir}/rc.lua"
                # append feh only if rc.lua exists (copy from default first if needed)
                if not os.path.isfile(rc):
                    default_rc = f"{MNT}/etc/xdg/awesome/rc.lua"
                    if os.path.isfile(default_rc):
                        shutil.copy2(default_rc, rc)
                if os.path.isfile(rc):
                    with open(rc, "a") as f:
                        f.write(f'\nauto_feh = awful.spawn.with_shell("feh --bg-fill {WALLPAPER_DST}")\n')

    # Fix ownership — must run inside the chroot because the username only
    # exists there, not in the live environment.
    _run_quiet(
        f"arch-chroot {MNT} chown -R {config.username}:{config.username}"
        f" /home/{config.username}",
        check=False,
    )
    ok("Wallpaper configured")


def configure_system(config: Config):
    msg("Configuring system...")

    parts = get_partitions(config.disk)

    if config.boot_mode == "uefi":
        efi_part = parts[0]
        if config.encrypt:
            boot_part, root_part = parts[1], parts[2]
        else:
            boot_part, root_part = None, parts[1]
    else:
        efi_part = None
        if config.encrypt:
            boot_part, root_part = parts[0], parts[1]
        else:
            boot_part, root_part = None, parts[0]

    # ── fstab ──
    msg("Generating fstab...")
    _run(f"genfstab -U {MNT} >> {MNT}/etc/fstab")
    ok("fstab generated")

    # ── crypttab (LUKS only) ──
    if config.encrypt:
        luks_uuid = _run_quiet(f"blkid -s UUID -o value {root_part}").stdout.strip()
        with open(f"{MNT}/etc/crypttab", "w") as f:
            f.write(f"{LUKS_NAME}  UUID={luks_uuid}  none  luks\n")
        ok("crypttab written")

    # ── Timezone ──
    _run(f"arch-chroot {MNT} ln -sf /usr/share/zoneinfo/{config.timezone} /etc/localtime")
    _run(f"arch-chroot {MNT} hwclock --systohc")
    ok(f"Timezone: {config.timezone}")

    # ── Locale ──
    _run(f"sed -i 's/^#{config.locale}/{config.locale}/' {MNT}/etc/locale.gen")
    _run(f"arch-chroot {MNT} locale-gen")
    with open(f"{MNT}/etc/locale.conf", "w") as f:
        f.write(f"LANG={config.locale}\n")
    ok(f"Locale: {config.locale}")

    # ── Keyboard ──
    with open(f"{MNT}/etc/vconsole.conf", "w") as f:
        f.write(f"KEYMAP={config.keymap}\n")
    # For X11/Wayland sessions
    os.makedirs(f"{MNT}/etc/X11/xorg.conf.d", exist_ok=True)
    with open(f"{MNT}/etc/X11/xorg.conf.d/00-keyboard.conf", "w") as f:
        f.write(
            f'Section "InputClass"\n'
            f'    Identifier "system-keyboard"\n'
            f'    MatchIsKeyboard "on"\n'
            f'    Option "XkbLayout" "{config.keymap}"\n'
            f'EndSection\n'
        )
    ok(f"Keyboard: {config.keymap}")

    # ── Hostname ──
    with open(f"{MNT}/etc/hostname", "w") as f:
        f.write(config.hostname + "\n")
    with open(f"{MNT}/etc/hosts", "w") as f:
        f.write(
            f"127.0.0.1   localhost\n"
            f"127.0.1.1   {config.hostname}\n"
            f"\n"
            f"::1         localhost ip6-localhost ip6-loopback\n"
            f"ff02::1     ip6-allnodes\n"
            f"ff02::2     ip6-allrouters\n"
        )
    ok(f"Hostname: {config.hostname}")

    # ── User ──
    _run(f"arch-chroot {MNT} useradd -m -G wheel,audio,video,storage,optical,network "
         f"-s /bin/bash {config.username}")
    subprocess.run(
        ["arch-chroot", MNT, "chpasswd"],
        input=f"{config.username}:{config.user_pass}\n", text=True, check=True,
    )
    # Enable wheel group in sudoers
    _run(f"sed -i 's/^# %wheel ALL=(ALL:ALL) ALL/%wheel ALL=(ALL:ALL) ALL/' "
         f"{MNT}/etc/sudoers")

    if config.root_pass:
        subprocess.run(
            ["arch-chroot", MNT, "chpasswd"],
            input=f"root:{config.root_pass}\n", text=True, check=True,
        )
    else:
        _run(f"arch-chroot {MNT} passwd -l root")
    ok(f"User: {config.username}")

    # ── Zram ──
    with open(f"{MNT}/etc/systemd/zram-generator.conf", "w") as f:
        f.write("[zram0]\nzram-size = ram / 2\ncompression-algorithm = zstd\n")
    ok("Zram configured")

    # ── NetworkManager ──
    _run(f"arch-chroot {MNT} systemctl enable NetworkManager")

    # ── Timesyncd ──
    _run(f"arch-chroot {MNT} systemctl enable systemd-timesyncd")

    # ── SSHD ──
    if config.sshd:
        _run(f"arch-chroot {MNT} systemctl enable sshd")
        ok("SSHD enabled")

    # ── Display manager ── enable for first selected desktop
    dm = next((DESKTOP_DM.get(de) for de in config.desktops if DESKTOP_DM.get(de)), None)
    if dm:
        _run(f"arch-chroot {MNT} systemctl enable {dm}")
        ok(f"Display manager: {dm} enabled")

    # ── lightdm config (explicit greeter so it doesn't silently fall back) ──
    # Map desktop name to the xsessions .desktop filename (without .desktop)
    _session_name = {
        "xfce4": "xfce", "cinnamon": "cinnamon", "awesome": "awesome",
        "bspwm": "bspwm", "i3": "i3", "openbox": "openbox",
    }
    first_session = next(
        (_session_name[de] for de in config.desktops if de in _session_name), None
    )
    if dm == "lightdm":
        # Patch the default lightdm.conf shipped by the package rather than
        # replacing it — avoids losing PAM/Xauth defaults that LightDM needs.
        lightdm_conf = f"{MNT}/etc/lightdm/lightdm.conf"
        # Uncomment / set greeter-session under [Seat:*]
        _run(
            f"sed -i 's|^#*greeter-session=.*|greeter-session=lightdm-slick-greeter|'"
            f" {lightdm_conf}"
        )
        if first_session:
            # Uncomment / set user-session under [Seat:*]
            _run(
                f"sed -i 's|^#*user-session=.*|user-session={first_session}|'"
                f" {lightdm_conf}"
            )
        with open(f"{MNT}/etc/lightdm/slick-greeter.conf", "w") as f:
            f.write(
                "[Greeter]\n"
                "background=/usr/share/backgrounds/Wallpaper08.jpg\n"
                "background-color=#1a1a2e\n"
                "draw-user-backgrounds=false\n"
            )
        ok("lightdm configured")

    # ── Desktop wallpaper ──
    _setup_wallpaper(config)

    # ── pacman.conf with extra repos ──
    _write_pacman_conf_chroot(config)

    # ── Chaotic-AUR keyring inside chroot ──
    if config.enable_chaotic:
        _setup_chaotic_aur_chroot()
        _run(f"arch-chroot {MNT} pacman -Syy")

    # ── LUKS initramfs ──
    if config.encrypt:
        msg("Configuring encrypted boot...")
        # Add encrypt hook to mkinitcpio
        _run(f"sed -i 's/^HOOKS=.*/HOOKS=(base udev autodetect microcode modconf kms "
             f"keyboard keymap consolefont block encrypt filesystems fsck)/' "
             f"{MNT}/etc/mkinitcpio.conf")
        _run(f"arch-chroot {MNT} mkinitcpio -P")
        # GRUB cryptdevice parameter
        luks_uuid = _run_quiet(f"blkid -s UUID -o value {root_part}").stdout.strip()
        _run(f"sed -i 's|^GRUB_CMDLINE_LINUX=\"\"|"
             f"GRUB_CMDLINE_LINUX=\"cryptdevice=UUID={luks_uuid}:{LUKS_NAME}\"|' "
             f"{MNT}/etc/default/grub")
        ok("Encrypted boot configured")

    # ── btrfs snapshot stack ──
    if config.filesystem == "btrfs":
        _configure_btrfs_snapshots(config)

    ok("System configured")


def _configure_btrfs_snapshots(config: Config):
    """Set up Timeshift + grub-btrfs for bootable snapshot rollback."""
    msg("Configuring Timeshift + grub-btrfs...")

    parts = get_partitions(config.disk)
    root_part = parts[2] if (config.boot_mode == "uefi" and config.encrypt) else \
                parts[1] if config.boot_mode == "uefi" else \
                parts[1] if config.encrypt else parts[0]

    if config.encrypt:
        root_uuid = _run_quiet(
            f"blkid -s UUID -o value /dev/mapper/{LUKS_NAME}").stdout.strip()
    else:
        root_uuid = _run_quiet(
            f"blkid -s UUID -o value {root_part}").stdout.strip()

    os.makedirs(f"{MNT}/etc/timeshift", exist_ok=True)
    with open(f"{MNT}/etc/timeshift/timeshift.json", "w") as f:
        f.write(f"""\
{{
  "backup_device_uuid" : "{root_uuid}",
  "parent_device_uuid" : "",
  "do_first_run" : "false",
  "btrfs_mode" : "true",
  "include_btrfs_home_for_backup" : "true",
  "include_btrfs_home_for_restore" : "false",
  "stop_cron_emails" : "true",
  "schedule_monthly" : "true",
  "schedule_weekly" : "true",
  "schedule_daily" : "false",
  "schedule_hourly" : "false",
  "schedule_boot" : "false",
  "count_monthly" : "2",
  "count_weekly" : "3",
  "count_daily" : "0",
  "count_hourly" : "0",
  "count_boot" : "0",
  "snapshot_size" : "0",
  "snapshot_count" : "0",
  "exclude" : [],
  "exclude-apps" : []
}}
""")

    _run_quiet(f"arch-chroot {MNT} systemctl enable grub-btrfsd", check=False)
    ok("Timeshift + grub-btrfs configured")


# ── Bootloader ─────────────────────────────────────────────────────────

def install_bootloader(config: Config):
    msg(f"Installing GRUB ({config.boot_mode})...")

    # Enable os-prober in grub config
    _run(f"sed -i 's/#GRUB_DISABLE_OS_PROBER=false/GRUB_DISABLE_OS_PROBER=false/' "
         f"{MNT}/etc/default/grub")

    if config.boot_mode == "uefi":
        _run(f"arch-chroot {MNT} grub-install "
             f"--target=x86_64-efi "
             f"--efi-directory=/boot/efi "
             f"--bootloader-id=archknife "
             f"--recheck")
    else:
        _run(f"arch-chroot {MNT} grub-install "
             f"--target=i386-pc "
             f"--recheck "
             f"{config.disk}")

    _run(f"arch-chroot {MNT} grub-mkconfig -o /boot/grub/grub.cfg")
    ok("GRUB installed")


# ── Cleanup ────────────────────────────────────────────────────────────

def cleanup(config: Config):
    msg("Unmounting...")

    if config.filesystem == "btrfs":
        for _, mountpoint in reversed(BTRFS_SUBVOLS):
            if mountpoint == "/":
                continue
            subprocess.run(f"umount -lf {MNT}{mountpoint}",
                           shell=True, capture_output=True)

    if config.boot_mode == "uefi":
        subprocess.run(f"umount -lf {MNT}/boot/efi",
                       shell=True, capture_output=True)
    if config.encrypt:
        subprocess.run(f"umount -lf {MNT}/boot",
                       shell=True, capture_output=True)

    subprocess.run(f"umount -lf {MNT}", shell=True, capture_output=True)

    if config.encrypt:
        subprocess.run(f"cryptsetup close {LUKS_NAME}",
                       shell=True, capture_output=True)

    ok("Done")


# ── Main orchestrator ──────────────────────────────────────────────────

def run_install(config: Config, script_dir: str):
    print(f"\n  {BOLD}{CYAN}Installing Arch Linux{NC}\n")

    partition_disk(config)
    install_base(config)

    # Copy DNS so chroot has network before configure_system runs
    shutil.copy2("/etc/resolv.conf", f"{MNT}/etc/resolv.conf")

    configure_system(config)
    install_bootloader(config)

    print(f"\n  {GREEN}{BOLD}Installation complete!{NC}")
    print(f"\n  Remove the installation media before rebooting.\n")

    try:
        while True:
            reply = input(
                f"  [R]eboot, [C]hroot into new install, [E]xit to shell: "
            ).strip().lower()
            if reply == "c":
                print(f"  Entering chroot. Type 'exit' to return.\n")
                subprocess.run(f"arch-chroot {MNT} /bin/bash", shell=True)
                continue
            if reply == "e":
                cleanup(config)
                break
            if reply in ("", "r"):
                cleanup(config)
                subprocess.run("reboot", shell=True)
                break
    except (EOFError, KeyboardInterrupt):
        cleanup(config)
