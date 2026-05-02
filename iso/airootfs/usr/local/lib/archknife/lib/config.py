from dataclasses import dataclass, field
from typing import List


@dataclass
class Config:
    boot_mode: str = ""         # "uefi" or "bios"
    install_method: str = ""    # "pacstrap"
    keymap: str = ""
    timezone: str = ""
    locale: str = ""
    hostname: str = ""
    username: str = ""
    user_pass: str = ""
    root_pass: str = ""
    disk: str = ""
    filesystem: str = ""        # "ext4", "btrfs", "xfs"
    encrypt: bool = False       # LUKS encryption
    luks_pass: str = ""
    sshd: bool = False
    desktops: List[str] = field(default_factory=list)  # chosen DE/WM (multiple)

    # Extra repos to enable on installed system
    enable_chaotic: bool = True
    enable_nemesis: bool = False
    enable_boki: bool = False

    def ready(self) -> bool:
        if self.encrypt and not self.luks_pass:
            return False
        return all([
            self.keymap, self.timezone, self.locale,
            self.disk, self.hostname, self.username,
            self.user_pass, self.filesystem, self.desktops,
        ])
