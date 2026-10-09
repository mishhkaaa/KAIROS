# KAIROS OS: a prompt with the mark, and the system line once per login shell.
case $- in *i*) ;; *) return ;; esac
if [ -n "$BASH_VERSION" ]; then
  PS1='\[\e[38;5;30m\]▚\[\e[0m\] \[\e[1m\]\u@\h\[\e[0m\]:\[\e[38;5;33m\]\w\[\e[0m\]\$ '
fi
alias org='cd /org'
if [ -z "$KAIROS_BANNER_SHOWN" ] && command -v kairos >/dev/null; then
  export KAIROS_BANNER_SHOWN=1
  # The first shell can start with the distro: give the /org service a few seconds to mount.
  for _ in $(seq 1 25); do mountpoint -q /org && break; sleep 0.2; done
  kairos banner 2>/dev/null
  mountpoint -q /org || echo "  /org is not mounted yet: sudo systemctl start kairos-orgfs"
fi
