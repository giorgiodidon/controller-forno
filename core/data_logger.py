"""
Data Logger - Registra dati durante esecuzione programmi
"""

import time
import json
import os
from datetime import datetime
from config import LOGS_DIR


class DataLogger:
    """
    Logger per temperature, eventi e dati esecuzione programma
    """
    
    def __init__(self):
        self.program_name = ""
        self.start_time = None
        self.temperatures = []  # Lista [{time, temp, setpoint, valve_position, cooling_rate}]
        self.events = []        # Lista [{time, type, message}]
        self.is_logging = False
        
        # Crea directory logs se non esiste
        os.makedirs(LOGS_DIR, exist_ok=True)
        
    def start_logging(self, program_name):
        """
        Inizia nuovo log esecuzione
        
        Args:
            program_name (str): Nome programma in esecuzione
        """
        self.program_name = program_name
        self.start_time = time.time()
        self.temperatures = []
        self.events = []
        self.is_logging = True
        
        self.log_event('start', f'Programma "{program_name}" avviato')
        print(f"📝 Logging avviato: {program_name}")
        
    def log_temperature(self, temp, setpoint, valve_position=0, cooling_rate=0):
        """
        Registra dati temperatura
        
        Args:
            temp (float): Temperatura attuale (°C)
            setpoint (float): Setpoint target (°C)
            valve_position (float): Posizione valvola 0-100%
            cooling_rate (float): Velocità raffreddamento (°C/h)
        """
        if not self.is_logging:
            return
        
        elapsed = time.time() - self.start_time
        
        self.temperatures.append({
            'time': round(elapsed / 60, 2),  # Minuti
            'temp': round(temp, 1),
            'setpoint': round(setpoint, 1),
            'valve_position': round(valve_position, 1),
            'cooling_rate': round(cooling_rate, 1)
        })
    
    def log_event(self, event_type, message):
        """
        Registra evento
        
        Args:
            event_type (str): Tipo evento (start, ramp_complete, hold_start, etc)
            message (str): Descrizione evento
        """
        if not self.is_logging and event_type != 'start':
            return
        
        elapsed = time.time() - self.start_time if self.start_time else 0
        
        self.events.append({
            'time': round(elapsed / 60, 2),
            'type': event_type,
            'message': message,
            'timestamp': datetime.now().isoformat()
        })
        
        print(f"📌 [{event_type}] {message}")
    
    def stop_logging(self):
        """Ferma logging"""
        if not self.is_logging:
            return
        
        self.log_event('stop', 'Programma fermato')
        self.is_logging = False
        print("⏸️ Logging fermato")
    
    def complete_logging(self):
        """Completa logging e salva file"""
        if not self.is_logging:
            return None
        
        self.log_event('complete', 'Programma completato')
        self.is_logging = False
        
        # Salva su file
        filepath = self._save_to_file()
        
        print(f"✅ Logging completato: {filepath}")
        return filepath
    
    def _save_to_file(self):
        """
        Salva log su file JSON
        
        Returns:
            str: Path del file salvato
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"execution_{self.program_name}_{timestamp}.json"
        filepath = os.path.join(LOGS_DIR, filename)
        
        data = {
            'program_name': self.program_name,
            'start_time': datetime.fromtimestamp(self.start_time).isoformat(),
            'duration_minutes': round((time.time() - self.start_time) / 60, 1),
            'temperatures': self.temperatures,
            'events': self.events,
            'statistics': self._calculate_statistics()
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        return filepath
    
    def _calculate_statistics(self):
        """Calcola statistiche esecuzione"""
        if not self.temperatures:
            return {}
        
        temps = [t['temp'] for t in self.temperatures]
        
        return {
            'max_temp': round(max(temps), 1),
            'min_temp': round(min(temps), 1),
            'avg_temp': round(sum(temps) / len(temps), 1),
            'total_samples': len(self.temperatures),
            'total_events': len(self.events)
        }
    
    def get_current_log(self):
        """
        Ritorna log corrente (per API)
        
        Returns:
            dict: Dati log corrente
        """
        return {
            'program_name': self.program_name,
            'is_logging': self.is_logging,
            'start_time': self.start_time,
            'elapsed_minutes': round((time.time() - self.start_time) / 60, 1) if self.start_time else 0,
            'temperatures': self.temperatures,
            'events': self.events,
            'samples_count': len(self.temperatures),
            'events_count': len(self.events)
        }
    
    def reset(self):
        """Reset logger"""
        self.program_name = ""
        self.start_time = None
        self.temperatures = []
        self.events = []
        self.is_logging = False
        print("🔄 Logger reset")
