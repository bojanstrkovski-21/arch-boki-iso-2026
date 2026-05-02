import os
import shutil
import subprocess
import time

MNT = "/mnt/archknife"


def run(cmd, check=False, **kwargs):
    if isinstance(cmd, str):
        return subprocess.run(cmd, shell=True, capture_output=True, text=True,
                              check=check, **kwargs)
    return subprocess.run(cmd, capture_output=True, text=True, check=check, **kwargs)


def detect_boot_mode():
    return "uefi" if os.path.isdir("/sys/firmware/efi") else "bios"


def detect_install_method(script_dir):
    if shutil.which("pacstrap"):
        return "pacstrap"
    return None


def is_online():
    return run("ping -c 1 -W 2 1.1.1.1").returncode == 0


def get_net_status():
    """Returns (online, connections) — connections is list of (name, type, device)."""
    online = False
    r = run("nmcli -t -f STATE general")
    if r.returncode == 0 and "connected" in r.stdout.lower():
        online = True

    connections = []
    r = run("nmcli -t -f NAME,TYPE,DEVICE con show --active")
    if r.returncode == 0:
        for line in r.stdout.strip().splitlines():
            parts = line.split(":")
            if len(parts) >= 3 and parts[2] != "lo":
                connections.append((parts[0], parts[1], parts[2]))
    return online, connections


def get_disks():
    """Returns list of (device, size, model) tuples."""
    r = run("lsblk -dnpo NAME,SIZE,MODEL")
    disks = []
    for line in r.stdout.strip().splitlines():
        parts = line.split(None, 2)
        if len(parts) < 2:
            continue
        dev = parts[0]
        if any(x in dev for x in ("loop", "sr", "rom", "zram")):
            continue
        size = parts[1]
        model = parts[2].strip() if len(parts) > 2 else ""
        disks.append((dev, size, model))
    return disks


def get_timezones():
    r = run(
        "find /usr/share/zoneinfo/Africa /usr/share/zoneinfo/America "
        "/usr/share/zoneinfo/Antarctica /usr/share/zoneinfo/Asia "
        "/usr/share/zoneinfo/Atlantic /usr/share/zoneinfo/Australia "
        "/usr/share/zoneinfo/Europe /usr/share/zoneinfo/Indian "
        "/usr/share/zoneinfo/Pacific -type f 2>/dev/null | "
        "sed 's|/usr/share/zoneinfo/||' | sort"
    )
    return r.stdout.strip().splitlines()


def detect_timezone():
    r = run("curl -s --max-time 3 ifconfig.io/timezone")
    tz = r.stdout.strip()
    if tz and os.path.isfile(f"/usr/share/zoneinfo/{tz}"):
        return tz
    return ""


def get_partitions(disk):
    """Get partition device paths (excludes the disk itself)."""
    r = run(f"lsblk -lnpo NAME {disk}", check=True)
    return r.stdout.strip().splitlines()[1:]


def scan_wifi():
    """Scan for wifi networks. Returns list of (ssid, signal, security) tuples, deduped."""
    run("nmcli device wifi rescan")
    time.sleep(2)

    r = run("nmcli -t -f SSID,SIGNAL,SECURITY device wifi list")
    if r.returncode != 0:
        return []

    seen = set()
    networks = []
    for line in r.stdout.strip().splitlines():
        parts = line.split(":", 2)
        if len(parts) < 3 or not parts[0]:
            continue
        ssid, signal, security = parts[0], int(parts[1] or 0), parts[2]
        if ssid in seen:
            continue
        seen.add(ssid)
        networks.append((ssid, signal, security))

    networks.sort(key=lambda x: x[1], reverse=True)
    return networks


def wifi_connect(ssid, password=None):
    """Connect to a wifi network. Returns (success, message)."""
    r = subprocess.run(["nmcli", "con", "show", ssid],
                       capture_output=True, text=True)
    if r.returncode == 0:
        r = subprocess.run(["nmcli", "con", "up", ssid],
                           capture_output=True, text=True)
        if r.returncode == 0:
            return True, f"Connected to {ssid}"
        subprocess.run(["nmcli", "con", "delete", ssid],
                       capture_output=True, text=True)

    cmd = ["nmcli", "device", "wifi", "connect", ssid]
    if password:
        cmd += ["password", password]
    r = subprocess.run(cmd, capture_output=True, text=True)

    if r.returncode == 0:
        return True, f"Connected to {ssid}"
    return False, f"Failed to connect to {ssid}"


def repo_in_pacman_conf(repo_name, conf_path="/etc/pacman.conf"):
    """Check if a repo section already exists in pacman.conf."""
    if not os.path.isfile(conf_path):
        return False
    with open(conf_path) as f:
        return f"[{repo_name}]" in f.read()


def update_mirrors():
    """Refresh Arch mirrors with reflector (leaves chaotic/custom mirrors untouched)."""
    run("reflector --latest 20 --sort rate --save /etc/pacman.d/mirrorlist")
    run("pacman -Syy")
