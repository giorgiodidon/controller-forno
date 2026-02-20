# Forno Ceramica v3.0 - Architettura Modulare

Controller professionale per forno ceramica con architettura modulare Python.

## 📁 Struttura Progetto

```
forno_ceramica/
│
├── app.py                      # Flask app principale
├── config.py                   # Configurazione centralizzata
├── requirements.txt            # Dipendenze Python
│
├── hardware/                   # Moduli hardware I/O
│   ├── __init__.py
│   ├── sensors.py              # MCP9600 e altri sensori
│   └── actuators.py            # Stepper motor valvola gas
│
├── core/                       # Logica business
│   ├── __init__.py
│   ├── pid_controller.py       # Controller PID temperatura
│   ├── safety_monitor.py       # Controlli sicurezza
│   └── data_logger.py          # Logging esecuzioni
│
├── services/                   # Servizi esterni
│   ├── __init__.py
│   ├── notifications.py        # Notifiche push ntfy.sh
│   └── storage.py              # Gestione programmi JSON
│
├── utils/                      # Utilities
│   ├── __init__.py
│   └── calculations.py         # Calcoli temperature/tempi
│
├── templates/                  # Template HTML
│   └── index.html              # Interfaccia web
│
└── data/                       # Dati runtime (auto-creata)
    ├── programs.json           # Programmi salvati
    ├── logs/                   # Log esecuzioni
    └── backups/                # Backup programmi
```

---

## 🚀 Installazione

### 1. Clona Repository

```bash
cd /home/pi
git clone <your-repo> forno_ceramica
cd forno_ceramica
```

### 2. Installa Dipendenze

```bash
pip install -r requirements.txt --break-system-packages
```

### 3. Crea Directory Templates

```bash
mkdir -p templates
# Copia index.html in templates/
cp /path/to/index.html templates/
```

### 4. Configurazione

Modifica `config.py` per il tuo setup:

```python
# Pin GPIO
STEPPER_STEP_PIN = 17
STEPPER_DIR_PIN = 27
STEPPER_ENABLE_PIN = 22

# Calibrazione valvola (DA MISURARE)
VALVE_MAX_TURNS = 5  # Giri totali chiuso→aperto

# Notifiche
NTFY_TOPIC = "forno_giorgio"
```

### 5. Avvia Server

```bash
python3 app.py
```

Output:
```
============================================================
Forno Ceramica v3.0
============================================================
✅ GPIO configurato - Stepper su pin STEP:17 DIR:27
✅ ActuatorManager inizializzato
📁 File programmi caricato: data/programs.json
🔔 Notifiche abilitate: forno_giorgio
✅ Tutti i componenti inizializzati
============================================================
✅ Thread monitoraggio avviato
🌐 Server web: http://0.0.0.0:5000
============================================================
```

---

## 🎯 Architettura Modulare

### **Vantaggi**

✅ **Separazione responsabilità** - Ogni modulo ha uno scopo preciso  
✅ **Manutenibilità** - Modifiche isolate senza side effects  
✅ **Testabilità** - Mock hardware per test senza Raspberry  
✅ **Scalabilità** - Aggiungi sensori/attuatori facilmente  
✅ **Riusabilità** - Moduli riutilizzabili in altri progetti  

---

## 📦 Moduli Dettagliati

### **hardware/** - Interfaccia Hardware

#### **sensors.py**
- `MCP9600Sensor`: Lettura termocoppia I2C
- `SensorManager`: Gestione centralizzata sensori

```python
from hardware import SensorManager

sensors = SensorManager()
temp_data = sensors.get_temperature_data()
# {'hot': 650.5, 'cold': 25.2, 'status': 'connected'}
```

**Espandibile:**
```python
# Aggiungi in SensorManager.__init__()
self.pressure_sensor = PressureSensor()
self.oxygen_sensor = OxygenSensor()
```

---

#### **actuators.py**
- `StepperValveController`: Controllo valvola gas con A4988
- `ActuatorManager`: Coordinamento attuatori

```python
from hardware import ActuatorManager

actuators = ActuatorManager()
actuators.set_valve_position(50)  # 50% apertura
```

**Caratteristiche:**
- Full step (no microstepping)
- No endstops (limiti software)
- Thread-safe con lock
- Calibrazione manuale

---

### **core/** - Logica Business

#### **pid_controller.py**
Controller PID per regolazione temperatura

```python
from core import PIDController

pid = PIDController(kp=2.5, ki=0.03, kd=1.8)
output = pid.compute(setpoint=800, current_value=750)
# output = 65.3% (apertura valvola)
```

**Features:**
- Anti-windup integrale
- Reset automatico
- Tuning dinamico

---

#### **safety_monitor.py**
Controlli sicurezza critici

```python
from core import SafetyMonitor

safety = SafetyMonitor()
result = safety.check_all(temp_hot=1320, temp_cold=25)
# result = {'is_safe': False, 'alarms': [...], 'actions': ['emergency_shutdown']}
```

**Controlli:**
- Sovratemperatura (>1310°C)
- Rate riscaldamento troppo veloce
- Raffreddamento rapido (<700°C)
- Salute sensore

---

#### **data_logger.py**
Logging esecuzioni programmi

```python
from core import DataLogger

logger = DataLogger()
logger.start_logging("gres_1200")
logger.log_temperature(temp=650, setpoint=650, valve_position=45)
logger.log_event('ramp_complete', 'Rampa 2/5 completata')
filepath = logger.complete_logging()
# Salva: data/logs/execution_gres_1200_20260213_143022.json
```

---

### **services/** - Servizi Esterni

#### **notifications.py**
Notifiche push via ntfy.sh

```python
from services import NotificationService

notif = NotificationService()
notif.notify_program_start("gres_1200")
notif.notify_over_temp(1320)
```

**Notifiche predefinite:**
- Sistema avviato/fermato
- Programma avviato/completato
- Rampe/hold completate
- Allarmi temperatura
- Errori sensore

---

#### **storage.py**
Gestione programmi di cottura

```python
from services import StorageService

storage = StorageService()
storage.save_program(program_data)
programs = storage.load_programs()
storage.create_backup()
```

---

### **utils/** - Utilities

#### **calculations.py**
Funzioni calcolo

```python
from utils import calculate_cooling_rate, calculate_ramp_time, format_time

rate = calculate_cooling_rate(temp_history)
# -120.5 °C/h

time_min = calculate_ramp_time(start=20, target=800, rate=100)
# 468.0 minuti

formatted = format_time(468)
# "07:48"
```

---

## 🔧 Calibrazione Iniziale

### 1. Calibra Valvola

```bash
# Dal browser: http://raspberry-ip:5000
# Oppure via API:

curl -X POST http://localhost:5000/api/valve/calibrate \
  -H "Content-Type: application/json" \
  -d '{"manual_steps": 0}'
```

**Procedura:**
1. Chiudi manualmente valvola completamente
2. Chiama API calibrate
3. Posizione azzerata a 0%

### 2. Trova VALVE_MAX_TURNS

```bash
# Imposta posizione 100%
curl -X POST http://localhost:5000/api/valve/position \
  -H "Content-Type: application/json" \
  -d '{"position": 100}'
```

1. Conta giri fisici della valvola
2. Aggiorna `config.py`:
   ```python
   VALVE_MAX_TURNS = 7.5  # Esempio: 7.5 giri
   ```
3. Riavvia server

---

## 🌐 API Endpoints

### **Temperature**
```bash
GET  /api/temperatures          # Lettura temperature real-time
GET  /api/status                # Stato completo sistema
```

### **Programmi**
```bash
GET    /api/programs            # Lista programmi
POST   /api/programs            # Salva programma
GET    /api/programs/<name>     # Ottieni programma
DELETE /api/programs/<name>     # Elimina programma
```

### **Attuatori**
```bash
POST /api/valve/position        # Imposta posizione valvola
GET  /api/valve/status          # Stato valvola
POST /api/valve/calibrate       # Calibra valvola
```

### **PID**
```bash
GET  /api/pid/tunings           # Ottieni parametri PID
POST /api/pid/tunings           # Imposta parametri PID
```

### **Logging**
```bash
GET  /api/log/current           # Log corrente
POST /api/log/start             # Avvia logging
POST /api/log/stop              # Ferma logging
POST /api/log/temperature       # Logga temperatura
POST /api/log/event             # Logga evento
```

### **Sicurezza**
```bash
GET  /api/safety/status         # Stato sicurezza
POST /api/safety/reset          # Reset emergenza
POST /api/emergency/stop        # STOP EMERGENZA
```

### **Notifiche**
```bash
POST /api/notify                # Invia notifica custom
```

---

## 🧪 Test Moduli

### Test Sensore (senza Flask)

```python
from hardware.sensors import SensorManager

sensors = SensorManager()
data = sensors.read_all()
print(data)
```

### Test Valvola (senza Flask)

```python
from hardware.actuators import ActuatorManager

actuators = ActuatorManager()
actuators.calibrate_valve()
actuators.set_valve_position(25)  # 25% apertura
print(actuators.get_status())
actuators.cleanup()
```

### Test PID

```python
from core.pid_controller import PIDController

pid = PIDController()
for temp in range(20, 801, 10):
    output = pid.compute(setpoint=800, current_value=temp)
    print(f"Temp: {temp}°C → Output: {output:.1f}%")
```

---

## 📊 Flusso Tipico Esecuzione

```
1. Frontend carica programma
   ↓
2. POST /api/log/start {"program_name": "gres_1200"}
   ↓
3. Loop PID:
   - Leggi temperatura
   - Calcola output PID
   - Imposta valvola
   - POST /api/log/temperature
   - Check safety
   ↓
4. Eventi rampe:
   - POST /api/log/event {"type": "ramp_complete"}
   → Notifica ntfy automatica
   ↓
5. Fine programma:
   - POST /api/log/stop
   - Salva file JSON in data/logs/
   - Notifica completamento
```

---

## 🔒 Sicurezza

### Limiti Hardware
```python
MAX_TEMP = 1290        # °C
OVER_TEMP = 1310       # °C (emergenza)
MAX_RATE_UP = 400      # °C/h
MAX_RATE_DOWN = 300    # °C/h (sotto 700°C)
```

### Actions Automatiche
- **Sovratemperatura**: Chiusura valvola + notifica MAX priority
- **Sensore disconnesso**: Chiusura valvola + notifica HIGH
- **Rate troppo veloce**: Riduzione potenza + notifica WARNING

---

## 🚧 Espansioni Future

### Sensori Addizionali
```python
# In hardware/sensors.py
class PressureSensor:
    def read(self):
        # Leggi pressione gas
        pass

# In SensorManager.__init__()
self.pressure = PressureSensor()
```

### Attuatori Addizionali
```python
# In hardware/actuators.py
class IgnitionControl:
    def ignite(self):
        # Accendi pilota
        pass
    
    def extinguish(self):
        # Spegni pilota
        pass

# In ActuatorManager.__init__()
self.ignition = IgnitionControl()
```

### Database
Sostituisci `services/storage.py` con SQLite/PostgreSQL:
```python
class DatabaseStorage:
    def __init__(self):
        self.conn = sqlite3.connect('forno.db')
        # ...
```

---

## 📝 Changelog

### v3.0.0 (2026-02-13)
- ✅ Architettura modulare completa
- ✅ Separazione hardware/core/services
- ✅ PID controller implementato
- ✅ Safety monitor con allarmi
- ✅ Data logger per esecuzioni
- ✅ Notifiche push ntfy.sh
- ✅ Storage JSON programmi
- ✅ Controllo valvola stepper A4988
- ✅ Sensore MCP9600 I2C
- ✅ API REST complete

---

## 🐛 Troubleshooting

### Errore GPIO
```
RuntimeError: No access to /dev/mem
```
**Fix:** Aggiungi utente a gruppo gpio
```bash
sudo usermod -a -G gpio $USER
sudo reboot
```

### Errore I2C
```
FileNotFoundError: [Errno 2] No such file or directory: '/dev/i2c-1'
```
**Fix:** Abilita I2C
```bash
sudo raspi-config
# Interface Options → I2C → Enable
sudo reboot
```

### Notifiche non arrivano
```bash
# Test manuale
curl -d "Test forno" ntfy.sh/forno_giorgio

# Verifica app mobile iscritta al topic
```

---

## 📞 Supporto

**Log completo:**
```bash
python3 app.py 2>&1 | tee forno.log
```

**Debug modulo specifico:**
```python
# In config.py
FLASK_DEBUG = True
```

---

## 📄 License

MIT License - Uso personale e commerciale libero

---

**Sviluppato con ❤️ per la ceramica artigianale**
