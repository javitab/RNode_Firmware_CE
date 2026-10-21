# WisBlock 1W with RNode BLE

## Target and compatibility

The experimental `wisblock_1w` target is for a **RAK3401 nRF52840 core +
RAK13302 SX1262/SKY66122 module in the IO slot of a RAK19007 base**, as used by
the RAK10724 WisMesh 1W kit. It is not the ordinary RAK4631's onboard radio.
The documented RAK13302 VC/VD radio band is **902-928 MHz**; other RF variants
have not been evaluated.

The firmware remains an RNode modem, not a standalone RatTunnel transport:
USB serial and encrypted Nordic UART BLE carry the existing RNode KISS
protocol, including split-packet framing. Run Reticulum on a connected host.
There is no on-device Wi-Fi or Reticulum TCP server.

The target deliberately uses the RAK4631-compatible BSP and RNode identification
(`BOARD_MODEL=0x51`, product `0x10`, model `0x12`) so existing host provisioning
and protocol tools can be used without inventing unsupported host identifiers.
The separate `WISBLOCK_1W` build flag selects the external radio wiring and BLE
policy. This compatibility identity does **not** make an ordinary RAK4631 image
safe to use on this stack. It also does not extend the RAK13302's physical band
to the wider range advertised by host tools for model `0x12`.

## Radio wiring and power

Pins below are nRF GPIO numbers as used by the RAK Arduino BSP.

| Signal | Pin/configuration |
| --- | --- |
| SPI NSS / SCK / MOSI / MISO | 26 / 3 / 30 / 29, SPIM3 |
| BUSY / RESET | 9 (WB_IO5) / 4 (WB_IO4) |
| Module supply enable | 34 (WB_IO2), high before radio initialization |
| FEM enable / ANT_SW | 21 (WB_IO3), high in both RX and TX |
| RX notification | SX1262 IRQ-register polling; no GPIO interrupt |
| TX/RX switch | SX1262 DIO2 |
| TCXO | DIO3, 1.8 V, 5 ms startup |
| Regulator | SX1262 DC-DC |
| LEDs | blue 36 (RX), green 35 (TX) |

The reference firmware reports P15 as floating and polls IRQ status. This target
also polls, but does not reproduce the reference's GPIO brute-force discovery or
fallback pin probing. RAK's connector table actually routes DIO1 to IO6, not P15;
polling avoids relying on the reference's incorrect DIO1 candidate. The normal
RNode framing callback runs in task context, with task-context queue operations.
The button assigned to P9 on ordinary RAK4631 builds is disabled here because P9
is BUSY. Battery monitoring is disabled rather than reusing unverified calibration.

**The full SX1262 drive range up to 22 dBm is available; there is no 17 dBm cap.**
Set the host's `txpower` to `22` to request full chip drive. RNode's TX-power
readback is the **chip setting**, not a measurement of amplified antenna output.
Do not request `30` as if the chip itself could supply 30 dBm.

RAK's [VC datasheet](https://docs.rakwireless.com/product-categories/wisblock/rak13302/datasheet/#transmit-power-vs-peak-current)
and [VD datasheet](https://docs.rakwireless.com/product-categories/wisblock/rak13302/datasheet-vd/#transmit-power-vs-peak-current)
both explicitly specify **22 dBm SX1262 configuration, nominal 30.0 dBm module
output, and 1000 mA peak current at 5 V**. This module-level operating point,
not an assumed amplifier gain or the reference's 17 dBm brownout mitigation,
is the basis for permitting 22 dBm. Actual output, harmonics, temperature and
supply stability have not been measured for this firmware.

Follow the [manufacturer's power instructions](https://docs.rakwireless.com/product-categories/wisblock/rak13302/quickstart/).
USB on the base alone is not a substitute for the correct PA supply:
VC uses a power-selection jumper; VD `001` is battery-powered and VD `002`
requires the module's external 5 V input. Use the correct battery or regulated
5 V / 1.5 A supply for the particular module variant. Always connect a suitable
antenna or rated load before powering the radio. Respect local frequency,
EIRP, duty-cycle and licensing limits; full drive is not legal everywhere.

## Build

Install Arduino CLI, GNU Make, Python 3 and the RAK nRF52 BSP. The minimal
dependencies for this headless target are:

```sh
arduino-cli core install rakwireless:nrf52@1.3.3 --config-file arduino-cli.yaml
arduino-cli lib install "Crypto@0.4.0"
make firmware-wisblock_1w
```

To also create the drag-and-drop UF2, use:

```sh
make uf2-wisblock_1w
```

The Make target stages the sketch under its required Arduino folder name, so
it also works from renamed clones and Git worktrees. Artifacts are exported to:

```text
build/wisblock_1w/RNode_Firmware_CE.ino.hex
build/wisblock_1w/RNode_Firmware_CE.ino.zip
build/wisblock_1w/RNode_Firmware_CE.ino.uf2
```

The ZIP is the application-only serial DFU package. The UF2 is the application
image for the RAK BSP's nRF52840 UF2-compatible bootloader; the converter uses
the same family identifier (`0xADA52840`) specified in that BSP's platform.
Neither package contains a full-chip erase, SoftDevice or bootloader image.

## Flash and provision manually

These are instructions for an operator; no device is flashed by the build or
host tests. Install `rns` (for `rnodeconf`), `adafruit-nrfutil` and `pyserial`
using your preferred Python environment. Back up any existing configuration.

### UF2 bootloader drive (double-reset)

Build with `make uf2-wisblock_1w`, press RESET twice to enter the bootloader,
and wait for the USB drive to mount in Finder. Check `INFO_UF2.TXT` on the drive
identifies a UF2-capable nRF52840 bootloader. Drag this exact file from the
repository onto that drive:

```text
build/wisblock_1w/RNode_Firmware_CE.ino.uf2
```

Wait for the copy to finish and the board to restart before disconnecting it.
Do not drag the `.hex` or `.zip` there. This UF2 contains blocks tagged with the
RAK BSP's nRF52840 family ID and targets the compiled application's addresses;
the double-reset drive must be the matching UF2/Adafruit-compatible nRF52840
bootloader, not an arbitrary USB volume or serial-only DFU bootloader. A UF2
bootloader can reject a mismatched family ID or an image outside its permitted
application region.

On the tested RAK UF2 bootloader 0.4.3, application-size metadata used by
RNode's firmware hash calculation was not populated by the UF2 transfer: the
running hash was the SHA-256 of empty input. Application-only serial DFU
populated it correctly. If this occurs, use serial DFU below and compare the
device's `rnodeconf "$PORT" -L` result with the BIN hash before setting the
expected hash. Do not store an empty-input hash to make validation pass.

This UF2 procedure writes the compiled application image directly. If firmware
signature/hash validation or host provisioning is needed, use the serial DFU
and `rnodeconf` procedure below instead; UF2 flashing does not perform that
post-flash provisioning step.

### Serial DFU and host provisioning

Set `PORT` to the actual device (for example `/dev/ttyACM0` on Linux or the
appropriate `/dev/cu.usbmodem...` on macOS). Double-tap RESET to enter the RAK
bootloader if necessary, then upload only the package just built:

```sh
arduino-cli upload build/wisblock_1w/sketch/RNode_Firmware_CE \
  --fqbn rakwireless:nrf52:WisCoreRAK4631Board \
  --input-dir build/wisblock_1w --port "$PORT"
```

After reboot, check the port again. On an unprovisioned device, generate your
local signing key if needed and provision the compatibility identity:

```sh
rnodeconf -k
rnodeconf "$PORT" -r --platform NRF52 --model 12 --product 10 --hwrev 1
```

Record the hash of the application BIN inside the DFU ZIP, as required by
the existing nRF52 firmware-validation path:

```sh
unzip -o build/wisblock_1w/RNode_Firmware_CE.ino.zip -d build/wisblock_1w
rnodeconf "$PORT" --firmware-hash \
  "$(shasum -a 256 build/wisblock_1w/RNode_Firmware_CE.ino.bin | cut -d ' ' -f 1)"
```

Do not hash the HEX, ZIP or ELF. Do not use an upstream RAK4631 autoinstall
or firmware-update image: it lacks the `WISBLOCK_1W` flag. Keep the build's
source available with any distributed firmware, in accordance with GPLv3.

## Connect and use BLE

For this target only, BLE starts at every boot, even with blank configuration
or a previously saved Bluetooth-disable setting. Pairing stays available while
BLE is on; there is no button/display requirement or 35-second pairing timeout.
Other boards retain their generated PIN and pairing-window behavior.

Select **`RNode XXXX`** in a BLE-capable RNode client's discovery view and enter
**`123456`** when prompted. This is BLE Nordic UART, not Bluetooth Classic SPP.
After initial bonding the firmware disconnects, as on upstream nRF52 builds;
reconnect to use the modem. UART access still requires encryption with MITM
protection, and Just Works bonds are rejected. Advertising restarts after
disconnect or a failed pairing attempt. A runtime Bluetooth-off command stops
advertising and disconnects; turning it on restores discovery. A reboot enables
BLE again. If a client retained an incompatible bond, forget the device on the
client and retry pairing.

**The public fixed PIN is weak pairing protection.** Anyone nearby who knows
it can pair and control the modem while BLE is enabled. Do not treat the PIN
as authentication of a trusted operator. Use a BLE-capable RNode host/client;
an ordinary terminal or a client supporting only Classic SPP will not work.

### Read-only USB discovery diagnostics

Use a BLE scanner such as LightBlue or nRF Connect with Bluetooth permission
granted; the normal macOS Bluetooth settings list may omit this Nordic UART
peripheral. Scan for `RNode XXXX` or service UUID
`6E400001-B5A3-F393-E0A9-E50E24DCCA9E`.

On `wisblock_1w` only, KISS request bytes `C0 46 FF C0` return the configured
name and current Bluetooth status without toggling BLE, pairing, or writing
configuration. The response is a KISS-escaped frame with command `46`, selector
`FF`, format version `01`, then six one-byte fields: stack ready, RNode Bluetooth
state, enabled, pairing allowed, advertising running, and initial advertising
start succeeded. Remaining bytes are the ASCII device name (no NUL terminator).
State values follow `Config.h`; an advertising-running flag confirms the stack
reports advertising, not that an external receiver has detected it.

Configure matching radio parameters on the connected host and peer, within
the module's supported band: for example 915000000 Hz, 125000 Hz bandwidth,
SF9, coding rate 4/5 and `txpower=22`. The firmware keeps the RNode sync word,
CRC and packet framing rather than importing RatTunnel's application protocol.

## Evidence and remaining hardware checks

`make test-wisblock_1w` runs host-compiled checks of the real board definitions,
BLE lifecycle functions, radio polling and TX-power setter with mocked hardware
APIs. It covers legacy/new pin isolation, fixed versus generated PINs, pairing
timeout behavior, reconnect/stop/start, encrypted UART permissions, rejected
Just Works bonds, rejected CRC/header-error/empty packets and 22 dBm drive.
These checks require Python 3 and a host `c++` compiler.

The target has compiled with RAK nRF52 BSP 1.3.3 and Crypto 0.4.0. On one
connected board, application-only serial DFU and EEPROM provisioning succeeded;
the device's running firmware hash and stored target hash matched the compiled
BIN. USB diagnostics reported advertising active, and the operator confirmed
the named device appeared in a phone's BLE scanner. This does not verify BLE
pairing, encrypted UART transport or RF output. On real hardware,
verify cold boot without USB, initial pairing, incorrect-PIN rejection, bonded
reconnect, runtime BLE off/on, USB and BLE KISS exchange, bidirectional LoRa
including split packets, RF output/spectral compliance and power/temperature
stability at 22 dBm drive.

## Source and attribution

The hardware investigation used
[hipstereclipse/rns-transport-wisblock1w](https://github.com/hipstereclipse/rns-transport-wisblock1w/tree/204995ab486a28739b3a8a2682393e32de3299c6),
especially `include/RNSConfig.h` and `include/RNSRadio.h`, whose README
declares Apache 2.0. Only hardware facts and initialization requirements were
used; no RatTunnel application code, diagnostics or transport implementation
were copied. The firmware remains based on RNode Firmware CE under GPLv3
with its existing source notices. RAK's connector/power tables additionally
identify IO3 as ANT_SW/FEM enable and document the 22 dBm operating point.
