"""
PID Autotuner - Metodo Relay Feedback con Ziegler-Nichols
Specifico per Forno Ceramica

Supporta autotuning a qualsiasi temperatura per:
- Test graduali del sistema (150, 350, 500, 700°C)
- Mappatura risposta termica del forno a diverse temperature
- Gain scheduling futuro (PID diversi per zone di temperatura)
"""

import time
import math
import json
import os
from datetime import datetime
from collections import deque
from config import LOGS_DIR, TEMP_LOG_INTERVAL


class RelayAutotuner:
    """
    Autotuning PID usando Relay Feedback (Åström-Hägglund)
    Più sicuro del metodo Z-N classico per forni ceramica.
    
    Integra DataLogger per log completi (ML-ready).
    Salva storico risultati per confronto tra temperature diverse.
    """
    
    HISTORY_FILE = os.path.join(LOGS_DIR, 'autotuning_history.json')
    
    def __init__(self, test_temperature=500):
        """
        Args:
            test_temperature: Temperatura test in °C (qualsiasi valore)
        """
        self.test_temperature = test_temperature
        self.setpoint = test_temperature
        
        # Parametri relay — adattati alla temperatura
        self.relay_high = 25   # Apertura valvola alta (%)
        self.relay_low = 0     # Apertura valvola bassa (%)
        self.hysteresis = 5    # Isteresi in °C
        
        # Stato test
        self.is_running = False
        self.phase = 'idle'  # idle, heating, relay, complete, error
        self.start_time = None
        
        # Raccolta dati
        self.temperature_log = []  # [{time, temp, valve, phase}]
        self.crossings = []        # [{time, direction, temp}]
        self.peaks = []            # [{time, type, temp}]
        
        # Risultati
        self.Ku = None  # Guadagno critico
        self.Pu = None  # Periodo critico
        self.amplitude = None  # Ampiezza oscillazione
        
        self.Kp = None  # PID calcolati
        self.Ki = None
        self.Kd = None
        
        # Parametri test
        self.min_oscillations = 3  # Oscillazioni minime da rilevare
        self.max_duration = 43200  # Timeout 12 ore
        
        # Stato interno relay
        self.relay_state = False
        self.last_direction = None
        self.current_peak_type = None
        self.temp_buffer = deque(maxlen=10)
        
        # DataLogger integration
        self.data_logger = None
        self._last_log_time = 0
        
    def set_data_logger(self, logger):
        """Collega il DataLogger per log completi durante autotuning"""
        self.data_logger = logger
        
    def start(self):
        """Avvia test autotuning"""
        # Adatta parametri relay alla temperatura
        self._adapt_relay_params()
        
        print("="*60)
        print(f"🎯 AVVIO PID AUTOTUNING - Test a {self.test_temperature}°C")
        print("="*60)
        print(f"Metodo: Relay Feedback (Åström-Hägglund)")
        print(f"Setpoint: {self.setpoint}°C")
        print(f"Relay: {self.relay_low}% ↔ {self.relay_high}%")
        print(f"Isteresi: ±{self.hysteresis}°C")
        print(f"Oscillazioni richieste: {self.min_oscillations}")
        print("="*60)
        
        self.is_running = True
        self.phase = 'heating'
        self.start_time = time.time()
        self._last_log_time = 0
        
        # Reset dati
        self.temperature_log = []
        self.crossings = []
        self.peaks = []
        self.temp_buffer.clear()
        self.Ku = None
        self.Pu = None
        self.amplitude = None
        self.Kp = None
        self.Ki = None
        self.Kd = None
        
        # Avvia DataLogger
        if self.data_logger:
            self.data_logger.start_logging(f'autotuning_{self.test_temperature}C')
            self.data_logger.log_event('autotuning_start',
                f'Autotuning a {self.test_temperature}°C - relay {self.relay_low}%↔{self.relay_high}%')
        
    def stop(self):
        """Ferma test"""
        self.is_running = False
        self.phase = 'idle'
        
        # Ferma DataLogger (salva il log)
        if self.data_logger:
            self.data_logger.log_event('autotuning_stop', 'Test fermato manualmente')
            self.data_logger.stop_logging()
        
        print("⏹️ Autotuning fermato")
    
    def _adapt_relay_params(self):
        """
        Adatta parametri relay alla temperatura di test.
        A temperature basse il forno risponde più veloce → relay meno aggressivo.
        A temperature alte la dispersione aumenta → serve più potenza.
        """
        temp = self.test_temperature
        
        if temp <= 200:
            self.relay_high = 15
            self.hysteresis = 3
        elif temp <= 400:
            self.relay_high = 20
            self.hysteresis = 4
        elif temp <= 600:
            self.relay_high = 25
            self.hysteresis = 5
        else:
            self.relay_high = 30
            self.hysteresis = 6
        
        self.relay_low = 0
        self.setpoint = temp
        
    def compute_valve_position(self, current_temp):
        """
        Calcola output valvola usando relay feedback
        
        Args:
            current_temp: Temperatura attuale
            
        Returns:
            float: Posizione valvola 0-100% o None
        """
        if not self.is_running:
            return None
        
        elapsed = time.time() - self.start_time
        
        # Log temperatura (interno autotuner)
        self.temperature_log.append({
            'time': elapsed,
            'temp': round(current_temp, 1),
            'valve': None,
            'phase': self.phase
        })
        
        # Aggiungi a buffer per rilevamento picchi
        self.temp_buffer.append(current_temp)
        
        # Timeout sicurezza
        if elapsed > self.max_duration:
            self.phase = 'error'
            self.is_running = False
            if self.data_logger:
                self.data_logger.log_event('autotuning_error',
                    f'Timeout {self.max_duration/60:.0f}min')
                self.data_logger.stop_logging()
            print(f"⚠️ Timeout {self.max_duration/60:.0f}min - Test interrotto")
            return 0
        
        # FASE 1: Riscaldamento iniziale
        if self.phase == 'heating':
            temp_diff = self.setpoint - current_temp
            
            # Vicino al setpoint? Passa a relay
            if temp_diff < 20:
                print(f"\n✅ Temperatura raggiunta: {current_temp:.1f}°C")
                print("🔄 Attivo controllo relay feedback...")
                self.phase = 'relay'
                self.relay_state = False
                if self.data_logger:
                    self.data_logger.log_event('relay_start',
                        f'Fase relay avviata a {current_temp:.1f}°C')
            
            # Rampa conservativa
            if temp_diff > 400:
                valve_pos = 35
            elif temp_diff > 300:
                valve_pos = 30
            elif temp_diff > 200:
                valve_pos = 25
            elif temp_diff > 100:
                valve_pos = 20
            elif temp_diff > 50:
                valve_pos = 15
            elif temp_diff > 20:
                valve_pos = 10
            else:
                valve_pos = 5
            
            # Log rate ogni minuto circa
            if len(self.temperature_log) >= 2 and len(self.temperature_log) % 30 == 0:
                last_temps = self.temperature_log[-30:]
                if len(last_temps) >= 2:
                    dt = last_temps[-1]['time'] - last_temps[0]['time']
                    dT = last_temps[-1]['temp'] - last_temps[0]['temp']
                    if dt > 0:
                        rate = (dT / dt) * 3600
                        print(f"  📊 Riscaldamento: {current_temp:.1f}°C | Rate: {rate:.1f}°C/h | Valvola: {valve_pos}%")
            
            if self.temperature_log:
                self.temperature_log[-1]['valve'] = valve_pos
            
            # Log al DataLogger
            self._log_to_datalogger(current_temp, valve_pos)
            
            return valve_pos
        
        # FASE 2: Controllo Relay Feedback
        if self.phase == 'relay':
            if current_temp < self.setpoint - self.hysteresis:
                valve_pos = self.relay_high
                self.relay_state = True
            elif current_temp > self.setpoint + self.hysteresis:
                valve_pos = self.relay_low
                self.relay_state = False
            else:
                valve_pos = self.relay_high if self.relay_state else self.relay_low
            
            if self.temperature_log:
                self.temperature_log[-1]['valve'] = valve_pos
            
            # Rileva crossing e picchi
            self._detect_crossing(current_temp, elapsed)
            self._detect_peaks(current_temp, elapsed)
            
            # Log al DataLogger
            self._log_to_datalogger(current_temp, valve_pos)
            
            # Verifica completamento
            if self._is_complete():
                self.phase = 'complete'
                self._calculate_pid()
                return 0
            
            return valve_pos
        
        # FASE 3: Test completato
        if self.phase == 'complete':
            return 0
        
        # FASE 4: Errore
        if self.phase == 'error':
            return 0
        
        return None
    
    def _log_to_datalogger(self, current_temp, valve_pos):
        """Logga al DataLogger con tutti i campi (ogni TEMP_LOG_INTERVAL)"""
        if not self.data_logger or not self.data_logger.is_logging:
            return
        
        now = time.time()
        if now - self._last_log_time < TEMP_LOG_INTERVAL:
            return
        
        # Calcola derivata temperatura
        temp_rate = 0.0
        if len(self.temp_buffer) >= 2:
            dt_s = 2.0  # SENSOR_UPDATE_INTERVAL
            temp_rate = (self.temp_buffer[-1] - self.temp_buffer[-2]) / (dt_s / 60.0)
        
        self.data_logger.log_temperature(
            temp=current_temp,
            setpoint=self.setpoint,
            valve_position=valve_pos,
            cooling_rate=0,
            pid_terms=None,  # Autotuning non usa PID
            valve_limited=False,
            pid_raw=valve_pos,  # Relay = diretto
            temp_cold=0,
            temp_rate=temp_rate
        )
        self._last_log_time = now
    
    def _detect_crossing(self, temp, elapsed):
        """Rileva attraversamento del setpoint"""
        if len(self.temp_buffer) < 2:
            return
        
        prev_temp = self.temp_buffer[-2]
        
        if prev_temp < self.setpoint <= temp:
            if self.last_direction != 'up':
                self.crossings.append({
                    'time': elapsed,
                    'direction': 'up',
                    'temp': temp
                })
                print(f"  ↗️ Crossing UP @ {elapsed:.1f}s, T={temp:.1f}°C")
                self.last_direction = 'up'
                if self.data_logger:
                    self.data_logger.log_event('crossing_up',
                        f'Crossing UP a {temp:.1f}°C ({elapsed:.0f}s)')
        
        elif prev_temp > self.setpoint >= temp:
            if self.last_direction != 'down':
                self.crossings.append({
                    'time': elapsed,
                    'direction': 'down',
                    'temp': temp
                })
                print(f"  ↘️ Crossing DOWN @ {elapsed:.1f}s, T={temp:.1f}°C")
                self.last_direction = 'down'
                if self.data_logger:
                    self.data_logger.log_event('crossing_down',
                        f'Crossing DOWN a {temp:.1f}°C ({elapsed:.0f}s)')
    
    def _detect_peaks(self, temp, elapsed):
        """Rileva picchi massimi e minimi"""
        if len(self.temp_buffer) < 3:
            return
        
        temps = list(self.temp_buffer)
        
        if temps[-3] < temps[-2] > temps[-1]:
            self.peaks.append({
                'time': elapsed,
                'type': 'max',
                'temp': temps[-2]
            })
            print(f"  🔺 Picco MAX: {temps[-2]:.1f}°C")
        
        elif temps[-3] > temps[-2] < temps[-1]:
            self.peaks.append({
                'time': elapsed,
                'type': 'min',
                'temp': temps[-2]
            })
            print(f"  🔻 Picco MIN: {temps[-2]:.1f}°C")
    
    def _is_complete(self):
        """Verifica se raccolti dati sufficienti"""
        num_cycles = len(self.crossings) // 2
        
        if num_cycles >= self.min_oscillations:
            print(f"\n✅ Raccolte {num_cycles} oscillazioni complete")
            return True
        
        return False
    
    def _calculate_pid(self):
        """Calcola parametri PID con metodo Ziegler-Nichols"""
        print("\n" + "="*60)
        print("📊 CALCOLO PARAMETRI PID")
        print("="*60)
        
        if len(self.crossings) < self.min_oscillations * 2:
            print("❌ Dati insufficienti")
            self.phase = 'error'
            return
        
        # 1. PERIODO CRITICO (Pu)
        periods = []
        for i in range(2, len(self.crossings), 2):
            period = self.crossings[i]['time'] - self.crossings[i-2]['time']
            periods.append(period)
            print(f"Periodo {len(periods)}: {period:.1f}s")
        
        self.Pu = sum(periods) / len(periods)
        print(f"\n⏱️ Periodo critico Pu = {self.Pu:.1f}s ({self.Pu/60:.2f} min)")
        
        # 2. AMPIEZZA OSCILLAZIONE
        if len(self.peaks) < 4:
            print("❌ Picchi insufficienti")
            self.phase = 'error'
            return
        
        max_peaks = [p['temp'] for p in self.peaks if p['type'] == 'max'][-3:]
        min_peaks = [p['temp'] for p in self.peaks if p['type'] == 'min'][-3:]
        
        avg_max = sum(max_peaks) / len(max_peaks)
        avg_min = sum(min_peaks) / len(min_peaks)
        
        self.amplitude = (avg_max - avg_min) / 2
        print(f"📏 Ampiezza oscillazione a = {self.amplitude:.1f}°C")
        print(f"   (Max: {avg_max:.1f}°C, Min: {avg_min:.1f}°C)")
        
        # 3. GUADAGNO CRITICO (Ku)
        d = self.relay_high - self.relay_low
        self.Ku = (4 * d) / (math.pi * self.amplitude)
        print(f"\n💪 Guadagno critico Ku = {self.Ku:.3f}")
        print(f"   (relay amplitude d = {d}%)")
        
        # 4. PARAMETRI PID con formule Ziegler-Nichols
        print("\n🎯 PARAMETRI PID CALCOLATI (Ziegler-Nichols):")
        
        self.Kp = 0.6 * self.Ku
        self.Ki = 1.2 * self.Ku / self.Pu
        self.Kd = 0.075 * self.Ku * self.Pu
        
        print(f"   Kp = {self.Kp:.4f}")
        print(f"   Ki = {self.Ki:.6f}")
        print(f"   Kd = {self.Kd:.2f}")
        
        kp_cons = 0.45 * self.Ku
        ki_cons = 0.54 * self.Ku / self.Pu
        
        print(f"\n💡 PARAMETRI CONSERVATIVI (consigliati):")
        print(f"   Kp = {kp_cons:.4f}")
        print(f"   Ki = {ki_cons:.6f}")
        print(f"   Kd = 0")
        
        print("="*60)
        
        # Salva risultati e log DataLogger
        self._save_results()
        
        if self.data_logger:
            self.data_logger.log_event('autotuning_complete',
                f'Ku={self.Ku:.3f} Pu={self.Pu:.1f}s Amp={self.amplitude:.1f}°C '
                f'→ Kp={kp_cons:.4f} Ki={ki_cons:.6f}')
            self.data_logger.complete_logging()
    
    def _save_results(self):
        """Salva risultati test su file JSON e aggiorna storico"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"autotuning_{self.test_temperature}C_{timestamp}.json"
        filepath = os.path.join(LOGS_DIR, filename)
        
        kp_cons = 0.45 * self.Ku
        ki_cons = 0.54 * self.Ku / self.Pu
        
        results = {
            'test_info': {
                'date': datetime.now().isoformat(),
                'temperature': self.test_temperature,
                'duration_minutes': round((time.time() - self.start_time) / 60, 1),
                'relay_high': self.relay_high,
                'relay_low': self.relay_low,
                'hysteresis': self.hysteresis,
                'oscillations': len(self.crossings) // 2
            },
            'measurements': {
                'Ku': round(self.Ku, 4),
                'Pu': round(self.Pu, 2),
                'Pu_minutes': round(self.Pu / 60, 2),
                'amplitude': round(self.amplitude, 2)
            },
            'pid_standard': {
                'Kp': round(self.Kp, 4),
                'Ki': round(self.Ki, 6),
                'Kd': round(self.Kd, 2)
            },
            'pid_conservative': {
                'Kp': round(kp_cons, 4),
                'Ki': round(ki_cons, 6),
                'Kd': 0
            },
            'raw_data': {
                'crossings': self.crossings[-10:],
                'peaks': self.peaks[-10:],
                'temperature_samples': len(self.temperature_log)
            }
        }
        
        os.makedirs(LOGS_DIR, exist_ok=True)
        with open(filepath, 'w') as f:
            json.dump(results, f, indent=2)
        
        print(f"\n💾 Risultati salvati: {filepath}")
        
        # Aggiorna storico
        self._update_history(results)
        
        return filepath
    
    def _update_history(self, results):
        """Aggiorna file storico autotuning per confronto tra temperature"""
        history = []
        
        # Carica storico esistente
        if os.path.exists(self.HISTORY_FILE):
            try:
                with open(self.HISTORY_FILE, 'r') as f:
                    history = json.load(f)
            except (json.JSONDecodeError, IOError):
                history = []
        
        # Aggiungi nuovo risultato
        history.append({
            'date': results['test_info']['date'],
            'temperature': results['test_info']['temperature'],
            'duration_min': results['test_info']['duration_minutes'],
            'Ku': results['measurements']['Ku'],
            'Pu': results['measurements']['Pu'],
            'Pu_min': results['measurements']['Pu_minutes'],
            'amplitude': results['measurements']['amplitude'],
            'pid_kp': results['pid_conservative']['Kp'],
            'pid_ki': results['pid_conservative']['Ki'],
            'relay_high': results['test_info']['relay_high'],
            'hysteresis': results['test_info']['hysteresis']
        })
        
        # Salva
        with open(self.HISTORY_FILE, 'w') as f:
            json.dump(history, f, indent=2)
        
        print(f"📋 Storico aggiornato: {len(history)} test totali")
    
    def get_status(self):
        """Ritorna stato corrente per API"""
        oscillations = len(self.crossings) // 2
        progress = min(100, (oscillations / self.min_oscillations) * 100)
        
        return {
            'running': self.is_running,
            'phase': self.phase,
            'test_temperature': self.test_temperature,
            'oscillations': oscillations,
            'required_oscillations': self.min_oscillations,
            'progress': round(progress, 1),
            'duration': (time.time() - self.start_time) if self.start_time else 0,
            'relay_state': self.relay_state,
            'relay_high': self.relay_high,
            'relay_low': self.relay_low,
            'hysteresis': self.hysteresis,
            'data_points': len(self.temperature_log)
        }
    
    def get_results(self):
        """Ritorna risultati finali"""
        if self.phase != 'complete':
            return None
        
        return {
            'Ku': self.Ku,
            'Pu': self.Pu,
            'Pu_minutes': self.Pu / 60,
            'amplitude': self.amplitude,
            'Kp': self.Kp,
            'Ki': self.Ki,
            'Kd': self.Kd,
            'Kp_conservative': 0.45 * self.Ku,
            'Ki_conservative': 0.54 * self.Ku / self.Pu,
            'Kd_conservative': 0,
            'test_temperature': self.test_temperature
        }
    
    def get_chart_data(self):
        """Ritorna dati per grafico real-time"""
        return {
            'temperatures': self.temperature_log[-100:],
            'crossings': self.crossings,
            'peaks': self.peaks,
            'setpoint': self.setpoint,
            'relay_high': self.relay_high,
            'relay_low': self.relay_low
        }
    
    def get_history(self):
        """Ritorna storico test per confronto"""
        if os.path.exists(self.HISTORY_FILE):
            try:
                with open(self.HISTORY_FILE, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return []
        return []
