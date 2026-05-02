# fix for screen readers
if grep -Fqa 'accessibility=' /proc/cmdline &> /dev/null; then
    setopt SINGLE_LINE_ZLE
fi

~/.automated_script.sh

# Auto-launch archknife installer on tty1
if [[ $(tty) == "/dev/tty1" ]]; then
    /usr/local/bin/archknife
fi
