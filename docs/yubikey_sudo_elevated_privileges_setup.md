# YubiKey & USB-C Hardware Token Setup: "Tap for Privileged Action" (`sudo`)

This guide provides step-by-step installation and configuration instructions for generic YubiKeys, USB-C security keys, and FIDO2/U2F hardware tokens on Linux. By configuring PAM (`pam_u2f`), touching the physical metal sensor on either primary or backup YubiKey authorizes elevated (`sudo`) actions instantly.

---

## 1. Overview & How It Works

When executing privileged commands in LocalObserve (such as system-wide Falco kernel installations `task install-falco-system` or root container management), PAM checks your connected USB-C or USB-A YubiKey.

```
┌──────────────────────────┐                      ┌──────────────────────────┐
│  Developer Terminal      │ ─── sudo command ──> │  Linux PAM (/etc/pam.d)  │
│  "sudo task install-..." │                      │  pam_u2f.so              │
└──────────────────────────┘                      └────────────┬─────────────┘
                                                               │ Prompt: "Please touch device..."
                                                               ▼
                                                  ┌──────────────────────────┐
                                                  │  Physical YubiKey Tap    │
                                                  │  (USB-C / USB-A Sensor)  │
                                                  └────────────┬─────────────┘
                                                               │ Hardware Auth Granted!
                                                               ▼
                                                  ┌──────────────────────────┐
                                                  │  Executes as Root        │
                                                  └──────────────────────────┘
```

---

## 2. Package Installation

Install the required PAM U2F module and YubiKey manager utilities for your Linux distribution:

### Ubuntu / Debian / Linux Mint
```bash
sudo apt update && sudo apt install -y libpam-u2f pamu2fcfg yubikey-manager
```

### Fedora / RHEL / AlmaLinux / Rocky Linux
```bash
sudo dnf install -y pam_u2f pamu2fcfg yubikey-manager
```

### Arch Linux / Manjaro
```bash
sudo pacman -S pam-u2f yubikey-manager
```

---

## 3. Registering YubiKeys (USB-C & Backup Keys)

1. **Create the configuration directory**:
   ```bash
   mkdir -p ~/.config/Yubico
   ```

2. **Register Key #1 (Primary USB-C or USB-A YubiKey)**:
   - Insert your first YubiKey into the USB port.
   - Run the key generator tool:
     ```bash
     pamu2fcfg > ~/.config/Yubico/u2f_keys
     ```
   - **Action**: When the YubiKey LED flashes, **touch the metal sensor/button** on the key.

3. **Register Key #2 (Secondary / Backup YubiKey)**:
   - Unplug Key #1 and insert Key #2.
   - Append Key #2 using the `-n` flag:
     ```bash
     pamu2fcfg -n >> ~/.config/Yubico/u2f_keys
     ```
   - **Action**: Touch the metal sensor on Key #2 when it flashes.

4. **Verify Registered Keys File**:
   ```bash
   cat ~/.config/Yubico/u2f_keys
   ```
   *You should see two colon-delimited configuration lines corresponding to your two YubiKeys.*

---

## 4. Configuring PAM for `sudo` ("Tap for Privileged Action")

Edit `/etc/pam.d/sudo` to enable YubiKey touch authorization:

```bash
sudo nano /etc/pam.d/sudo
```

Add the `pam_u2f.so` line **above** `@include common-auth`:

```pam
# /etc/pam.d/sudo
# Allow physical YubiKey tap for sudo privileged actions
auth       sufficient   pam_u2f.so authfile=${HOME}/.config/Yubico/u2f_keys cue

@include common-auth
```

### Key PAM Option Flags Explained

| Option | Function |
| :--- | :--- |
| `sufficient` | **Passwordless Touch**: Tapping either YubiKey physical button alone authorizes `sudo` (no password typing required). |
| `required` | **Multi-Factor (2FA)**: Requires BOTH user password entry AND YubiKey physical tap. |
| `cue` | Displays user prompt in terminal: `Please touch the device to authorize privileges...` |
| `authfile=...` | Explicit path to registered keys file (`~/.config/Yubico/u2f_keys`). |

---

## 5. Verification & Testing

Open a **new terminal window** (keep your existing terminal open as a safety backup):

1. **Test `sudo` with YubiKey**:
   ```bash
   sudo whoami
   ```
2. **Terminal Output**:
   ```text
   Please touch the device to authorize privileges...
   ```
3. **Tap the YubiKey**: Touch the flashing physical metal sensor on either YubiKey.
4. **Result**: Output prints `root` instantly!

---

## 6. Integration with LocalObserve Tasks

With YubiKey PAM authorization configured, all privileged host management tasks run with a quick physical tap:

```bash
# System-wide Falco kernel installer
task install-falco-system

# Rootless / Rootful Podman cross-runtime verification
task verify-runtimes

# JIT Administrative Privilege Helper
python3 tools/compliance_rbac_jit.py elevate --duration 15m
```

---

### Kill Switch Step-Up Authentication

The local kill switch (`tools/kill_switch.py`) uses `sudo -v` as a step-up
authentication gate before executing process termination or container
isolation. With `pam_u2f.so` configured as described above, the `--prompt-yubikey`
flag requires a physical YubiKey touch. Without PAM U2F configuration, it falls
back to a standard sudo password prompt.

```bash
# Dry-run with step-up auth (test the auth flow without executing the kill)
python3 tools/kill_switch.py --id 718c5dbc-b1a3-419b-a329-e7721d294257 --dry-run --prompt-yubikey

# Live execution with YubiKey step-up
python3 tools/kill_switch.py --id 718c5dbc-b1a3-419b-a329-e7721d294257 --prompt-yubikey
```

> [!NOTE]
> The `--prompt-yubikey` flag triggers `sudo -v` regardless of dry-run mode,
> so the authentication flow can be tested without executing the actual kill action.

---

## 7. Troubleshooting & Emergency Fallback

- **YubiKey Not Flashing**: Verify USB-C port connectivity with `ykman info` or `lsusb`.
- **Bypass / Emergency Fallback**: If YubiKey is unplugged, PAM falls back to password authentication (if configured as `sufficient`) or switch terminals to edit `/etc/pam.d/sudo`.
