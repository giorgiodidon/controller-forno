"""
Program Runner - Motore di esecuzione programmi di cottura

Gestisce l'intero ciclo di cottura server-side:
- Calcola il setpoint corrente in base alla rampa attiva
- Comanda il PID e la valvola ad intervalli adeguati all'inerzia termica
- Avanza le fasi (rampa/hold) in base alla temperatura REALE, non al tempo
- Supporta rampe in salita e in discesa (raffreddamento controllato)
- Completa automaticamente il programma dopo l'ultima fase

NOTA SULL'INTERVALLO DI AGGIORNAMENTO:
Un forno ceramica a mattoni ha inerzia termica enorme (minuti).
L'intervallo PID→valvola è 30s di default (PID_CYCLE_INTERVAL).
Le letture sensore restano ogni 2s per grafico e sicurezza,
ma il PID calcola e comanda la valvola solo ogni 30s.
Questo evita che il PID accumuli errore integrale eccessivo
su un sistema che risponde lentamente.
L'autotuning futuro misurerà il periodo critico reale del forno
e i parametri PID saranno calibrati su quel periodo.
"""

import time
import threading
from collections import deque
from config import (
    PID_CYCLE_INTERVAL,
    TEMP_SMOOTHING_WINDOW,
    RAMP_TOLERANCE,
    HOLD_TOLERANCE,
    SENSOR_UPDATE_INTERVAL,
    TEMP_LOG_INTERVAL,
    VALVE_MAX_STEP_PER_CYCLE
)


class ProgramRunner:
    """
    Esecutore programmi di cottura.
    
    Gira come thread dedicato. Ad ogni ciclo PID (30s default):
    1. Legge temperatura reale (media smorzata)
    2. Calcola setpoint dalla rampa corrente
    3. Calcola output PID
    4. Comanda valvola
    5. Aggiorna stato per il frontend
    """
    
    def __init__(self, pid_controller, actuators, sensors, logger,
                 notifications, program_state, temperature_data):
        """
        Args:
            pid_controller: PIDController instance
            actuators: ActuatorManager instance
            sensors: SensorManager (per lettura diretta)
            logger: DataLogger instance
            notifications: NotificationService instance
            program_state: dict globale condiviso con Flask
            temperature_data: dict globale temperature
        """
        self.pid = pid_controller
        self.actuators = actuators
        self.sensors = sensors
        self.logger = logger
        self.notifications = notifications
        self.program_state = program_state
        self.temperature_data = temperature_data
        
        # Stato interno
        self._thread = None
        self._stop_event = threading.Event()
        self.is_running = False
        
        # Dati programma
        self.program_name = ''
        self.ramps = []
        self.current_ramp_index = 0    # Indice rampa attuale (0-based)
        self.phase = 'idle'            # idle, ramp, hold, complete, stopped
        
        # Setpoint e tracking
        self.current_setpoint = 20.0   # Setpoint attuale (°C)
        self.ramp_start_temp = 20.0    # Temperatura inizio rampa corrente
        self.ramp_start_time = 0       # Timestamp inizio rampa corrente
        
        # Hold tracking
        self.hold_remaining = 0        # Secondi rimasti di hold
        self.hold_total = 0            # Secondi totali hold corrente
        
        # Tempo avvio programma
        self.start_time = 0            # Timestamp avvio (secondi)
        
        # Buffer temperature per media mobile (smorza rumore sensore)
        self.temp_buffer = deque(maxlen=TEMP_SMOOTHING_WINDOW)
        
        # Ultimo comando valvola
        self.last_valve_output = 0.0
        
        # Ultimo log temperatura
        self._last_log_time = 0
    
    def start(self, program_name, ramps):
        """
        Avvia esecuzione programma.
        
        Args:
            program_name: Nome del programma
            ramps: Lista rampe [{'target':T, 'rate':R, 'hold':H}, ...]
                   rate in °C/h, hold in minuti, target in °C
        """
        if self.is_running:
            print("⚠️ ProgramRunner: programma già in esecuzione")
            return False
        
        if not ramps:
            print("❌ ProgramRunner: nessuna rampa definita")
            return False
        
        self.program_name = program_name
        self.ramps = ramps
        self.current_ramp_index = 0
        self.start_time = time.time()
        self.temp_buffer.clear()
        self._last_log_time = 0
        
        # Reset PID
        self.pid.reset()
        
        # Inizia dalla prima rampa
        self._start_ramp(0)
        
        # Aggiorna stato globale
        self._update_program_state()
        
        # Avvia thread
        self._stop_event.clear()
        self.is_running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        
        # Log e notifica
        self.logger.start_logging(program_name)
        self.logger.log_event('program_start', f'Programma "{program_name}" avviato - {len(ramps)} rampe')
        self.notifications.notify_program_start(program_name)
        
        print(f"🔥 ProgramRunner: avviato '{program_name}' con {len(ramps)} rampe")
        return True
    
    def stop(self):
        """Ferma esecuzione programma (stop manuale)"""
        if not self.is_running:
            return
        
        self._stop_event.set()
        self.is_running = False
        self.phase = 'stopped'
        
        # Chiudi valvola
        self.actuators.set_valve_position(0)
        self.last_valve_output = 0
        
        # Log e notifica
        elapsed_min = (time.time() - self.start_time) / 60
        self.logger.log_event('program_stop', f'Programma fermato manualmente dopo {elapsed_min:.1f} min')
        self.logger.stop_logging()
        self.notifications.notify_program_stopped()
        
        # Resetta stato globale
        self._reset_program_state()
        
        print(f"⏹️ ProgramRunner: '{self.program_name}' fermato")
    
    def emergency_stop(self):
        """Stop di emergenza — chiude tutto immediatamente"""
        self._stop_event.set()
        self.is_running = False
        self.phase = 'stopped'
        self.last_valve_output = 0
        
        # La chiusura valvola è gestita da actuators.emergency_stop() in app.py
        
        self.logger.log_event('emergency_stop', 'ARRESTO DI EMERGENZA')
        self.logger.stop_logging()
        self._reset_program_state()
        
        print("🚨 ProgramRunner: EMERGENCY STOP")
    
    def _start_ramp(self, index):
        """Inizializza una nuova rampa"""
        if index >= len(self.ramps):
            return
        
        ramp = self.ramps[index]
        self.current_ramp_index = index
        self.phase = 'ramp'
        
        # Temperatura di partenza: la temperatura reale attuale
        current_temp = self._get_smoothed_temp()
        if current_temp is None:
            current_temp = self.current_setpoint  # Fallback
        
        self.ramp_start_temp = current_temp
        self.ramp_start_time = time.time()
        
        # Il setpoint parte dalla temperatura attuale
        self.current_setpoint = current_temp
        
        target = float(ramp.get('target', 200))
        rate = float(ramp.get('rate', 100))
        direction = "salita" if target > current_temp else "discesa"
        
        self.logger.log_event(
            'ramp_start',
            f'Rampa {index + 1}/{len(self.ramps)} → {target}°C a {rate}°C/h ({direction})'
        )
        
        print(f"📈 Rampa {index + 1}: {current_temp:.1f}°C → {target}°C @ {rate}°C/h ({direction})")
    
    def _start_hold(self):
        """Inizializza fase di mantenimento"""
        ramp = self.ramps[self.current_ramp_index]
        hold_minutes = float(ramp.get('hold', 0))
        
        if hold_minutes <= 0:
            # Nessun hold, passa direttamente alla prossima rampa
            self._advance_to_next_ramp()
            return
        
        self.phase = 'hold'
        self.hold_total = hold_minutes * 60  # Converti in secondi
        self.hold_remaining = self.hold_total
        target = float(ramp.get('target', 200))
        
        self.logger.log_event(
            'hold_start',
            f'Mantenimento {target}°C per {hold_minutes:.0f} min'
        )
        self.notifications.notify_hold_start(target, hold_minutes)
        
        print(f"⏱️ Hold: {target}°C per {hold_minutes:.0f} min")
    
    def _advance_to_next_ramp(self):
        """Passa alla rampa successiva o completa il programma"""
        ramp = self.ramps[self.current_ramp_index]
        target = float(ramp.get('target', 0))
        
        self.notifications.notify_ramp_complete(
            self.current_ramp_index + 1,
            len(self.ramps),
            target
        )
        
        next_index = self.current_ramp_index + 1
        if next_index < len(self.ramps):
            self._start_ramp(next_index)
        else:
            self._complete_program()
    
    def _complete_program(self):
        """Programma completato con successo"""
        self.phase = 'complete'
        self.is_running = False
        self._stop_event.set()
        
        # Chiudi valvola
        self.actuators.set_valve_position(0)
        self.last_valve_output = 0
        
        elapsed_min = (time.time() - self.start_time) / 60
        
        self.logger.log_event('program_complete', f'Programma completato in {elapsed_min:.1f} min')
        self.logger.complete_logging()
        self.notifications.notify_program_complete(self.program_name, elapsed_min)
        
        # Resetta stato globale
        self._reset_program_state()
        
        print(f"✅ ProgramRunner: '{self.program_name}' completato in {elapsed_min:.1f} min")
    
    def _run_loop(self):
        """Loop principale del runner — gira ogni PID_CYCLE_INTERVAL secondi"""
        print(f"🔥 ProgramRunner loop avviato (ciclo PID ogni {PID_CYCLE_INTERVAL}s)")
        
        while not self._stop_event.is_set():
            try:
                self._cycle()
            except Exception as e:
                print(f"❌ ProgramRunner errore nel ciclo: {e}")
                self.logger.log_event('error', f'Errore runner: {e}')
            
            # Attendi il prossimo ciclo PID (interrompibile con stop_event)
            self._stop_event.wait(timeout=PID_CYCLE_INTERVAL)
        
        print("🔥 ProgramRunner loop terminato")
    
    def _cycle(self):
        """Singolo ciclo di controllo PID"""
        # 1. Leggi temperatura smorzata
        current_temp = self._get_smoothed_temp()
        if current_temp is None:
            print("⚠️ ProgramRunner: nessuna lettura temperatura valida")
            return
        
        # Aggiungi al buffer
        self.temp_buffer.append(current_temp)
        
        ramp = self.ramps[self.current_ramp_index]
        target = float(ramp.get('target', 200))
        rate = float(ramp.get('rate', 100))
        
        # 2. Calcola setpoint in base alla fase
        if self.phase == 'ramp':
            self._process_ramp(current_temp, target, rate)
        elif self.phase == 'hold':
            self._process_hold(current_temp, target)
        
        # 3. Calcola output PID
        pid_raw_output = self.pid.compute(self.current_setpoint, current_temp)
        
        # 4. Rate limiter — limita il salto massimo per ciclo
        valve_limited = False
        valve_output = pid_raw_output
        delta = valve_output - self.last_valve_output
        if abs(delta) > VALVE_MAX_STEP_PER_CYCLE:
            valve_limited = True
            if delta > 0:
                valve_output = self.last_valve_output + VALVE_MAX_STEP_PER_CYCLE
            else:
                valve_output = self.last_valve_output - VALVE_MAX_STEP_PER_CYCLE
            valve_output = max(0, min(100, valve_output))
        
        # 5. Comanda valvola
        self.actuators.set_valve_position(valve_output)
        self.last_valve_output = valve_output
        
        # 6. Aggiorna stato per frontend
        self._update_program_state()
        
        # 7. Calcola derivata temperatura (°C/min)
        temp_rate = 0.0
        if len(self.temp_buffer) >= 2:
            dt_samples = PID_CYCLE_INTERVAL / 60.0  # minuti tra campioni
            temp_rate = (self.temp_buffer[-1] - self.temp_buffer[-2]) / dt_samples if dt_samples > 0 else 0
        
        # 8. Log periodico con tutti i dati
        now = time.time()
        if now - self._last_log_time >= TEMP_LOG_INTERVAL:
            self.logger.log_temperature(
                temp=current_temp,
                setpoint=self.current_setpoint,
                valve_position=valve_output,
                cooling_rate=self.temperature_data.get('cooling_rate', 0),
                pid_terms=self.pid.get_terms(),
                valve_limited=valve_limited,
                pid_raw=pid_raw_output,
                temp_cold=self.temperature_data.get('cold', 0),
                temp_rate=temp_rate
            )
            self._last_log_time = now
        
        # Debug
        limited_str = " [LIM]" if valve_limited else ""
        phase_str = f"RAMP→{target}°C" if self.phase == 'ramp' else f"HOLD {target}°C ({self.hold_remaining:.0f}s)"
        print(f"  🌡️ T={current_temp:.1f}°C SP={self.current_setpoint:.1f}°C "
              f"PID={pid_raw_output:.1f}%→V={valve_output:.1f}%{limited_str} [{phase_str}] "
              f"R{self.current_ramp_index + 1}/{len(self.ramps)}")
    
    def _process_ramp(self, current_temp, target, rate):
        """
        Processa fase rampa.
        Il setpoint avanza alla velocità rate (°C/h).
        Supporta sia salita che discesa.
        """
        # Calcola incremento setpoint basato sul tempo trascorso
        dt = PID_CYCLE_INTERVAL  # secondi dall'ultimo ciclo
        rate_per_second = rate / 3600.0
        delta = rate_per_second * dt
        
        is_heating = target > self.ramp_start_temp
        
        if is_heating:
            # Rampa in salita
            self.current_setpoint += delta
            self.current_setpoint = min(self.current_setpoint, float(target))
            
            # Rampa completa quando temperatura reale raggiunge target
            if current_temp >= target - RAMP_TOLERANCE:
                print(f"  ✅ Rampa {self.current_ramp_index + 1} completata: "
                      f"T={current_temp:.1f}°C >= target {target}°C (±{RAMP_TOLERANCE})")
                self._start_hold()
        else:
            # Rampa in discesa (raffreddamento controllato)
            self.current_setpoint -= delta
            self.current_setpoint = max(self.current_setpoint, float(target))
            
            # Rampa completa quando temperatura reale scende al target
            if current_temp <= target + RAMP_TOLERANCE:
                print(f"  ✅ Rampa {self.current_ramp_index + 1} completata (discesa): "
                      f"T={current_temp:.1f}°C <= target {target}°C (±{RAMP_TOLERANCE})")
                self._start_hold()
    
    def _process_hold(self, current_temp, target):
        """
        Processa fase hold.
        Il timer hold scorre SOLO quando la temperatura è entro tolleranza.
        """
        self.current_setpoint = float(target)
        
        # Il timer avanza solo se la temperatura è entro tolleranza
        if abs(current_temp - target) <= HOLD_TOLERANCE:
            self.hold_remaining -= PID_CYCLE_INTERVAL
            
            if self.hold_remaining <= 0:
                self.hold_remaining = 0
                hold_min = self.hold_total / 60
                print(f"  ✅ Hold completato: {target}°C per {hold_min:.0f} min")
                self.logger.log_event(
                    'hold_complete',
                    f'Mantenimento {target}°C completato ({hold_min:.0f} min)'
                )
                self._advance_to_next_ramp()
        else:
            # Fuori tolleranza: timer fermo
            diff = current_temp - target
            direction = "sopra" if diff > 0 else "sotto"
            remaining_min = self.hold_remaining / 60
            print(f"  ⏸️ Hold in pausa: T={current_temp:.1f}°C ({direction} {abs(diff):.1f}°C), "
                  f"rimangono {remaining_min:.1f} min")
    
    def _get_smoothed_temp(self):
        """
        Ritorna temperatura media smorzata.
        Usa il buffer delle ultime N letture per ridurre il rumore.
        Se il buffer è vuoto, legge direttamente dal dict globale.
        """
        # Prendi dalla temperatura globale (aggiornata dal thread monitor)
        current = self.temperature_data.get('hot', 0)
        
        if current <= 0 and self.temperature_data.get('status') != 'connected':
            if len(self.temp_buffer) > 0:
                return sum(self.temp_buffer) / len(self.temp_buffer)
            return None
        
        self.temp_buffer.append(current)
        
        if len(self.temp_buffer) > 0:
            return sum(self.temp_buffer) / len(self.temp_buffer)
        
        return current
    
    def _update_program_state(self):
        """Aggiorna il dict globale program_state per il frontend"""
        ramp = self.ramps[self.current_ramp_index] if self.current_ramp_index < len(self.ramps) else {}
        target = float(ramp.get('target', 0))
        rate = float(ramp.get('rate', 0))
        
        # Calcola progresso rampa
        ramp_progress = 0
        if self.phase == 'ramp':
            delta_total = abs(target - self.ramp_start_temp)
            if delta_total > 0:
                current_temp = self._get_smoothed_temp() or self.current_setpoint
                delta_done = abs(current_temp - self.ramp_start_temp)
                ramp_progress = min(100, max(0, (delta_done / delta_total) * 100))
        elif self.phase == 'hold':
            ramp_progress = 100  # Rampa completata, in hold
        
        # Calcola tempi rimanenti
        elapsed_min = (time.time() - self.start_time) / 60
        total_estimated = self._estimate_total_minutes()
        remaining_min = max(0, total_estimated - elapsed_min)
        
        # Hold rimanente
        hold_remaining_min = self.hold_remaining / 60 if self.phase == 'hold' else 0
        
        # Tempo rampa rimanente (stima)
        ramp_remaining_min = 0
        if self.phase == 'ramp' and rate > 0:
            current_temp = self._get_smoothed_temp() or self.current_setpoint
            temp_remaining = abs(target - current_temp)
            ramp_remaining_min = (temp_remaining / rate) * 60
        
        self.program_state['running'] = self.is_running
        self.program_state['name'] = self.program_name
        self.program_state['program_name'] = self.program_name
        self.program_state['ramps'] = self.ramps
        self.program_state['current_ramp'] = self.current_ramp_index + 1
        self.program_state['total_ramps'] = len(self.ramps)
        self.program_state['current_setpoint'] = round(self.current_setpoint, 1)
        self.program_state['target_temp'] = target
        self.program_state['rate'] = rate
        self.program_state['phase'] = self.phase
        self.program_state['start_time'] = self.start_time * 1000  # ms per JS
        self.program_state['ramp_progress'] = round(ramp_progress, 1)
        self.program_state['ramp_remaining_min'] = round(ramp_remaining_min, 1)
        self.program_state['hold_remaining_min'] = round(hold_remaining_min, 1)
        self.program_state['total_remaining_min'] = round(remaining_min, 1)
        self.program_state['elapsed_min'] = round(elapsed_min, 1)
        self.program_state['valve_output'] = round(self.last_valve_output, 1)
    
    def _reset_program_state(self):
        """Resetta lo stato globale"""
        self.program_state['running'] = False
        self.program_state['name'] = ''
        self.program_state['program_name'] = ''
        self.program_state['ramps'] = []
        self.program_state['current_ramp'] = 0
        self.program_state['total_ramps'] = 0
        self.program_state['current_setpoint'] = 20.0
        self.program_state['target_temp'] = 0
        self.program_state['rate'] = 0
        self.program_state['phase'] = 'idle'
        self.program_state['start_time'] = None
        self.program_state['ramp_progress'] = 0
        self.program_state['ramp_remaining_min'] = 0
        self.program_state['hold_remaining_min'] = 0
        self.program_state['total_remaining_min'] = 0
        self.program_state['elapsed_min'] = 0
        self.program_state['valve_output'] = 0
    
    def _estimate_total_minutes(self):
        """Stima tempo totale programma in minuti (basata sulle rampe rimanenti)"""
        total = 0
        temp = self.ramp_start_temp if self.current_ramp_index == 0 else 20
        
        for i, ramp in enumerate(self.ramps):
            target = float(ramp.get('target', 200))
            rate = max(float(ramp.get('rate', 100)), 10)
            hold = float(ramp.get('hold', 0))
            
            delta = abs(target - temp)
            ramp_min = (delta / rate) * 60
            total += ramp_min + hold
            temp = target
        
        return total
    
    def get_status(self):
        """Stato del runner per diagnostica"""
        return {
            'is_running': self.is_running,
            'program_name': self.program_name,
            'phase': self.phase,
            'current_ramp': self.current_ramp_index + 1,
            'total_ramps': len(self.ramps),
            'current_setpoint': round(self.current_setpoint, 1),
            'valve_output': round(self.last_valve_output, 1),
            'hold_remaining': round(self.hold_remaining, 0) if self.phase == 'hold' else 0,
            'elapsed_seconds': round(time.time() - self.start_time, 0) if self.start_time else 0
        }
