"""
Gestione Attuatori (Motore Stepper per Valvola Gas)

Sistema configurazione:
- Motore: NEMA17 1.8° (200 steps/giro)
- Riduzione: Pulegge 20 denti (motore) → 60 denti (valvola)
- Rapporto: 3:1 (3 giri motore = 1 giro valvola)
- Apertura totale: 7 giri motore = 2.33 giri valvola
- Steps totali: 1400 steps (200 steps/giro × 7 giri)
"""

import RPi.GPIO as GPIO
import time
import threading
from config import (
    STEPPER_STEP_PIN,
    STEPPER_DIR_PIN,
    STEPS_PER_REVOLUTION,
    MOTOR_TURNS_FULL_OPEN,
    VALVE_TOTAL_STEPS,
    GEAR_RATIO,
    STEPPER_SPEED_NORMAL,
    STEPPER_SPEED_SLOW
)


class StepperValveController:
    """
    Controller per valvola gas con motore stepper A4988
    Configurazione semplificata: full step, no endstops
    ENABLE collegato a GND (sempre abilitato)
    """
    
    def __init__(self):
        self.current_steps = 0      # Posizione attuale (0 = chiuso)
        self.target_position = 0    # Target in percentuale 0-100
        self.total_steps = VALVE_TOTAL_STEPS
        self.lock = threading.Lock()
        
        # Setup GPIO
        self._setup_gpio()
        
    def _setup_gpio(self):
        """Configura pin GPIO per stepper A4988 - TESTATO E FUNZIONANTE"""
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        
        # Pin Output con initial LOW (sicuro)
        GPIO.setup(STEPPER_STEP_PIN, GPIO.OUT, initial=GPIO.LOW)
        GPIO.setup(STEPPER_DIR_PIN, GPIO.OUT, initial=GPIO.LOW)
        
        # ENABLE collegato a GND fisicamente (sempre abilitato)
        
        print(f"✅ GPIO configurato - STEP:{STEPPER_STEP_PIN} DIR:{STEPPER_DIR_PIN}")
        print(f"   Resistori 10kΩ su STEP e DIR collegati a GND")
        print(f"   ENABLE collegato a GND (sempre abilitato)")
        
    def step(self, direction, steps, speed=STEPPER_SPEED_NORMAL):
        """
        Muove motore di N steps - TESTATO E FUNZIONANTE
        
        Args:
            direction (bool): True=apri (orario), False=chiudi (antiorario)
            steps (int): Numero di steps da muovere
            speed (float): Delay tra steps in secondi (testato: 0.01s)
        """
        # Imposta direzione
        GPIO.output(STEPPER_DIR_PIN, GPIO.HIGH if direction else GPIO.LOW)
        time.sleep(0.1)  # Pausa per stabilizzare direzione (importante!)
        
        # Esegui steps
        for i in range(steps):
            GPIO.output(STEPPER_STEP_PIN, GPIO.HIGH)
            time.sleep(speed)
            GPIO.output(STEPPER_STEP_PIN, GPIO.LOW)
            time.sleep(speed)
            
            # Aggiorna posizione
            if direction:
                self.current_steps += 1
            else:
                self.current_steps -= 1
            
            # Limiti software
            if self.current_steps < 0:
                self.current_steps = 0
                print("⚠️ Limite chiusura raggiunto")
                break
            if self.current_steps > self.total_steps:
                self.current_steps = self.total_steps
                print("⚠️ Limite apertura raggiunto")
                break
    
    def set_position(self, percentage):
        """
        Imposta posizione valvola in percentuale
        
        Args:
            percentage (float): Apertura 0-100%
                0% = completamente chiuso
                100% = completamente aperto
        
        Returns:
            float: Posizione reale raggiunta (%)
        """
        with self.lock:
            # Limita range
            percentage = max(0, min(100, percentage))
            
            # Calcola steps target
            target_steps = int((percentage / 100.0) * self.total_steps)
            steps_to_move = target_steps - self.current_steps
            
            if steps_to_move == 0:
                return percentage
            
            # Muovi motore
            direction = steps_to_move > 0  # True=apri, False=chiudi
            steps_abs = abs(steps_to_move)
            
            print(f"🔧 Valvola: {self.get_position_percent():.1f}% → {percentage:.1f}% ({steps_to_move:+d} steps)")
            
            self.step(direction, steps_abs)
            
            # Salva target
            self.target_position = percentage
            
            # Ritorna posizione effettiva
            actual = self.get_position_percent()
            return actual
    
    def get_position_percent(self):
        """Ritorna posizione attuale in percentuale"""
        return round((self.current_steps / self.total_steps) * 100, 1)
    
    def get_position_steps(self):
        """Ritorna posizione attuale in steps"""
        return self.current_steps
    
    def calibrate(self, manual_steps=0):
        """
        Calibrazione manuale posizione
        Senza endstops, bisogna impostare manualmente lo zero
        
        Sistema pulegge 3:1 (20:60 denti):
        - 1 giro motore = 1/3 giro valvola
        - 7 giri motore = apertura completa = 1400 steps
        
        Args:
            manual_steps (int): Se >0, muove chiudendo di N steps prima di azzerare
        """
        print("🏠 Calibrazione valvola...")
        print(f"   Sistema: Pulegge 20:60 denti (rapporto 3:1)")
        print(f"   Range: 0 → {self.total_steps} steps (7 giri motore)")
        
        if manual_steps > 0:
            print(f"   Chiusura di {manual_steps} steps...")
            self.step(False, manual_steps, speed=STEPPER_SPEED_SLOW)
        
        # Azzera contatore
        self.current_steps = 0
        self.target_position = 0
        
        print("✅ Calibrazione completata - Posizione azzerata")
        print(f"   Apertura totale richiede: {MOTOR_TURNS_FULL_OPEN} giri motore")
    
    def emergency_close(self):
        """
        Chiusura emergenza - bypassa set_position per evitare deadlock
        Muove direttamente lo stepper alla posizione 0
        """
        print("🚨 CHIUSURA EMERGENZA VALVOLA!")
        with self.lock:
            if self.current_steps > 0:
                self.step(False, self.current_steps, speed=STEPPER_SPEED_NORMAL)
            self.current_steps = 0
            self.target_position = 0
    
    def get_status(self):
        """Ritorna stato completo valvola"""
        return {
            'position_percent': self.get_position_percent(),
            'position_steps': self.current_steps,
            'target_percent': self.target_position,
            'total_steps': self.total_steps,
            'motor_turns': round(self.current_steps / STEPS_PER_REVOLUTION, 2),
            'valve_turns': round(self.current_steps / STEPS_PER_REVOLUTION / GEAR_RATIO, 2),
            'gear_ratio': GEAR_RATIO
        }
    
    def cleanup(self):
        """
        Cleanup GPIO con shutdown sicuro - TESTATO
        Porta pin a LOW senza GPIO.cleanup() per evitare stati floating
        """
        print("🧹 Shutdown sicuro valvola...")
        self.emergency_close()  # Chiudi valvola (gestisce il lock internamente)
        
        # Porta pin a LOW (sicuro)
        GPIO.output(STEPPER_STEP_PIN, GPIO.LOW)
        GPIO.output(STEPPER_DIR_PIN, GPIO.LOW)
        time.sleep(0.5)
        
        # NON fare GPIO.cleanup() - evita stati floating
        print("✅ Pin GPIO a LOW - Motore fermo")


class ActuatorManager:
    """
    Manager centrale per tutti gli attuatori
    Gestisce coordinamento e sicurezza
    """
    
    def __init__(self):
        self.valve = StepperValveController()
        
        # Placeholder per futuri attuatori
        # self.ignition = IgnitionControl()
        # self.cooling_fan = CoolingFan()
        # self.exhaust_damper = DamperControl()
        
        print("✅ ActuatorManager inizializzato")
        
    def set_valve_position(self, percentage):
        """
        Imposta posizione valvola
        
        Args:
            percentage (float): Apertura 0-100%
        
        Returns:
            float: Posizione effettiva raggiunta
        """
        return self.valve.set_position(percentage)
    
    def get_valve_position(self):
        """Ottieni posizione attuale valvola"""
        return self.valve.get_position_percent()
    
    def calibrate_valve(self, manual_steps=0):
        """Calibra valvola (azzera posizione)"""
        self.valve.calibrate(manual_steps)
    
    def emergency_stop(self):
        """
        STOP EMERGENZA - chiude tutto
        """
        print("🚨 EMERGENCY STOP ATTUATORI!")
        self.valve.emergency_close()
        # self.ignition.off()
        # self.cooling_fan.on()
    
    def get_status(self):
        """Stato completo tutti attuatori"""
        return {
            'valve': self.valve.get_status()
            # 'ignition': self.ignition.get_status(),
            # 'fan': self.cooling_fan.get_status(),
        }
    
    def cleanup(self):
        """Cleanup completo sistema - SHUTDOWN SICURO"""
        print("🧹 Cleanup completo attuatori...")
        self.valve.cleanup()
        
        # NON fare GPIO.cleanup() - mantiene pin OUTPUT LOW
        # Evita stati floating che farebbero girare il motore
        print("✅ Cleanup completato - Pin GPIO a LOW (sicuro)")
