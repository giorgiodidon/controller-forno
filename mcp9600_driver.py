
import smbus2

class MCP9600:
    def __init__(self, bus=1, address=0x60):
        self.bus = smbus2.SMBus(bus)
        self.address = address

    def _read_reg(self, reg):
        data = self.bus.read_i2c_block_data(self.address, reg, 2)
        value = (data[0] << 8) | data[1]
        if value & 0x8000:
            value -= 0x10000
        return value * 0.0625

    def read_hot_junction(self):
        return self._read_reg(0x00)

    def read_delta(self):
        return self._read_reg(0x01)

    def read_cold_junction(self):
        return self._read_reg(0x02)
