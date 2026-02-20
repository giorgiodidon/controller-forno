#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test lettura temperatura con tipo S
"""

import smbus2
import time
import struct

bus = smbus2.SMBus(1)
MCP9600_ADDRESS = 0x60

# Verifica tipo
tc_type = bus.read_byte_data(MCP9600_ADDRESS, 0x06)
print(f"Tipo termocoppia: 0x{tc_type:02X}")

if tc_type != 0x05:
    print("[WARNING] Tipo non e' S (0x05)!")
    print("          Le letture potrebbero essere errate.")
    print("")

print("Lettura temperature (CTRL+C per fermare)...")
print("")

try:
    while True:
        # Leggi temperatura hot junction (0x00)
        data = bus.read_i2c_block_data(MCP9600_ADDRESS, 0x00, 2)
        raw = struct.unpack('>h', bytes(data))[0]
        temp_hot = raw * 0.0625  # Risoluzione 0.0625 gradi C
        
        # Leggi temperatura cold junction (0x02)
        data = bus.read_i2c_block_data(MCP9600_ADDRESS, 0x02, 2)
        raw = struct.unpack('>h', bytes(data))[0]
        temp_cold = raw * 0.0625
        
        # Delta
        delta = temp_hot - temp_cold
        
        print(f"Hot: {temp_hot:7.2f}C  |  Cold: {temp_cold:6.2f}C  |  Delta: {delta:7.2f}C")
        
        time.sleep(1)
        
except KeyboardInterrupt:
    print("\nTest terminato")
    bus.close()
