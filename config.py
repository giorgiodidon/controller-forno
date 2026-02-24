"""
Configurazione centralizzata Forno Ceramica
"""

# ===== HARDWARE I2C =====
I2C_BUS = 1
MCP9600_ADDR = 0x60

# ===== GPIO PINS =====
# Stepper Motor A4988
# TESTATO E FUNZIONANTE - NON MODIFICARE
STEPPER_STEP_PIN = 18   # GPIO 18 (Pin fisico 12) - Giallo
STEPPER_DIR_PIN = 17    # GPIO 17 (Pin fisico 11) - Verde
# ENABLE collegato a GND sull'A4988 (sempre abilitato)
# Resistori 10kOhm su STEP e DIR collegati a GND

# ===== STEPPER CONFIGURATION =====
STEPS_PER_REVOLUTION = 200  # Motore NEMA17 1.8° = 200 steps/giro

# Sistema pulegge
MOTOR_PULLEY_TEETH = 20     # Denti puleggia motore
VALVE_PULLEY_TEETH = 60     # Denti puleggia valvola
GEAR_RATIO = VALVE_PULLEY_TEETH / MOTOR_PULLEY_TEETH  # 60/20 = 3:1

# Apertura valvola
MOTOR_TURNS_FULL_OPEN = 7   # Giri motore per apertura totale valvola
VALVE_TURNS_FULL_OPEN = MOTOR_TURNS_FULL_OPEN / GEAR_RATIO  # 7/3 = 2.33 giri valvola

# Steps totali motore per apertura completa
VALVE_TOTAL_STEPS = int(STEPS_PER_REVOLUTION * MOTOR_TURNS_FULL_OPEN)  # 200 * 7 = 1400 steps

# Velocità stepper (secondi tra step)
# TESTATO: 0.01s (10ms) funziona perfettamente
STEPPER_SPEED_NORMAL = 0.01    # 10ms - testato e stabile
STEPPER_SPEED_SLOW = 0.02      # 20ms - per movimenti delicati

# ===== SAFETY LIMITS =====
MAX_TEMP = 1290        # °C - Temperatura massima lavoro
OVER_TEMP = 1310       # °C - Allarme critico
MAX_RATE_UP = 400      # °C/h - Massima velocità riscaldamento
MAX_RATE_DOWN = 300    # °C/h - Massima velocità raffreddamento (sotto 700°C)
TEMP_TOLERANCE = 15    # °C - Tolleranza per mantenimento temperatura

# Soglie allarmi
COOLING_RATE_WARNING = 300  # °C/h - Raffreddamento troppo rapido

# ===== PID CONTROLLER =====
# Parametri default (da autotuning)
PID_KP = 2.5
PID_KI = 0.03
PID_KD = 1.8

# Limiti anti-windup
PID_INTEGRAL_MAX = 500
PID_INTEGRAL_MIN = -500

# ===== NOTIFICHE NTFY =====
NTFY_TOPIC = "forno_giorgio"
NTFY_ENABLED = True
NTFY_URL = f"https://ntfy.sh/{NTFY_TOPIC}"

# ===== STORAGE =====
PROGRAMS_FILE = 'data/programs.json'
LOGS_DIR = 'data/logs/'
BACKUP_DIR = 'data/backups/'

# ===== WEB SERVER =====
FLASK_HOST = '0.0.0.0'
FLASK_PORT = 5000
FLASK_DEBUG = False  # ATTENZIONE: True espone debugger interattivo sulla rete

# ===== TIMING INTERVALS =====
SENSOR_UPDATE_INTERVAL = 2      # secondi - lettura sensore temperatura
TEMP_LOG_INTERVAL = 30          # secondi - logging durante esecuzione
SAFETY_CHECK_INTERVAL = 1       # secondi - controlli sicurezza

# ===== PROGRAM RUNNER (ciclo PID → valvola) =====
# IMPORTANTE: un forno ceramica a mattoni ha inerzia termica enorme.
# L'effetto di un cambio valvola si vede dopo 2-5 minuti.
# Aggiornare la valvola troppo spesso causa overshoot e usura meccanica.
# Il valore ottimale sarà affinato dopo l'autotuning (Pu/10 circa).
PID_CYCLE_INTERVAL = 30         # secondi - intervallo aggiornamento PID e valvola
PID_UPDATE_INTERVAL = 30        # alias per compatibilità

# Temperatura: smorzamento rumore sensore
TEMP_SMOOTHING_WINDOW = 5       # numero letture per media mobile (5 × 2s = 10s di media)

# Tolleranze per avanzamento fasi
RAMP_TOLERANCE = 10             # °C - target raggiunto se entro questa tolleranza
HOLD_TOLERANCE = 15             # °C - timer hold avanza solo se entro tolleranza

# ===== WATCHDOG =====
WATCHDOG_INTERVAL = 5           # secondi - controllo watchdog
WATCHDOG_SENSOR_TIMEOUT = 30    # secondi - tempo max senza lettura sensore valida
WATCHDOG_THREAD_TIMEOUT = 15    # secondi - tempo max senza heartbeat dal thread monitor

# ===== VALVOLA ELETTROMAGNETICA (predisposizione futura) =====
# Valvola normalmente chiusa: HIGH = aperta, LOW/nessuna alimentazione = chiusa
# Indipendente dalla valvola di precisione stepper
SOLENOID_VALVE_ENABLED = False      # Abilitare quando installata
SOLENOID_VALVE_PIN = 24             # GPIO pin (da configurare)
# La valvola elettromagnetica viene chiusa dal watchdog in caso di emergenza
# anche se lo stepper o il software principale non rispondono

# ===== TEMPERATURE HISTORY =====
TEMP_HISTORY_SIZE = 1000        # Numero letture da mantenere in memoria
COOLING_CALC_WINDOW = 600       # secondi (10min) per calcolo raffreddamento

# ===== SISTEMA =====
SYSTEM_NAME = "Forno Ceramica v3.2"
SYSTEM_VERSION = "3.2.0"
