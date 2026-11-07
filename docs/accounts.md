# Accounts, passwords, and SSH

## Defaults

| Setting | Fresh build |
| --- | --- |
| Local account | `dev` (UID 1000), Bash, member of `sudo` |
| Account password | Chosen by you; there is no default |
| SSH account | `dev`, public-key login enabled; password login optional |
| Root SSH | Disabled in installed Debian |
| Sudo | Initially passwordless for `dev` |
| Hostname | `tabs3` |
| USB address | Tablet `172.16.42.2`, computer `172.16.42.1/30` |

The RAM diagnostic/recovery environment is different: it uses
`root@172.16.42.2`, key-only, and ephemeral host keys. Installed Debian has
persistent host keys generated at first boot.

For installed Debian, you can use SSH keys, account passwords, or both.
Fresh builds disable SSH password authentication until you enable it below.
The build still needs a public key for initial access and the separate recovery
environment, even if you choose password login for everyday use.

## Choose your key and account password before building

On your computer, from the repository:

```sh
install -d -m 700 private
ssh-keygen -t ed25519 -f private/id_ed25519 -C tabs3-owner
bash scripts/build-env.sh
bash scripts/set-dev-password.sh
```

Choose a key passphrase at the prompt. The password script prompts twice
without echo and saves only a SHA-512 crypt hash in
`private/dev-password.hash`, with private permissions. Use an SSH agent
(`ssh-add private/id_ed25519`) for automated tools with a protected key.

Supply **only the `.pub` file** to the builders:

```sh
bash scripts/build-rootfs.sh private/id_ed25519.pub
bash scripts/build-initramfs.sh private/id_ed25519.pub
```

Complete the other [build prerequisites](building.md) first. You may supply an
existing public key instead. Never copy the private half to the tablet, put
passwords in command arguments, or commit `private/`. Personalized rootfs and
boot images must not become public download images.

## First SSH connection

Configure [USB networking](user-guide.md#usb-ssh) and connect:

```sh
ssh -i private/id_ed25519 -o IdentitiesOnly=yes \
    -o UserKnownHostsFile=private/installed-known-hosts dev@172.16.42.2
```

Compare the first host-key fingerprint with the tablet console before accepting
it. On the console, run `sudo ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub`.
An unexpected key change needs investigation; do not disable global host-key
checking. After a deliberate reinstall, remove only the old entry in this
dedicated known-hosts file once the new fingerprint has been verified.

## Enable SSH password login

On installed Debian, sign in at the console or through your existing SSH key.
The password is the same account password chosen during the build. To set or
change it, run `passwd` as that user.

Open an administrator-owned configuration file:

```sh
sudoedit /etc/ssh/sshd_config.d/00-local-auth.conf
```

Add these settings, preserving any unrelated settings already in that file:

```sshdconfig
PubkeyAuthentication yes
PasswordAuthentication yes
KbdInteractiveAuthentication no
PermitRootLogin no
PermitEmptyPasswords no
```

This allows either a key or an account password. The local file is read before
`00-tabs3-server.conf` and `10-tabs3.conf`, so the project defaults do not
override your choice when you run `tabs3-server-enable` again. OpenSSH uses
the first value it reads for these settings; see the
[Debian SSH configuration reference](https://manpages.debian.org/trixie/openssh-server/sshd_config.5.en.html).

Validate the configuration and inspect the effective settings:

```sh
sudo /usr/sbin/sshd -t
sudo /usr/sbin/sshd -T -C user=dev,addr=172.16.42.1,host=usb-client \
    | grep -E '^(pubkeyauthentication|passwordauthentication|permitrootlogin|permitemptypasswords|authenticationmethods) '
```

For the standard configuration, expect `pubkeyauthentication yes`,
`passwordauthentication yes`, `permitrootlogin no`, `permitemptypasswords no`,
and `authenticationmethods any`. Use your actual username and client address
when checking a different account or Wi-Fi connection. Resolve validation
errors or conflicting local rules before reloading:

```sh
sudo systemctl reload ssh.service
```

Keep the existing session open while testing a second connection. From your
computer, force a password login to verify the choice:

```sh
ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no \
    -o UserKnownHostsFile=private/installed-known-hosts dev@172.16.42.2
```

Enter your account password at the prompt. Ordinary `ssh dev@172.16.42.2`
can use either enabled method. To return to key-only login, change
`PasswordAuthentication` to `no` in the same local file, validate, and reload.
These settings apply to installed Debian; diagnostic and recovery images
continue to use their configured root SSH key.

## Change a password or key

On installed Debian, logged in as `dev`, run `passwd`. This changes the local
account password, including the password used by SSH when password login is
enabled. It does not change your SSH keys or enable password authentication
on its own.

To replace a key, add its public half to `~/.ssh/authorized_keys`, test a second
connection, then remove the old public key. Keep `.ssh` at mode `700` and
`authorized_keys` at `600`, owned by the account.

## Use your own administrator name

The builder currently creates `dev`; it does not accept an arbitrary username.
Add your own administrator after first boot. Replace `alex` below:

```sh
sudo adduser alex
sudo usermod -aG sudo alex
sudo install -d -m 700 -o alex -g alex /home/alex/.ssh
sudo install -m 600 -o alex -g alex /home/dev/.ssh/authorized_keys \
    /home/alex/.ssh/authorized_keys
```

The `adduser` prompt sets the new account's password. Open a second SSH session
as `alex` and verify `sudo -v` before changing the original account. The example
copies the same authorized key; replace it if this user needs a different one.

Project tools default to `dev` and some use `sudo -n` for unattended work.
Update them before retiring `dev`. Locking a password alone does not revoke
that account's authorized SSH keys.

## Require a password for sudo

Keep your current administrator session open. Run:

```sh
sudo visudo -f /etc/sudoers.d/tabs3-dev
```

Replace its rule with `dev ALL=(ALL:ALL) ALL`. Run `sudo visudo -c`, then
test `sudo -k` followed by `sudo -v` in a second session. Unattended tools using
`sudo -n` will need a separate, scoped policy or an interactive invocation.

## Lost access

With a working SSH key, `sudo passwd dev` resets the console password. If
neither method works, use your configured recovery key and
[recovery procedure](maintenance.md). There is no shared recovery password
or remote reset service.
