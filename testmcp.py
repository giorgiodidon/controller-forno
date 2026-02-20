#!/usr/bin/env python3

import smbus2
import time

bus = smbus2.SMBus(1)
addr = 0x60

print("Test MCP9600 all'indirizzo 0x60")

try:
    while True:
        data = bus.read_i2c_block_data(addr, 0x00, 2)
        temp_raw = (data[0] << 8) | data[1]
        
        if temp_raw & 0x8000:
            temp_raw = temp_raw - 0x10000
        
        temp = temp_raw * 0.0625
        print(f"Temperatura: {temp:.2f} C")
        
        time.sleep(1)
        
except KeyboardInterrupt:
    print("Finito")
