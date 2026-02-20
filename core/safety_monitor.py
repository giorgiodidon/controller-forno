"""
Monitor Sicurezza - Controlli critici per prevenire danni
"""

import time
from collections import deque
from config import (
    MAX_TEMP, OVER_TEMP,
    MAX_RATE_UP, MAX_RATE_DOWN,
    COOLING_RATE_WARNING
)


class SafetyMonitor:
    """
    Monitora continuamente parametri critici e genera allarmi
    """
    
    def __init__(self):
        self.alarms = []
        self.temp_history = deque(maxlen=100)  # Ultimi 100 campioni
        self.last_check_time = time.time()
        
        # Stato
        self.is_safe = True
        self.emergency_stop_triggered = False
        
    def check_all(self, temp_hot, temp_cold, cooling_rate=0):
        """
        Esegue tutti i controlli di sicurezza
        
        Args:
            temp_hot (float): Temperatura termocoppia (°C)
            temp_cold (float): Temperatura ambiente (°C)
            cooling_rate (float): Velocità raffreddamento (°C/h, negativa)
        
        Returns:
            dict: Risultato controlli {is_safe, alarms, actions}
        """
        self.alarms = []
        actions = []
        
        # Aggiungi a storico
        self.temp_history.append({
            'temp': temp_hot,
            'time': time.time()
        })
        
        # ===== CONTROLLO 1: Sovratemperatura Critica =====
        if temp_hot > OVER_TEMP:
            self.alarms.append({
                'level': 'CRITICAL',
                'code': 'OVER_TEMP',
                'message': f'SOVRATEMPERATURA CRITICA: {temp_hot}°C',
                'value': temp_hot,
                'limit': OVER_TEMP
            })
            actions.append('emergency_shutdown')
            self.emergency_stop_triggered = True
        
        # ===== CONTROLLO 2: Temperatura Massima Lavoro =====
        elif temp_hot > MAX_TEMP:
            self.alarms.append({
                'level': 'WARNING',
                'code': 'MAX_TEMP',
                'message': f'Temperatura vicina al limite: {temp_hot}°C',
                'value': temp_hot,
                'limit': MAX_TEMP
            })
            actions.append('reduce_power')
        
        # ===== CONTROLLO 3: Raffreddamento Rapido =====
        if temp_hot < 700 and abs(cooling_rate) > COOLING_RATE_WARNING:
            self.alarms.append({
                'level': 'WARNING',
                'code': 'FAST_COOLING',
                'message': f'Raffreddamento troppo rapido: {cooling_rate:.1f}°C/h',
                'value': abs(cooling_rate),
                'limit': COOLING_RATE_WARNING
            })
            actions.append('notify_user')
        
        # ===== CONTROLLO 4: Rate Riscaldamento =====
        if len(self.temp_history) >= 2:
            rate_up = self._calculate_heating_rate()
            if rate_up > MAX_RATE_UP:
                self.alarms.append({
                    'level': 'WARNING',
                    'code': 'FAST_HEATING',
                    'message': f'Riscaldamento troppo veloce: {rate_up:.1f}°C/h',
                    'value': rate_up,
                    'limit': MAX_RATE_UP
                })
                actions.append('reduce_power')
        
        # Aggiorna stato
        self.is_safe = len([a for a in self.alarms if a['level'] == 'CRITICAL']) == 0
        self.last_check_time = time.time()
        
        return {
            'is_safe': self.is_safe,
            'alarms': self.alarms,
            'actions': actions,
            'emergency_stop': self.emergency_stop_triggered
        }
    
    def _calculate_heating_rate(self):
        """
        Calcola velocità riscaldamento dagli ultimi campioni
        
        Returns:
            float: °C/h
        """
        if len(self.temp_history) < 2:
            return 0.0
        
        # Prendi primi e ultimi 10 campioni
        recent = list(self.temp_history)[-10:]
        old = list(self.temp_history)[:10]
        
        if len(recent) < 2 or len(old) < 2:
            return 0.0
        
        # Media temperature
        temp_recent = sum(t['temp'] for t in recent) / len(recent)
        temp_old = sum(t['temp'] for t in old) / len(old)
        
        # Delta tempo
        dt = recent[-1]['time'] - old[0]['time']
        
        if dt <= 0:
            return 0.0
        
        # Rate in °C/h
        delta_temp = temp_recent - temp_old
        rate = (delta_temp / dt) * 3600
        
        return max(0, rate)  # Solo riscaldamento
    
    def check_sensor_health(self, sensor_status):
        """
        Verifica salute sensore
        
        Args:
            sensor_status (str): 'connected' o 'error'
        
        Returns:
            bool: True se sensore ok
        """
        if sensor_status != 'connected':
            self.alarms.append({
                'level': 'CRITICAL',
                'code': 'SENSOR_ERROR',
                'message': 'Sensore MCP9600 disconnesso o malfunzionante',
                'value': sensor_status,
                'limit': 'connected'
            })
            self.is_safe = False
            self.emergency_stop_triggered = True
            return False
        
        return True
    
    def reset_emergency(self):
        """Reset flag emergenza (solo dopo intervento manuale)"""
        self.emergency_stop_triggered = False
        self.alarms = []
        print("✅ Reset emergenza - Sistema pronto")
    
    def get_status(self):
        """Stato completo safety monitor"""
        return {
            'is_safe': self.is_safe,
            'emergency_stop': self.emergency_stop_triggered,
            'alarms': self.alarms,
            'last_check': self.last_check_time,
            'temp_samples': len(self.temp_history)
        }
    
    def get_alarms_summary(self):
        """Summary allarmi per display"""
        if not self.alarms:
            return "✅ Nessun allarme"
        
        critical = [a for a in self.alarms if a['level'] == 'CRITICAL']
        warnings = [a for a in self.alarms if a['level'] == 'WARNING']
        
        summary = []
        if critical:
            summary.append(f"🚨 {len(critical)} CRITICI")
        if warnings:
            summary.append(f"⚠️ {len(warnings)} WARNING")
        
        return " • ".join(summary)
