"""Host-side regression checks; these do not emulate BLE or RF hardware."""

from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


def method(source, signature):
    start = source.index(signature)
    opening = source.index("{", start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


class FirmwareTests(unittest.TestCase):
    def compile_run(self, source, headers=None, flags=()):
        compiler = shutil.which("c++")
        self.assertIsNotNone(compiler, "A host C++ compiler is required")
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            for name, content in (headers or {}).items():
                (directory / name).write_text(content)
            (directory / "test.cpp").write_text(source)
            result = subprocess.run(
                [compiler, "-std=c++11", "-I", str(directory), "-I", str(ROOT),
                 *flags, str(directory / "test.cpp"), "-o", str(directory / "test")],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            subprocess.run([str(directory / "test")], check=True)

    def test_board_mapping_and_legacy_isolation(self):
        source = r"""
#include <cassert>
#include <cstdint>
#define NRF52840_XXAA
#define SS 26
#define WB_IO1 17
#define WB_IO2 34
#define WB_IO4 4
#define LED_BLUE 36
#define LED_GREEN 35
#include "Boards.h"
int main() {
    static_assert(INTERFACE_COUNT == 1, "single SX1262");
    assert(interfaces[0] == SX1262);
    assert(!interface_cfg[0][0] && interface_cfg[0][1] && interface_cfg[0][2]);
#ifdef WISBLOCK_1W
    static_assert(HAS_BLE && !HAS_INPUT && !HAS_PMU, "headless BLE target");
    static_assert(BLE_PAIRING_PIN == 123456, "fixed PIN");
    const int8_t expected[] = {26, 3, 30, 29, 9, -1, 4, -1, 21, 34};
#else
    static_assert(HAS_BLE && HAS_INPUT && HAS_PMU, "legacy unchanged");
#ifdef BLE_PAIRING_PIN
#error "Fixed PIN must not apply to legacy boards"
#endif
    const int8_t expected[] = {42, 43, 44, 45, 46, 47, 38, -1, 37, -1};
#endif
    for (int i = 0; i < 10; ++i) assert(interface_pins[0][i] == expected[i]);
}
"""
        for target in (False, True):
            with self.subTest(wisblock_1w=target):
                flags = ["-DBOARD_MODEL=0x51", "-DBOARD_VARIANT=0x12"]
                if target:
                    flags.append("-DWISBLOCK_1W")
                self.compile_run(source, {"variant.h": ""}, flags)

    def test_ble_lifecycle_and_legacy_pin(self):
        source = r"""
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#define MCU_VARIANT 0x71
#define MCU_NRF52 0x71
#define MCU_ESP32 0x81
#define HAS_EEPROM false
#define BLE_RX_BUF 6144
#define BLE_PAIRING_PIN 123456
#define BLE_MANUFACTURER "RAK Wireless"
#define BLE_MODEL "RAK3401 + RAK13302"
#define BT_ENABLE_BYTE 0x73
#define ADDR_CONF_BT 0
#define ADDR_SIGNATURE 1
#define eeprom_addr(x) (x)
#define BT_STATE_OFF 0
#define BT_STATE_ON 1
#define BT_STATE_PAIRING 2
#define BT_STATE_CONNECTED 3
#define CABLE_STATE_DISCONNECTED 0
#define BLE_GAP_SEC_STATUS_SUCCESS 0
#define BLE_GAP_PHY_2MBPS 2
#define BANDWIDTH_MAX 1
#define SECMODE_ENC_WITH_MITM 3
#define BLE_GAP_ADV_FLAGS_LE_ONLY_GENERAL_DISC_MODE 2
uint8_t bt_state = BT_STATE_OFF, cable_state = 1;
uint32_t bt_ssp_pin = 0, now = 0;
bool bt_ready = false, bt_enabled = false, bt_allow_pairing = false;
bool console_active = false;
uint32_t millis() { return now; }
long random(long) { return 0; }
int indications = 0;
void kiss_indicate_btpin() { ++indications; }
struct ble_gap_conn_sec_mode_t { int sm = 1, lv = 3; };
struct ble_gap_addr_t { uint8_t addr[6] = {}; };
struct BLEConnection {
    ble_gap_conn_sec_mode_t mode;
    int disconnects = 0, debonds = 0;
    ble_gap_conn_sec_mode_t getSecureMode() { return mode; }
    bool bonded() { return true; }
    void removeBondKey() { ++debonds; }
    void disconnect() { ++disconnects; }
    void requestPHY(int) {}
    void requestMtuExchange(int) {}
    void requestDataLengthUpdate() {}
};
struct BLEUart {
    int starts = 0, read_permission = 0, write_permission = 0;
    BLEUart(int) {}
    void flushTXD() {}
    void bufferTXD(bool) {}
    void setPermission(int r, int w) { read_permission = r; write_permission = w; }
    void begin() { ++starts; }
};
struct BLEDis {
    int starts = 0;
    void setManufacturer(const char*) {}
    void setModel(const char*) {}
    void begin() { ++starts; }
};
struct BLEBas { void begin() {} };
struct Security {
    std::string pin;
    bool mitm = false;
    void setIOCaps(bool, bool, bool) {}
    void setMITM(bool value) { mitm = value; }
    template<class T> void setPairPasskeyCallback(T) {}
    template<class T> void setSecuredCallback(T) {}
    template<class T> void setPairCompleteCallback(T) {}
    void setPIN(const char* value) { assert(strlen(value) == 6); pin = value; }
};
struct Advertising {
    int starts = 0, stops = 0, clears = 0;
    int flags = 0, names = 0, services = 0, power_fields = 0, bytes = 0;
    int fast_interval = 32, slow_interval = 244, fast_timeout = 30;
    bool running = false;
    void restartOnDisconnect(bool) {}
    void clearData() { ++clears; bytes = flags = names = services = power_fields = 0; }
    bool add(int count) { if (bytes + count > 31) return false; bytes += count; return true; }
    bool addFlags(int) { ++flags; return add(3); }
    bool addTxPower() { ++power_fields; return add(3); }
    bool addService(BLEUart&) { ++services; return add(18); }
    bool addName() { ++names; return add(12); }
    void setInterval(int fast, int slow) { fast_interval = fast; slow_interval = slow; }
    void setFastTimeout(int timeout) { fast_timeout = timeout; }
    bool start(int) { ++starts; running = true; return true; }
    bool isRunning() { return running; }
    void stop() { ++stops; running = false; }
};
struct Periph {
    template<class T> void setDisconnectCallback(T) {}
    void setConnInterval(int, int) {}
};
struct MockBluefruit {
    struct Security Security;
    struct Advertising Advertising, ScanResponse;
    struct Periph Periph;
    BLEConnection connection;
    int disconnects = 0;
    void configPrphBandwidth(int) {}
    void autoConnLed(bool) {}
    bool begin() { return true; }
    void setTxPower(int) {}
    void setName(const char*) {}
    ble_gap_addr_t getAddr() { return {}; }
    BLEConnection* Connection(uint16_t) { return &connection; }
    bool connected() { return true; }
    uint16_t connHandle() { return 0; }
    void disconnect(uint16_t) { ++disconnects; }
} Bluefruit;
struct MD5 {
    static unsigned char* make_hash(char*, int) {
        static unsigned char hash[16] = {};
        return hash;
    }
};
uint8_t eeprom_read(uint32_t) { return 0; }
#include "Bluetooth.h"
std::string diagnostic;
void serial_write(uint8_t byte) { diagnostic += char(byte); }
void escaped_serial_write(uint8_t byte) {
    if (byte == 0xc0) { serial_write(0xdb); serial_write(0xdc); }
    else if (byte == 0xdb) { serial_write(0xdb); serial_write(0xdd); }
    else { serial_write(byte); }
}
#define FEND 0xc0
#define CMD_BT_CTRL 0x46
void query_status(uint8_t sbyte) {
DIAGNOSTIC_QUERY
}
int main() {
    assert(bt_init());
    assert(Bluefruit.Security.mitm);
#ifdef WISBLOCK_1W
    assert(bt_enabled && bt_allow_pairing && bt_state == BT_STATE_ON);
    assert(Bluefruit.Security.pin == "123456");
    assert(bt_advertising_started);
    assert(Bluefruit.Advertising.flags == 1 && Bluefruit.Advertising.names == 1);
    assert(Bluefruit.Advertising.services == 0 && Bluefruit.Advertising.power_fields == 0);
    assert(Bluefruit.Advertising.bytes == 15);
    assert(Bluefruit.ScanResponse.services == 1 && Bluefruit.ScanResponse.names == 0);
    assert(Bluefruit.ScanResponse.bytes == 18);
    assert(Bluefruit.Advertising.fast_interval == 160);
    assert(Bluefruit.Advertising.slow_interval == 160);
    assert(Bluefruit.Advertising.fast_timeout == 0);
    int initial_starts = Bluefruit.Advertising.starts;
    query_status(0xff);
    const unsigned char expected_status[] = {
        0xc0, 0x46, 0xff, 1, 1, BT_STATE_ON, 1, 1, 1, 1
    };
    assert(diagnostic.size() == sizeof(expected_status) + strlen(bt_devname) + 1);
    assert(memcmp(diagnostic.data(), expected_status, sizeof(expected_status)) == 0);
    assert(diagnostic.substr(sizeof(expected_status), strlen(bt_devname)) == bt_devname);
    assert(uint8_t(diagnostic.back()) == FEND);
    assert(Bluefruit.Advertising.starts == initial_starts);
    assert(SerialBT.read_permission == 3 && SerialBT.write_permission == 3);
    now = 40000;
    update_bt();
    assert(bt_allow_pairing);
    bt_enable_pairing();
    assert(bt_get_passkey() == 123456 && indications == 1);
    bt_pairing_complete(0, 0);
    assert(bt_allow_pairing && bt_get_passkey() == 123456);
    bt_disconnect_callback(0, 19);
    assert(bt_state == BT_STATE_ON && Bluefruit.Advertising.starts == 2);
    Bluefruit.connection.mode.lv = 2;
    bt_pairing_complete(0, 0);
    assert(Bluefruit.connection.debonds == 1);
    bt_stop();
    assert(!bt_allow_pairing && bt_state == BT_STATE_OFF);
    assert(Bluefruit.Advertising.stops == 1 && Bluefruit.disconnects == 1);
    diagnostic.clear();
    query_status(0xff);
    assert(diagnostic[5] == BT_STATE_OFF && diagnostic[8] == 0);
    assert(Bluefruit.Advertising.stops == 1);
    int starts = Bluefruit.Advertising.starts;
    bt_disconnect_callback(0, 19);
    bt_connect_callback(0);
    bt_pairing_complete(0, 0);
    assert(Bluefruit.Advertising.starts == starts && bt_state == BT_STATE_OFF);
    bt_start();
    assert(bt_allow_pairing && bt_get_passkey() == 123456);
    assert(SerialBT.starts == 1 && bledis.starts == 1);
    assert(Bluefruit.Advertising.clears == 2);
    assert(Bluefruit.Advertising.bytes == 15 && Bluefruit.ScanResponse.bytes == 18);
#else
    assert(!bt_enabled && !bt_allow_pairing && bt_state == BT_STATE_OFF);
    assert(Bluefruit.Security.pin == "100000");
    bt_enable_pairing();
    assert(Bluefruit.Advertising.bytes == 24 && Bluefruit.ScanResponse.bytes == 12);
    assert(Bluefruit.Advertising.fast_interval == 32);
    assert(Bluefruit.Advertising.slow_interval == 244);
    now = 40000;
    update_bt();
    assert(!bt_allow_pairing && pairing_pin == 0);
#endif
}
"""
        handler = (ROOT / "RNode_Firmware_CE.ino").read_text()
        handler = handler[handler.index("} else if (command == CMD_BT_CTRL)"):]
        query = method(handler, "if (sbyte == 0xFF)")
        source = source.replace(
            "DIAGNOSTIC_QUERY", "#ifdef WISBLOCK_1W\n" + query + "\n#endif"
        )
        for target in (False, True):
            with self.subTest(wisblock_1w=target):
                self.compile_run(source, {"bluefruit.h": ""},
                                 ["-DWISBLOCK_1W"] if target else [])

    def test_irq_polling_and_full_chip_drive(self):
        radio = (ROOT / "Radio.cpp").read_text()
        methods = "\n".join(
            method(radio, signature) for signature in (
                "void sx126x::poll()", "void sx126x::setTxPower(",
                "void sx126x::enableTCXO()", "void sx126x::onReceive(",
            )
        )
        defines = "\n".join(line for line in radio.splitlines()
                            if line.startswith("#define "))
        source = r"""
#include <cassert>
#include <cstdint>
#define OCP_TUNED 0x40
#define WISBLOCK_1W
#define INPUT 0
#define RISING 1
#define INTERFACE_COUNT 1
int attaches = 0, detaches = 0;
void pinMode(int pin, int) { assert(pin >= 0); }
int digitalPinToInterrupt(int pin) { assert(pin >= 0); return pin; }
void attachInterrupt(int, void(*)(), int) { ++attaches; }
void detachInterrupt(int) { ++detaches; }
void (*onIntRise[1])() = {nullptr};
""" + defines + r"""
struct sx126x {
    int _dio0 = -1, _index = 0, callbacks = 0, resumes = 0, standbys = 0, tx_drive = 0;
    int _implicitHeaderMode = 0, _payloadLength = 255, last_receive_size = -1;
    bool _radio_online = true, _tcxo = true, valid = true;
    void (*_onReceive)(uint8_t, int) = [](uint8_t, int) {};
    int8_t _txp = 0;
    uint8_t irq = IRQ_RX_DONE_MASK_6X, length = 10, tcxo_voltage = 0;
    void executeOpcodeRead(int opcode, uint8_t* buffer, int) {
        if (opcode == OP_GET_IRQ_STATUS_6X) buffer[1] = irq;
        else if (opcode == OP_RX_BUFFER_STATUS_6X) buffer[0] = length;
    }
    bool getPacketValidity() { irq = 0; return valid; }
    void standby() { ++standbys; }
    void receive(int size = 0) {
        ++resumes;
        last_receive_size = size;
        if (size > 0) {
            _implicitHeaderMode = 1;
            _payloadLength = size;
        } else {
            _implicitHeaderMode = 0;
        }
    }
    void handleDio0Rise() { ++callbacks; }
    uint8_t readRegister(int) { return 0; }
    void writeRegister(int, int) {}
    void executeOpcode(int opcode, uint8_t* buffer, int) {
        if (opcode == OP_TX_PARAMS_6X) tx_drive = static_cast<int8_t>(buffer[0]);
        if (opcode == OP_DIO3_TCXO_CTRL_6X) tcxo_voltage = buffer[0];
    }
    void poll();
    void onReceive(void(*callback)(uint8_t, int));
    void setTxPower(int, int);
    void enableTCXO();
};
""" + methods + r"""
int main() {
    sx126x radio;
    radio.onReceive([](uint8_t, int) {});
    assert(attaches == 0);
    radio.poll();
    assert(radio.callbacks == 1 && radio.resumes == 1 && radio.irq == 0);
    radio.poll();
    assert(radio.callbacks == 1);
    radio.irq = IRQ_RX_DONE_MASK_6X;
    radio.valid = false;
    radio.poll();
    assert(radio.callbacks == 1 && radio.resumes == 2);
    radio.valid = true;
    radio.irq = IRQ_RX_DONE_MASK_6X | IRQ_HEADER_ERROR_MASK_6X;
    radio.poll();
    assert(radio.callbacks == 1 && radio.resumes == 3);
    radio.irq = IRQ_RX_DONE_MASK_6X;
    radio.length = 0;
    radio.poll();
    assert(radio.callbacks == 1 && radio.resumes == 4);
    radio.length = 10;
    radio.irq = IRQ_HEADER_ERROR_MASK_6X;
    radio.poll();
    assert(radio.callbacks == 1 && radio.resumes == 5 && radio.irq == 0);
    radio.irq = IRQ_RX_DONE_MASK_6X;
    radio.poll();
    assert(radio.callbacks == 2 && radio.resumes == 6);

    radio._implicitHeaderMode = 1;
    radio._payloadLength = 23;
    radio.irq = IRQ_RX_DONE_MASK_6X;
    radio.poll();
    assert(radio.callbacks == 3 && radio.resumes == 7);
    assert(radio._implicitHeaderMode == 1 && radio._payloadLength == 23);
    assert(radio.last_receive_size == 23);
    radio.irq = IRQ_RX_DONE_MASK_6X;
    radio.poll();
    assert(radio.callbacks == 4 && radio.resumes == 8);
    assert(radio._implicitHeaderMode == 1 && radio._payloadLength == 23);
    assert(radio.last_receive_size == 23);
    radio.irq = IRQ_RX_DONE_MASK_6X;
    radio._dio0 = 10;
    radio.onReceive([](uint8_t, int) {});
    assert(attaches == 1);
    radio.poll();
    assert(radio.callbacks == 4 && radio.resumes == 8);
    radio._dio0 = -1;
    radio._radio_online = false;
    radio.poll();
    assert(radio.callbacks == 4 && radio.resumes == 8);
    radio.onReceive(nullptr);
    assert(detaches == 0);
    radio._radio_online = true;
    radio.poll();
    assert(radio.callbacks == 4);
    radio.setTxPower(22, 1);
    assert(radio._txp == 22 && radio.tx_drive == 22);
    radio.setTxPower(30, 1);
    assert(radio._txp == 22 && radio.tx_drive == 22);
    radio.enableTCXO();
    assert(radio.tcxo_voltage == 0x02);
}
"""
        self.compile_run(source)

    def test_uf2_matches_rak_nrf52840_application(self):
        hex_path = ROOT / "build/wisblock_1w/RNode_Firmware_CE.ino.hex"
        uf2_path = ROOT / "build/wisblock_1w/RNode_Firmware_CE.ino.uf2"
        self.assertTrue(hex_path.is_file(), "Build the WisBlock 1W target first")
        self.assertTrue(uf2_path.is_file(), "Generate UF2 with make uf2-wisblock_1w")

        image = {}
        upper = 0
        for line in hex_path.read_text().splitlines():
            record = bytes.fromhex(line[1:])
            self.assertEqual(sum(record) & 0xFF, 0, "Invalid Intel HEX checksum")
            count, address, kind = record[0], int.from_bytes(record[1:3], "big"), record[3]
            if kind == 4:
                upper = int.from_bytes(record[4:6], "big") << 16
            elif kind == 2:
                upper = int.from_bytes(record[4:6], "big") << 4
            elif kind == 0:
                start = upper + address
                for offset, value in enumerate(record[4:4 + count]):
                    image[start + offset] = value
            elif kind == 1:
                break

        raw = uf2_path.read_bytes()
        self.assertGreater(len(raw), 0)
        self.assertEqual(len(raw) % 512, 0)
        uf2 = {}
        total_blocks = len(raw) // 512
        for block_no in range(total_blocks):
            block = raw[block_no * 512:(block_no + 1) * 512]
            fields = struct.unpack("<IIIIIIII", block[:32])
            magic0, magic1, flags, address, size, number, total, family = fields
            self.assertEqual((magic0, magic1), (0x0A324655, 0x9E5D5157))
            self.assertEqual(struct.unpack("<I", block[508:])[0], 0x0AB16F30)
            self.assertEqual(flags, 0x2000)
            self.assertEqual(size, 256)
            self.assertEqual(number, block_no)
            self.assertEqual(total, total_blocks)
            self.assertEqual(family, 0xADA52840)
            self.assertGreaterEqual(address, 0x26000)
            self.assertLess(address + size, 0xED000)
            for offset, value in enumerate(block[32:32 + size]):
                target = address + offset
                if target in image:
                    self.assertEqual(value, image[target], f"HEX/UF2 mismatch at 0x{target:x}")
                uf2[target] = value

        self.assertTrue(image)
        self.assertLessEqual(set(image), set(uf2))


if __name__ == "__main__":
    unittest.main()
