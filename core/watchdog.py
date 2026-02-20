"""
Watchdog - Monitor di sicurezza indipendente

Il watchdog gira come thread separato e sorveglia:
1. Che il thread di monitoraggio temperature sia vivo (heartbeat)
2. Che il sensore stia producendo letture valide
3. Che non ci siano condizioni di emergenza non gestite

Se rileva anomalie, interviene direttamente chiudendo la valvola stepper
e (in futuro) la valvola elettromagnetica di sicurezza.

Il watchdog è l'ultima linea di difesa software prima della
valvola elettromagnetica hardware (normalmente chiusa).
"""

import time
import threading
from config import (
    WATCHDOG_INTERVAL,
    WATCHDOG_SENSOR_TIMEOUT,
    WATCHDOG_THREAD_TIMEOUT,
    SOLENOID_VALVE_ENABLED,
    SOLENOID_VALVE_PIN,
    OVER_TEMP
)


class SolenoidValve:
    """
    Controller valvola elettromagnetica di sicurezza (predisposizione futura)
    
    Valvola normalmente chiusa (NC):
    - Senza alimentazione → chiusa (gas bloccato) = stato sicuro
    - Con alimentazione (HIGH) → aperta (gas passa)
    
    Questo garantisce che in caso di blackout o crash totale
    il gas viene chiuso automaticamente dall'hardware.
    """
    
    def __init__(self, enabled=SOLENOID_VALVE_ENABLED, pin=SOLENOID_VALVE_PIN):
        self.enabled = enabled
        self.pin = pin
        self.is_open = False
        
        if self.enabled:
            import RPi.GPIO as GPIO
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.pin, GPIO.OUT, initial=GPIO.LOW)  # Parte chiusa
            print(f"✅ Valvola elettromagnetica configurata su GPIO {self.pin}")
        else:
            print("ℹ️  Valvola elettromagnetica: non installata (predisposizione)")
    
    def open(self):
        """Apri valvola (alimenta solenoide)"""
        if not self.enabled:
            return
        import RPi.GPIO as GPIO
        GPIO.output(self.pin, GPIO.HIGH)
        self.is_open = True
        print("🔓 Valvola elettromagnetica APERTA")
    
    def close(self):
        """Chiudi valvola (togli alimentazione solenoide) - STATO SICURO"""
        if not self.enabled:
            return
        import RPi.GPIO as GPIO
        GPIO.output(self.pin, GPIO.LOW)
        self.is_open = False
        print("🔒 Valvola elettromagnetica CHIUSA (sicurezza)")
    
    def get_status(self):
        return {
            'enabled': self.enabled,
            'pin': self.pin if self.enabled else None,
            'is_open': self.is_open
        }


class Watchdog:
    """
    Watchdog indipendente per sicurezza sistema forno.
    
    Monitora:
    - Heartbeat del thread di monitoraggio temperature
    - Timeout letture sensore
    - Sovratemperatura non gestita
    
    Interviene con:
    - Chiusura valvola stepper (via actuators)
    - Chiusura valvola elettromagnetica (quando installata)
    - Notifica di emergenza
    """
    
    def __init__(self, actuators, notifications):
        """
        Args:
            actuators: ActuatorManager instance
            notifications: NotificationService instance
        """
        self.actuators = actuators
        self.notifications = notifications
        self.solenoid = SolenoidValve()
        
        # Heartbeat dal thread monitor
        self._last_heartbeat = time.time()
        self._heartbeat_lock = threading.Lock()
        
        # Ultima lettura sensore valida
        self._last_valid_sensor_time = time.time()
        self._sensor_lock = threading.Lock()
        
        # Ultima temperatura nota
        self._last_temperature = 0.0
        
        # Stato watchdog
        self.is_running = False
        self._thread = None
        self._triggered = False       # True se il watchdog ha fatto un intervento
        self._trigger_reason = None
        self._trigger_count = 0       # Quante volte ha triggerato
        
        # Contatore notifiche (evita spam)
        self._last_notification_time = 0
        self._notification_cooldown = 60  # Minimo 60s tra notifiche watchdog
        
        print("🐕 Watchdog inizializzato")
    
    def start(self):
        """Avvia thread watchdog"""
        if self.is_running:
            return
        
        self.is_running = True
        self._triggered = False
        self._last_heartbeat = time.time()
        self._last_valid_sensor_time = time.time()
        
        # Apri valvola elettromagnetica (se installata) — permetti flusso gas
        if self.solenoid.enabled:
            self.solenoid.open()
        
        self._thread = threading.Thread(target=self._watchdog_loop, daemon=True)
        self._thread.start()
        print("🐕 Watchdog avviato")
    
    def stop(self):
        """Ferma watchdog"""
        self.is_running = False
        print("🐕 Watchdog fermato")
    
    def feed(self):
        """
        Heartbeat dal thread di monitoraggio.
        Deve essere chiamato regolarmente dal temperature_monitor_thread.
        Se non viene chiamato per WATCHDOG_THREAD_TIMEOUT secondi,
        il watchdog interviene.
        """
        with self._heartbeat_lock:
            self._last_heartbeat = time.time()
    
    def report_sensor_ok(self, temperature):
        """
        Segnala che il sensore ha prodotto una lettura valida.
        
        Args:
            temperature: Temperatura letta
        """
        with self._sensor_lock:
            self._last_valid_sensor_time = time.time()
            self._last_temperature = temperature
    
    def report_sensor_error(self):
        """Segnala errore sensore (non aggiorna il timer)"""
        pass  # Il timeout scatterà automaticamente
    
    def reset(self):
        """Reset stato watchdog dopo intervento manuale"""
        self._triggered = False
        self._trigger_reason = None
        self._last_heartbeat = time.time()
        self._last_valid_sensor_time = time.time()
        
        # Riapri valvola elettromagnetica (se installata)
        if self.solenoid.enabled:
            self.solenoid.open()
        
        print("🐕 Watchdog reset — stato normale")
    
    def _watchdog_loop(self):
        """Loop principale watchdog"""
        print(f"🐕 Watchdog loop avviato (intervallo: {WATCHDOG_INTERVAL}s)")
        
        while self.is_running:
            try:
                now = time.time()
                
                # Se già triggerato, continua a monitorare ma non ri-triggera
                if self._triggered:
                    time.sleep(WATCHDOG_INTERVAL)
                    continue
                
                # CHECK 1: Heartbeat thread monitor
                with self._heartbeat_lock:
                    heartbeat_age = now - self._last_heartbeat
                
                if heartbeat_age > WATCHDOG_THREAD_TIMEOUT:
                    self._trigger_emergency(
                        f"Thread monitor non risponde da {heartbeat_age:.0f}s "
                        f"(limite: {WATCHDOG_THREAD_TIMEOUT}s)"
                    )
                    continue
                
                # CHECK 2: Timeout sensore
                with self._sensor_lock:
                    sensor_age = now - self._last_valid_sensor_time
                    last_temp = self._last_temperature
                
                if sensor_age > WATCHDOG_SENSOR_TIMEOUT:
                    self._trigger_emergency(
                        f"Nessuna lettura sensore valida da {sensor_age:.0f}s "
                        f"(limite: {WATCHDOG_SENSOR_TIMEOUT}s)"
                    )
                    continue
                
                # CHECK 3: Sovratemperatura non gestita
                # (backup del safety_monitor — se per qualche motivo non ha agito)
                if last_temp > OVER_TEMP:
                    self._trigger_emergency(
                        f"Sovratemperatura rilevata dal watchdog: {last_temp:.1f}°C "
                        f"(limite: {OVER_TEMP}°C)"
                    )
                    continue
                
            except Exception as e:
                # Il watchdog non deve MAI crashare
                print(f"🐕 ⚠️ Errore nel watchdog (continuo): {e}")
            
            time.sleep(WATCHDOG_INTERVAL)
        
        print("🐕 Watchdog loop terminato")
    
    def _trigger_emergency(self, reason):
        """
        Azione di emergenza del watchdog.
        Chiude tutte le valvole e notifica.
        """
        self._triggered = True
        self._trigger_reason = reason
        self._trigger_count += 1
        
        print(f"\n{'!'*60}")
        print(f"🐕🚨 WATCHDOG EMERGENCY #{self._trigger_count}")
        print(f"   Motivo: {reason}")
        print(f"{'!'*60}")
        
        # 1. Chiudi valvola elettromagnetica (se installata) — azione più veloce
        if self.solenoid.enabled:
            try:
                self.solenoid.close()
            except Exception as e:
                print(f"🐕 ❌ Errore chiusura valvola elettromagnetica: {e}")
        
        # 2. Chiudi valvola stepper
        try:
            self.actuators.emergency_stop()
        except Exception as e:
            print(f"🐕 ❌ Errore chiusura valvola stepper: {e}")
        
        # 3. Notifica (con cooldown anti-spam)
        now = time.time()
        if now - self._last_notification_time > self._notification_cooldown:
            try:
                self.notifications.send(
                    "🐕🚨 WATCHDOG EMERGENCY",
                    f"Il watchdog ha chiuso il gas!\n"
                    f"Motivo: {reason}\n"
                    f"Intervento #{self._trigger_count}\n"
                    f"Controllare il forno IMMEDIATAMENTE!",
                    priority="max",
                    tags=["rotating_light", "dog"]
                )
                self._last_notification_time = now
            except Exception as e:
                print(f"🐕 ❌ Errore invio notifica watchdog: {e}")
    
    def get_status(self):
        """Stato completo watchdog"""
        now = time.time()
        
        with self._heartbeat_lock:
            heartbeat_age = now - self._last_heartbeat
        with self._sensor_lock:
            sensor_age = now - self._last_valid_sensor_time
        
        return {
            'running': self.is_running,
            'triggered': self._triggered,
            'trigger_reason': self._trigger_reason,
            'trigger_count': self._trigger_count,
            'heartbeat_age_seconds': round(heartbeat_age, 1),
            'sensor_age_seconds': round(sensor_age, 1),
            'solenoid': self.solenoid.get_status(),
            'thresholds': {
                'thread_timeout': WATCHDOG_THREAD_TIMEOUT,
                'sensor_timeout': WATCHDOG_SENSOR_TIMEOUT
            }
        }
