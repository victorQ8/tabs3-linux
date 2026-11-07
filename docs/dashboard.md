# Panel dashboard and presence wake (`tabs3-dashboard`)

The server shows its own state on the tablet's panel without a desktop or a
web page: `tabs3-dashboard.service` draws straight into the framebuffer
(`/dev/fb0`, the DRM fbdev of the AMOLED panel) from a small Python program
using the Python imaging library. It takes virtual terminal 7 in graphics
mode so the text console on tty1 (still there for a USB keyboard) does not
paint over it, and gives the terminal back when it stops.

The picture is a quiet instrument panel rather than a grid of cards: a true
black background (unlit AMOLED pixels), one typeface (B612, the display
face Airbus designed for cockpit screens, with B612 Mono for figures;
`FONT_SET` in the configuration file offers five other sets, from Inter to
Atkinson Hyperlegible, each from a Debian font package), hairline-ruled
rows with an inline ten-minute sparkline each, and a single amber accent
that only appears for a warning (hot, warm, battery low, storage nearly
full, running on battery). The whole picture moves by a few pixels every
few minutes (`PIXEL_SHIFT_SECONDS`) so the panel keeps no ghost of it.

One frame every two seconds (`REFRESH` in `/etc/tabs3/dashboard.conf`):

- clock, date, uptime, load averages, hostname, package versions, the number
  of logged-in sessions;
- CPU use with a ten-minute graph, the current core clocks, GPU temperature;
- temperatures: the hottest CPU sensor, the board (AP) thermistor and the
  battery, with a ten-minute graph;
- battery: charge, status, current, voltage, external-power connection;
- memory and root storage;
- network interfaces with their addresses and rates, the remote processors
  (modem, audio DSP, sensor DSP) and the light sensor.

Version 0.1.9 distinguishes the keeper's intentional discharge from a lost
charger: with external power online and `charge_behaviour` actively set to
`force-discharge`, every theme says **Reducing to 80%** (or the configured
high target in `/etc/tabs3/battery.conf`). `inhibit-charge` says **Battery
resting**. Only the bracketed sysfs choice is treated as active; an unplugged
or unreadable charger never claims a deliberate descent. Voltage, current
and temperature remain real measurements. This is display wording only;
it does not change charger policy or the USB role.

Rendering pauses while the screen sleeps: `tabs3-screen.service`
(`tabs3-base`) blanks the panel after the idle time (60 s in the server
profile) and wakes it on a touch or the power key.

## Select a design

Version 0.1.2 adds three layouts alongside the original. The existing layout
stays the default, including when upgrading with an older configuration file.

| `THEME` | Design |
| --- | --- |
| `original` | The original instrument panel: large clock, ruled metric rows, inline history. |
| `observatory` | Mint CPU dial and a wide history plot, colored resource meters, connections and thermal readings. |
| `folio` | Warm ivory and copper, a serif clock, three large readings, and a quiet memory/storage/network footer. |
| `terminal` | A [btop-inspired](https://github.com/aristocratos/btop) monitor with framed plots, segmented meters, core clocks, network rates, and remote-processor states. |
| `silicon` | A true-black hardware portrait: brushed processor package with live CPU load, illuminated memory chips, a violet GPU die, and a power/storage/network rail. |

On the tablet (including over SSH), switch with one command:

```sh
sudo tabs3-dashboard-theme observatory
sudo tabs3-dashboard-theme folio
sudo tabs3-dashboard-theme terminal
sudo tabs3-dashboard-theme silicon
sudo tabs3-dashboard-theme original
```

The command saves the choice in `/var/lib/tabs3-dashboard/theme` (from 0.1.4;
`THEME` in `/etc/tabs3/dashboard.conf` is the default when nothing was
saved, so upgrades never meet a modified configuration file), restarts the
dashboard and asks the screen service to wake the panel. The choice survives
reboots. Run `tabs3-dashboard-theme` without an argument to show the saved
choice and available designs. You can also edit `THEME` in the configuration
and run `sudo systemctl restart tabs3-dashboard` yourself. `FONT_SET` still applies;
Folio uses DejaVu Serif from the existing font dependency for its large figures.
The alternatives use the same metrics, refresh loop, screen blanking, presence
wake and pixel shifting. They render on a black background without animations.
Folio intentionally emphasizes the clock and key readings; the original and
Terminal show the core clocks and firmware details.

Preview a layout without taking over the screen:

```sh
/usr/libexec/tabs3-dashboard --theme terminal --preview /tmp/terminal.png --fake
```

`--theme` overrides the configuration for that invocation. `TABS3_THEME` can
also override the configuration. An unknown theme exits with an explanation
before opening the framebuffer. Synthetic values are used only with
`--preview --fake`; ordinary service startup always reads actual measurements.

From the repository, `python3 tools/dashboard-preview` writes all five native
2048 × 1536 previews, normal/warning/missing-sensor states, a comparison PNG,
and a local `index.html` gallery to `work/dashboard-designs/`. The gallery's
design and state selectors work offline. Use `TABS3_FONT_DIR` to point at an
extracted Debian `/usr/share/fonts` tree when previewing on another distro;
otherwise unavailable typefaces use the existing fallback behavior.

Version 0.1.2 was installed on the tablet on 2026-10-14. All four layouts
were selected through `tabs3-dashboard-theme`; each rendered into the native
2048 × 1536 framebuffer with the panel awake and zero automatic service
restarts. Framebuffer captures were inspected, and the saved selection was
returned to `original`. The captures remain private because they contain
the tablet's network addresses. Local checks also covered missing sensors,
empty history, zero resource totals and preservation of unrelated settings.
Longer performance testing and the owner's physical readability check remain.

### Silicon hardware view

Version 0.1.7 adds `silicon`. The Snapdragon package carries aggregate CPU
utilization and temperature, with CPU history above and four sampled core
clocks below. Eight illustrated LPDDR4 packages share an occupancy meter
driven by total memory usage. The Adreno 530 die displays GPU temperature;
GPU utilization is not collected and is not inferred from CPU activity.
The bottom rail shows battery charge/current/voltage, root storage use,
network addresses and aggregate rates. Missing readings use dashes or an
explicit unavailable state; CPU heat, low battery and full storage retain
their warning colors.

The dark metal, contacts, traces and die pattern are generated with Pillow
and cached once per renderer. Only values, meters and the CPU sparkline
redraw, at the existing refresh rate.
It needs no image downloads, extra dependencies or GPU rendering. It keeps
the existing pixel shift and pauses with the other themes when the panel
sleeps. The original theme remains the installation default.

Preview with synthetic data:

```sh
/usr/libexec/tabs3-dashboard --theme silicon --preview /tmp/silicon.png --fake
```

The local gallery opens on Silicon and includes normal, warning and missing
sensor views for every theme. Version 0.1.7 was installed and its framebuffer
capture inspected on 2026-10-15; the owner approved the design on the tablet.
Version 0.1.8 reduces the header from 328 to 168 design pixels (21.4% to
10.9% of screen height), enlarges the processor package and utilization
figure, and adds a RAM history plot in the recovered space. Local checks
cover all six font sets, warnings, missing readings, long hostnames, 100%
CPU use, empty history, zero totals and pixel shifting. Version 0.1.8 was
then installed on the tablet, with Silicon saved, the panel awake, and zero
automatic dashboard restarts. Its live framebuffer capture was inspected;
longer on-tablet performance testing remains.

The owner approved the compact header and requested removal of the original
0.1.7 layout backup. Its local backup was moved to the PC's Trash, and the
tablet's backup copy was deleted. Silicon 0.1.8 remains selected.

## Presence wake

While the screen is off the dashboard watches four sources and, when one
of them changes, opens and closes the pipe `/run/tabs3-screen/wake`
(`tabs3-base` 0.1.20), which `tabs3-screen` treats like a touch:

- the light sensor (`qcom-smgr-light`): an illuminance change of at least
  `LIGHT_CHANGE_PERCENT` (35 %) and `LIGHT_CHANGE_LUX` (3 lux) against a
  slowly following baseline, so a shadow falling on the tablet or a light
  switched on wakes it. This is the sensor that does the work: the tablet
  lives upright on a mount, where someone walking up to it changes the
  light at the sensor long before they touch anything;
- the accelerometer (`qcom-smgr-accel`), off by default
  (`WAKE_ON_MOTION=0`) because a mounted tablet is never picked up: two
  consecutive samples whose magnitude differs by `MOTION_THRESHOLD`
  (0.25 m/s^2) from the resting value. For a tablet lying on a desk,
  `WAKE_ON_MOTION=1` makes a hand on the desk or picking it up wake it;
- the analog microphone (`tabs3-dashboard` 0.1.3): an ALSA capture on
  `SOUND_DEVICE` (`hw:0,2`, the WCD9335 ADC3 through the audio DSP, routed
  with the same mixer settings as the UCM "Mic" device) measured in 100 ms
  windows; a level at least `SOUND_RISE_DB` (15 dB) above the quietest window
  of the last half minute and at least `SOUND_MIN_DBFS` (-50 dBFS) loud, on
  two consecutive polls, wakes the screen, so footsteps or a voice do it in
  any lighting (the room floor is about -66 dBFS, speech peaks near -32).
  The capture starts at the first screen-off and then stays open: closing
  a capture stalls the audio DSP for five seconds ("CMD 10bcd timeout") and
  the next one can come back silent. With the screen off the dashboard uses
  about 2.4 % of a core and the capture 0.5 % (measured 2026-10-14); a
  quiet room produced no false wake;
- the front camera (`tabs3-dashboard` 0.1.5 with `tabs3-base` 0.1.25 and
  kernel package 65): every `CAMERA_INTERVAL` seconds (4) a 640x480 frame
  is taken through the raw CAMSS path (`tabs3_camera`; the camera is
  powered for about half a second), metered so that its exposure follows
  the room, reduced to a 40x30 grid and compared with the previous grid at
  equal brightness. A mean change of `CAMERA_CHANGE_PERCENT` (3.5 %) of the
  picture's level wakes the screen, so someone moving in the room does it
  without a sound and without changing the light at the sensor; a still,
  lit room measures 0.2 to 0.3 %. In the dark (nothing above the black
  level at the longest exposure) the camera samples four times slower and
  detects nobody. Frames live only in memory, nothing is written, and the
  camera is not sampled while the screen is on. With the screen off and
  the sampler running the dashboard used 3.4 % of a core over two minutes
  (measured 2026-10-14), about one percent more than before.

The sensors are ignored for `SETTLE_AFTER_OFF` seconds after the screen goes
off, because the panel switching off is itself a light change, and at most
one wake happens every `WAKE_HOLDOFF` seconds. The last wake and its cause
are shown on the dashboard's bottom line. Each sensor can be turned off in
the configuration file; the thresholds are starting points to tune for the
place where the tablet hangs.

The framebuffer only exists once the display driver has probed, which can be
after `multi-user.target`; the package's udev rule tags `/dev/fb0` for
systemd and starts the service when the device appears, and the service
binds to `dev-fb0.device` instead of testing for the node once.

The tablet has no infrared or radar presence sensor, so a silent person
standing still in unchanged light is not detected even by the camera; a
Bluetooth phone-proximity trigger is the next candidate.

## Camera pictures

The dashboard shows no camera picture: 0.1.5 put one from the front camera
in a corner of the panel and 0.1.6 removed it at the owner's request, who
wants the camera for the presence wake only. Pictures are taken on the
command line with `tabs3-snapshot` (`tabs3-base` 0.1.25):

```sh
sudo tabs3-snapshot --camera front /srv/pictures/room.png
sudo tabs3-snapshot --camera rear --size 1048x780 --quiet rear.png
```

meters the frame in a few steps (exposure first up to 1/30 s, then analogue
gain up to 8x, then longer exposures up to half a second, backing off when
lamps saturate more than 4 % of the picture), focuses the rear camera's
lens with a contrast sweep (`--focus auto`, the default since `tabs3-base`
0.1.26 and kernel package 66; a position 0 to 1023 or `none` instead) and
writes a half-size colour
picture (black level, grey-world white balance, gamma 2.2; colour needs
`python3-numpy`, otherwise the grey 8-bit view). The full front frame takes
about six seconds with the decode, the binned modes about two.

## Build, install, check

```sh
bash scripts/build-dashboard-package.sh          # artifacts/tabs3-dashboard_<version>_all.deb
sudo apt install ./tabs3-base_0.1.21_all.deb ./tabs3-dashboard_0.1.2_all.deb   # on the tablet
systemctl status tabs3-dashboard tabs3-screen
journalctl -u tabs3-dashboard -b
/usr/libexec/tabs3-dashboard --preview /tmp/frame.png     # one frame to a file, no panel
```
