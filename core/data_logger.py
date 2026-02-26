"""
Data Logger - Registra dati durante esecuzione programmi
"""

import time
import json
import os
from datetime import datetime
from config import LOGS_DIR, TEMP_LOG_INTERVAL, PID_CYCLE_INTERVAL


class DataLogger:
    """
    Logger per temperature, PID, eventi e dati esecuzione programma.
    
    Ogni campione include lo stato completo del sistema per consentire:
    - Analisi post-cottura e affinamento PID
    - Training modelli ML per predizione comportamento forno
    - Implementazione PID adattivo
    """
    
    def __init__(self):
        self.program_name = ""
        self.start_time = None
        self.temperatures = []  # Campioni completi
        self.events = []        # Eventi di fase
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
        
    def log_temperature(self, temp, setpoint, valve_position=0, cooling_rate=0,
                        pid_terms=None, valve_limited=False, pid_raw=0,
                        temp_cold=0, temp_rate=0):
        """
        Registra campione completo dello stato del sistema.
        
        Args:
            temp (float): Temperatura reale (°C)
            setpoint (float): Setpoint target calcolato dal runner (°C)
            valve_position (float): Posizione valvola dopo rate limiter 0-100%
            cooling_rate (float): Velocità raffreddamento (°C/h)
            pid_terms (dict): Termini PID {p, i, d, error, integral, kp, ki, kd}
            valve_limited (bool): True se il rate limiter ha agito
            pid_raw (float): Output PID prima del rate limiter
            temp_cold (float): Temperatura cold junction (°C)
            temp_rate (float): Derivata temperatura (°C/min)
        """
        if not self.is_logging:
            return
        
        elapsed = time.time() - self.start_time
        
        sample = {
            # Tempo
            'time': round(elapsed / 60, 2),         # minuti dall'avvio
            # Temperature
            'temp': round(temp, 1),                  # temperatura reale forno
            'temp_cold': round(temp_cold, 1),        # cold junction
            'temp_rate': round(temp_rate, 2),         # derivata °C/min
            'setpoint': round(setpoint, 1),           # setpoint dal runner
            'error': round(setpoint - temp, 1),       # errore (SP - T)
            # Valvola
            'valve': round(valve_position, 1),        # posizione dopo rate limiter
            'pid_raw': round(pid_raw, 1),             # output PID prima del limiter
            'valve_limited': valve_limited,            # True se limiter attivo
            # Raffreddamento
            'cooling_rate': round(cooling_rate, 1),
        }
        
        # Termini PID (se disponibili)
        if pid_terms:
            sample['pid_p'] = round(pid_terms.get('p', 0), 3)
            sample['pid_i'] = round(pid_terms.get('i', 0), 3)
            sample['pid_d'] = round(pid_terms.get('d', 0), 3)
            sample['pid_integral'] = round(pid_terms.get('integral', 0), 2)
            sample['pid_kp'] = pid_terms.get('kp', 0)
            sample['pid_ki'] = pid_terms.get('ki', 0)
            sample['pid_kd'] = pid_terms.get('kd', 0)
        
        self.temperatures.append(sample)
    
    def log_event(self, event_type, message):
        """
        Registra evento
        
        Args:
            event_type (str): Tipo evento (start, ramp_start, ramp_complete,
                              hold_start, hold_complete, program_complete, 
                              stop, emergency_stop, error)
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
        """Ferma logging e salva file (anche su stop manuale)"""
        if not self.is_logging:
            return None
        
        self.log_event('stop', 'Programma fermato')
        self.is_logging = False
        
        # Salva sempre — anche su stop manuale i dati sono preziosi per ML
        filepath = self._save_to_file()
        print(f"📝 Log salvato (stop): {filepath}")
        return filepath
    
    def complete_logging(self):
        """Completa logging e salva file"""
        if not self.is_logging:
            return None
        
        self.log_event('complete', 'Programma completato')
        self.is_logging = False
        
        filepath = self._save_to_file()
        print(f"✅ Log salvato (completato): {filepath}")
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
            'sample_interval_seconds': TEMP_LOG_INTERVAL,
            'pid_cycle_seconds': PID_CYCLE_INTERVAL,
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
        errors = [t.get('error', 0) for t in self.temperatures]
        valves = [t.get('valve', 0) for t in self.temperatures]
        limited_count = sum(1 for t in self.temperatures if t.get('valve_limited', False))
        
        return {
            'max_temp': round(max(temps), 1),
            'min_temp': round(min(temps), 1),
            'avg_temp': round(sum(temps) / len(temps), 1),
            'avg_error': round(sum(abs(e) for e in errors) / len(errors), 1) if errors else 0,
            'max_error': round(max(abs(e) for e in errors), 1) if errors else 0,
            'avg_valve': round(sum(valves) / len(valves), 1) if valves else 0,
            'rate_limited_pct': round(limited_count / len(self.temperatures) * 100, 1),
            'total_samples': len(self.temperatures),
            'total_events': len(self.events)
        }
    
    def get_current_log(self):
        """
        Ritorna log corrente (per API)
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
