"""
PID Autotuner - Metodo Relay Feedback con Ziegler-Nichols
Specifico per Forno Ceramica
"""

import time
import math
import json
import os
from datetime import datetime
from collections import deque
from config import LOGS_DIR


class RelayAutotuner:
    """
    Autotuning PID usando Relay Feedback (Åström-Hägglund)
    Più sicuro del metodo Z-N classico per forni ceramica
    """
    
    def __init__(self, test_temperature=500):
        """
        Args:
            test_temperature: Temperatura test in °C (default 500°C)
        """
        self.test_temperature = test_temperature
        self.setpoint = test_temperature
        
        # Parametri relay
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
        self.max_duration = 43200  # Timeout 12 ore (per riscaldamento ultra-lento)
        
        # Stato interno relay
        self.relay_state = False
        self.last_direction = None
        self.current_peak_type = None
        self.temp_buffer = deque(maxlen=10)  # Buffer per rilevamento picchi
        
    def start(self):
        """Avvia test autotuning"""
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
        
        # Reset dati
        self.temperature_log = []
        self.crossings = []
        self.peaks = []
        self.temp_buffer.clear()
        
    def stop(self):
        """Ferma test"""
        self.is_running = False
        self.phase = 'idle'
        print("⏹️ Autotuning fermato")
        
    def compute_valve_position(self, current_temp):
        """
        Calcola output valvola usando relay feedback
        
        Durante heating: ritorna posizione calcolata (rampa lenta)
        Durante relay: ritorna posizione relay
        
        Args:
            current_temp: Temperatura attuale
            
        Returns:
            float: Posizione valvola 0-100% o None
        """
        if not self.is_running:
            return None
        
        elapsed = time.time() - self.start_time
        
        # Log temperatura
        self.temperature_log.append({
            'time': elapsed,
            'temp': round(current_temp, 1),
            'valve': None,  # Verrà aggiornato dopo
            'phase': self.phase
        })
        
        # Aggiungi a buffer per rilevamento picchi
        self.temp_buffer.append(current_temp)
        
        # Timeout sicurezza
        if elapsed > self.max_duration:
            self.phase = 'error'
            self.is_running = False
            print(f"⚠️ Timeout {self.max_duration/60:.0f}min - Test interrotto")
            return 0  # Chiudi valvola
        
        # FASE 1: Riscaldamento iniziale ULTRA-LENTO
        if self.phase == 'heating':
            temp_diff = self.setpoint - current_temp
            
            # Vicino al setpoint? Passa a relay
            if temp_diff < 20:
                print(f"\n✅ Temperatura raggiunta: {current_temp:.1f}°C")
                print("🔄 Attivo controllo relay feedback...")
                self.phase = 'relay'
                self.relay_state = False
            
            # RAMPA ULTRA-CONSERVATIVA
            # Obiettivo: ~50-80°C/h (molto lento, sicuro per forno)
            if temp_diff > 400:
                valve_pos = 35  # >400°C distanza: 35% (era 70%)
            elif temp_diff > 300:
                valve_pos = 30  # 300-400°C: 30% (era 60%)
            elif temp_diff > 200:
                valve_pos = 25  # 200-300°C: 25% (era 45%)
            elif temp_diff > 100:
                valve_pos = 20  # 100-200°C: 20% (era 30%)
            elif temp_diff > 50:
                valve_pos = 15  # 50-100°C: 15% (molto dolce)
            elif temp_diff > 20:
                valve_pos = 10  # 20-50°C: 10% (quasi chiuso)
            else:
                valve_pos = 5   # <20°C: 5% (apertura minima)
            
            # Log velocità stimata
            if len(self.temperature_log) >= 2:
                # Calcola rate attuale ogni minuto
                if len(self.temperature_log) % 30 == 0:  # Ogni 30 campioni (~1min)
                    last_temps = self.temperature_log[-30:]
                    if len(last_temps) >= 2:
                        dt = last_temps[-1]['time'] - last_temps[0]['time']
                        dT = last_temps[-1]['temp'] - last_temps[0]['temp']
                        if dt > 0:
                            rate = (dT / dt) * 3600  # °C/h
                            print(f"  📊 Riscaldamento: {current_temp:.1f}°C | Rate: {rate:.1f}°C/h | Valvola: {valve_pos}%")
            
            # Aggiorna log
            if self.temperature_log:
                self.temperature_log[-1]['valve'] = valve_pos
            
            return valve_pos
        
        # FASE 2: Controllo Relay Feedback
        if self.phase == 'relay':
            # Logica relay con isteresi
            if current_temp < self.setpoint - self.hysteresis:
                valve_pos = self.relay_high
                self.relay_state = True
            elif current_temp > self.setpoint + self.hysteresis:
                valve_pos = self.relay_low
                self.relay_state = False
            else:
                # Dentro isteresi: mantieni stato
                valve_pos = self.relay_high if self.relay_state else self.relay_low
            
            # Aggiorna log
            if self.temperature_log:
                self.temperature_log[-1]['valve'] = valve_pos
            
            # Rileva crossing e picchi
            self._detect_crossing(current_temp, elapsed)
            self._detect_peaks(current_temp, elapsed)
            
            # Verifica completamento
            if self._is_complete():
                self.phase = 'complete'
                self._calculate_pid()
                return 0  # Chiudi valvola
            
            return valve_pos
        
        # FASE 3: Test completato
        if self.phase == 'complete':
            return 0  # Chiudi valvola
        
        # FASE 4: Errore
        if self.phase == 'error':
            return 0  # Chiudi valvola
        
        return None
    
    def _detect_crossing(self, temp, elapsed):
        """Rileva attraversamento del setpoint"""
        if len(self.temp_buffer) < 2:
            return
        
        prev_temp = self.temp_buffer[-2]
        
        # Crossing dal basso (up)
        if prev_temp < self.setpoint <= temp:
            if self.last_direction != 'up':
                self.crossings.append({
                    'time': elapsed,
                    'direction': 'up',
                    'temp': temp
                })
                print(f"  ↗️ Crossing UP @ {elapsed:.1f}s, T={temp:.1f}°C")
                self.last_direction = 'up'
        
        # Crossing dall'alto (down)
        elif prev_temp > self.setpoint >= temp:
            if self.last_direction != 'down':
                self.crossings.append({
                    'time': elapsed,
                    'direction': 'down',
                    'temp': temp
                })
                print(f"  ↘️ Crossing DOWN @ {elapsed:.1f}s, T={temp:.1f}°C")
                self.last_direction = 'down'
    
    def _detect_peaks(self, temp, elapsed):
        """Rileva picchi massimi e minimi"""
        if len(self.temp_buffer) < 3:
            return
        
        temps = list(self.temp_buffer)
        
        # Picco massimo
        if temps[-3] < temps[-2] > temps[-1]:
            self.peaks.append({
                'time': elapsed,
                'type': 'max',
                'temp': temps[-2]
            })
            print(f"  🔺 Picco MAX: {temps[-2]:.1f}°C")
        
        # Picco minimo
        elif temps[-3] > temps[-2] < temps[-1]:
            self.peaks.append({
                'time': elapsed,
                'type': 'min',
                'temp': temps[-2]
            })
            print(f"  🔻 Picco MIN: {temps[-2]:.1f}°C")
    
    def _is_complete(self):
        """Verifica se raccolti dati sufficienti"""
        # Serve almeno min_oscillations cicli completi
        # 1 ciclo = 2 crossings (up + down)
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
        
        # Prendi ultimi picchi stabili
        max_peaks = [p['temp'] for p in self.peaks if p['type'] == 'max'][-3:]
        min_peaks = [p['temp'] for p in self.peaks if p['type'] == 'min'][-3:]
        
        avg_max = sum(max_peaks) / len(max_peaks)
        avg_min = sum(min_peaks) / len(min_peaks)
        
        self.amplitude = (avg_max - avg_min) / 2
        print(f"📏 Ampiezza oscillazione a = {self.amplitude:.1f}°C")
        print(f"   (Max: {avg_max:.1f}°C, Min: {avg_min:.1f}°C)")
        
        # 3. GUADAGNO CRITICO (Ku)
        d = self.relay_high - self.relay_low  # Ampiezza relay
        self.Ku = (4 * d) / (math.pi * self.amplitude)
        print(f"\n💪 Guadagno critico Ku = {self.Ku:.3f}")
        print(f"   (relay amplitude d = {d}%)")
        
        # 4. PARAMETRI PID con formule Ziegler-Nichols
        print("\n🎯 PARAMETRI PID CALCOLATI (Ziegler-Nichols):")
        
        # PID completo (può essere aggressivo)
        self.Kp = 0.6 * self.Ku
        self.Ki = 1.2 * self.Ku / self.Pu
        self.Kd = 0.075 * self.Ku * self.Pu
        
        print(f"   Kp = {self.Kp:.4f}")
        print(f"   Ki = {self.Ki:.6f}")
        print(f"   Kd = {self.Kd:.2f}")
        
        # Versione conservativa (consigliata per forno)
        kp_cons = 0.45 * self.Ku
        ki_cons = 0.54 * self.Ku / self.Pu
        
        print(f"\n💡 PARAMETRI CONSERVATIVI (consigliati):")
        print(f"   Kp = {kp_cons:.4f}")
        print(f"   Ki = {ki_cons:.6f}")
        print(f"   Kd = 0")
        
        print("="*60)
        
        # Salva risultati
        self._save_results()
    
    def _save_results(self):
        """Salva risultati test su file JSON"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"autotuning_{self.test_temperature}C_{timestamp}.json"
        filepath = os.path.join(LOGS_DIR, filename)
        
        # Prepara dati
        results = {
            'test_info': {
                'date': datetime.now().isoformat(),
                'temperature': self.test_temperature,
                'duration_minutes': (time.time() - self.start_time) / 60,
                'relay_high': self.relay_high,
                'relay_low': self.relay_low,
                'hysteresis': self.hysteresis,
                'oscillations': len(self.crossings) // 2
            },
            'measurements': {
                'Ku': round(self.Ku, 4),
                'Pu': round(self.Pu, 2),
                'amplitude': round(self.amplitude, 2)
            },
            'pid_standard': {
                'Kp': round(self.Kp, 4),
                'Ki': round(self.Ki, 6),
                'Kd': round(self.Kd, 2)
            },
            'pid_conservative': {
                'Kp': round(0.45 * self.Ku, 4),
                'Ki': round(0.54 * self.Ku / self.Pu, 6),
                'Kd': 0
            },
            'raw_data': {
                'crossings': self.crossings[-10:],  # Ultimi 10
                'peaks': self.peaks[-10:],
                'temperature_samples': len(self.temperature_log)
            }
        }
        
        # Salva
        os.makedirs(LOGS_DIR, exist_ok=True)
        with open(filepath, 'w') as f:
            json.dump(results, f, indent=2)
        
        print(f"\n💾 Risultati salvati: {filepath}")
        
        return filepath
    
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
            'data_points': len(self.temperature_log)
        }
    
    def get_results(self):
        """Ritorna risultati finali"""
        if self.phase != 'complete':
            return None
        
        return {
            'Ku': self.Ku,
            'Pu': self.Pu,
            'amplitude': self.amplitude,
            'Kp': self.Kp,
            'Ki': self.Ki,
            'Kd': self.Kd,
            'Kp_conservative': 0.45 * self.Ku,
            'Ki_conservative': 0.54 * self.Ku / self.Pu,
            'Kd_conservative': 0
        }
    
    def get_chart_data(self):
        """Ritorna dati per grafico real-time"""
        return {
            'temperatures': self.temperature_log[-100:],  # Ultimi 100 punti
            'crossings': self.crossings,
            'peaks': self.peaks,
            'setpoint': self.setpoint,
            'relay_high': self.relay_high,
            'relay_low': self.relay_low
        }
