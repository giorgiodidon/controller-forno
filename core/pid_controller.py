"""
Controller PID per regolazione temperatura forno
"""

import time
from config import (
    PID_KP, PID_KI, PID_KD,
    PID_INTEGRAL_MAX, PID_INTEGRAL_MIN
)


class PIDController:
    """
    Controller PID per temperatura forno ceramica
    """
    
    def __init__(self, kp=PID_KP, ki=PID_KI, kd=PID_KD):
        """
        Args:
            kp (float): Guadagno proporzionale (risposta immediata)
            ki (float): Guadagno integrale (elimina errore stazionario)
            kd (float): Guadagno derivativo (smorzamento oscillazioni)
        """
        self.kp = kp
        self.ki = ki
        self.kd = kd
        
        # Stato interno
        self.prev_error = 0.0
        self.integral = 0.0
        self.prev_time = time.time()
        
        # Limiti anti-windup integrale
        self.integral_max = PID_INTEGRAL_MAX
        self.integral_min = PID_INTEGRAL_MIN
        
        # Stato ultimo calcolo — per log, diagnostica, ML
        self.last_output = 0.0
        self.last_error = 0.0
        self.last_p_term = 0.0
        self.last_i_term = 0.0
        self.last_d_term = 0.0
        self.last_dt = 0.0
        
    def compute(self, setpoint, current_value):
        """
        Calcola output PID
        
        Args:
            setpoint (float): Temperatura target (°C)
            current_value (float): Temperatura attuale (°C)
        
        Returns:
            float: Output PID 0-100% (apertura valvola)
        """
        now = time.time()
        dt = now - self.prev_time
        
        # Evita divisione per zero
        if dt <= 0:
            dt = 0.1
        
        # Calcolo errore
        error = setpoint - current_value
        
        # Termine proporzionale
        p_term = self.kp * error
        
        # Termine integrale con anti-windup
        self.integral += error * dt
        self.integral = max(self.integral_min, min(self.integral_max, self.integral))
        i_term = self.ki * self.integral
        
        # Termine derivativo
        derivative = (error - self.prev_error) / dt
        d_term = self.kd * derivative
        
        # Output totale PID
        output = p_term + i_term + d_term
        
        # Limita output 0-100%
        output = max(0, min(100, output))
        
        # Salva tutto per diagnostica, log e ML
        self.prev_error = error
        self.prev_time = now
        self.last_output = output
        self.last_error = error
        self.last_p_term = p_term
        self.last_i_term = i_term
        self.last_d_term = d_term
        self.last_dt = dt
        
        return output
    
    def get_terms(self):
        """
        Ritorna i termini dell'ultimo calcolo PID.
        Per logging, diagnostica, ML e PID adattivo.
        
        Returns:
            dict: {p, i, d, error, output, integral, dt, kp, ki, kd}
        """
        return {
            'p': round(self.last_p_term, 3),
            'i': round(self.last_i_term, 3),
            'd': round(self.last_d_term, 3),
            'error': round(self.last_error, 2),
            'output': round(self.last_output, 1),
            'integral': round(self.integral, 2),
            'dt': round(self.last_dt, 2),
            'kp': self.kp,
            'ki': self.ki,
            'kd': self.kd
        }
    
    def reset(self):
        """Reset stato PID (chiamare quando si cambia setpoint)"""
        self.integral = 0.0
        self.prev_error = 0.0
        self.prev_time = time.time()
        self.last_p_term = 0.0
        self.last_i_term = 0.0
        self.last_d_term = 0.0
        print("🔄 PID reset")
    
    def set_tunings(self, kp, ki, kd):
        """
        Aggiorna parametri PID (da autotuning)
        
        Args:
            kp, ki, kd (float): Nuovi parametri
        """
        self.kp = kp
        self.ki = ki
        self.kd = kd
        print(f"⚙️ PID tuning aggiornato: Kp={kp:.3f} Ki={ki:.3f} Kd={kd:.3f}")
    
    def get_tunings(self):
        """Ritorna parametri attuali"""
        return {
            'kp': self.kp,
            'ki': self.ki,
            'kd': self.kd
        }
    
    def get_status(self):
        """Stato completo PID per diagnostica"""
        return {
            'kp': self.kp,
            'ki': self.ki,
            'kd': self.kd,
            'integral': round(self.integral, 2),
            'last_error': round(self.last_error, 2),
            'last_output': round(self.last_output, 1),
            'last_p': round(self.last_p_term, 3),
            'last_i': round(self.last_i_term, 3),
            'last_d': round(self.last_d_term, 3)
        }
