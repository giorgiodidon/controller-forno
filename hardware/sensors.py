"""
Gestione Sensori di Temperatura
"""

import smbus2
import time
from config import I2C_BUS, MCP9600_ADDR


class MCP9600Sensor:
    """Sensore termocoppia MCP9600 su I2C"""
    
    def __init__(self, bus=I2C_BUS, address=MCP9600_ADDR):
        self.bus_num = bus
        self.address = address
        self.last_reading = None
        self.is_connected = False
        
    def read(self):
        """
        Legge temperature dal sensore MCP9600
        
        Returns:
            tuple: (hot_temp, cold_temp, delta_temp) oppure (None, None, None) se errore
        """
        try:
            bus = smbus2.SMBus(self.bus_num)
            
            # Hot junction (termocoppia) - Register 0x00
            data = bus.read_i2c_block_data(self.address, 0x00, 2)
            hot_raw = (data[0] << 8) | data[1]
            if hot_raw & 0x8000:  # Negativo
                hot_raw = hot_raw - 0x10000
            hot_temp = round(hot_raw * 0.0625, 1)
            
            # Cold junction (ambiente) - Register 0x02
            data = bus.read_i2c_block_data(self.address, 0x02, 2)
            cold_raw = (data[0] << 8) | data[1]
            if cold_raw & 0x8000:  # Negativo
                cold_raw = cold_raw - 0x10000
            cold_temp = round(cold_raw * 0.0625, 1)
            
            bus.close()
            
            delta_temp = round(hot_temp - cold_temp, 1)
            
            # Aggiorna cache
            self.last_reading = {
                'hot': hot_temp,
                'cold': cold_temp,
                'delta': delta_temp,
                'timestamp': time.time()
            }
            
            self.is_connected = True
            return hot_temp, cold_temp, delta_temp
            
        except Exception as e:
            print(f"❌ Errore lettura MCP9600: {e}")
            self.is_connected = False
            return None, None, None
    
    def get_hot_temp(self):
        """Shortcut: ritorna solo temperatura termocoppia"""
        result = self.read()
        return result[0] if result[0] is not None else 0.0
    
    def get_cold_temp(self):
        """Shortcut: ritorna solo temperatura ambiente"""
        result = self.read()
        return result[1] if result[1] is not None else 0.0
    
    def get_status(self):
        """Ritorna stato sensore per diagnostica"""
        return {
            'connected': self.is_connected,
            'address': f'0x{self.address:02x}',
            'bus': self.bus_num,
            'last_reading': self.last_reading
        }


class SensorManager:
    """
    Manager centrale per tutti i sensori
    Facilita aggiunta futuri sensori (pressione, flusso, ecc)
    """
    
    def __init__(self):
        self.mcp9600 = MCP9600Sensor()
        
        # Placeholder per futuri sensori
        # self.pressure_sensor = PressureSensor()
        # self.oxygen_sensor = OxygenSensor()
        
    def read_all(self):
        """
        Legge tutti i sensori disponibili
        
        Returns:
            dict: Dati completi da tutti i sensori
        """
        hot, cold, delta = self.mcp9600.read()
        
        return {
            'temperature': {
                'hot': hot,
                'cold': cold,
                'delta': delta,
                'status': 'connected' if hot is not None else 'error',
                'timestamp': time.time()
            }
            # Espandibile con altri sensori:
            # 'pressure': self.pressure_sensor.read(),
            # 'oxygen': self.oxygen_sensor.read(),
        }
    
    def get_temperature_data(self):
        """Shortcut: solo dati temperatura"""
        data = self.read_all()
        return data['temperature']
    
    def is_healthy(self):
        """Check salute sensori"""
        return self.mcp9600.is_connected
    
    def get_diagnostics(self):
        """Diagnostica completa sensori"""
        return {
            'mcp9600': self.mcp9600.get_status()
        }
