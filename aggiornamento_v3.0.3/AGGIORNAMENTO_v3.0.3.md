# 🔄 AGGIORNAMENTO v3.0.3 - PID Autotuning

**Data:** 2026-02-18  
**Da versione:** v3.0.2  
**A versione:** v3.0.3  

---

## 📦 CONTENUTO AGGIORNAMENTO

### **Novità Principali:**
✅ PID Autotuning con metodo Relay Feedback  
✅ Interfaccia web dedicata `/autotuning`  
✅ Grafico oscillazioni real-time  
✅ Calcolo automatico parametri Ziegler-Nichols  
✅ Test a 500°C fisso  
✅ Salvataggio risultati JSON  

---

## 📁 NUOVI FILE

### **1. Backend - Modulo Autotuning**
```
core/autotuner.py
```
**Cosa fa:**
- Relay feedback automatico
- Rilevamento oscillazioni e picchi
- Calcolo Ku, Pu con Ziegler-Nichols
- Generazione PID ottimizzati (conservativi)
- Logging completo in JSON

**Dimensione:** ~450 righe  
**Dipendenze:** Nessuna nuova (usa librerie standard)

---

### **2. Frontend - Interfaccia Autotuning**
```
templates/autotuning.html
```
**Cosa fa:**
- Pagina web dedicata autotuning
- Controlli test (avvia/ferma)
- Grafico oscillazioni Chart.js
- Display risultati PID
- Applicazione parametri

**URL accesso:** `http://raspberry-ip:5000/autotuning`  
**Stile:** Identico a index.html (dark theme mobile-first)

---

### **3. Documentazione Completa**
```
AUTOTUNING_DOCS.md
```
**Contenuto:**
- Teoria Relay Feedback vs Z-N classico
- Procedura uso step-by-step
- Interpretazione risultati
- Configurazione parametri
- Troubleshooting
- Roadmap Fase 2-3-4 (adattativo + ML)

---

## 🔧 FILE DA MODIFICARE

### **1. app.py**
**File patch:** `patches/app.py.patch`

**Modifiche da applicare:**

#### **Modifica 1 - Import (riga ~17)**
Dopo:
```python
from core import PIDController, SafetyMonitor, DataLogger
```
Aggiungere:
```python
from core.autotuner import RelayAutotuner
```

#### **Modifica 2 - Inizializzazione (riga ~35)**
Dopo:
```python
logger = DataLogger()
```
Aggiungere:
```python
autotuner = RelayAutotuner(test_temperature=500)
```

#### **Modifica 3 - Routes Autotuning (riga ~250 circa)**
Aggiungere **prima** della sezione `# ===== CLEANUP =====`:
```python
# ===== ROUTES AUTOTUNING =====

@app.route('/autotuning')
def autotuning_page():
    """Pagina autotuning PID"""
    return render_template('autotuning.html')

@app.route('/api/autotuning/start', methods=['POST'])
def start_autotuning():
    # ... (vedi patch completo)

@app.route('/api/autotuning/stop', methods=['POST'])
def stop_autotuning():
    # ... (vedi patch completo)

@app.route('/api/autotuning/status')
def get_autotuning_status():
    # ... (vedi patch completo)

@app.route('/api/autotuning/results')
def get_autotuning_results():
    # ... (vedi patch completo)

@app.route('/api/autotuning/chart_data')
def get_autotuning_chart_data():
    # ... (vedi patch completo)

@app.route('/api/pid/apply', methods=['POST'])
def apply_pid():
    # ... (vedi patch completo)
```

**Totale:** 7 nuove routes API

#### **Modifica 4 - Thread Monitoraggio (dentro temperature_monitor_thread)**
Dopo:
```python
safety_result = safety.check_all(...)
```
Aggiungere:
```python
# Controllo autotuning
if autotuner.is_running:
    valve_pos = autotuner.compute_valve_position(temperature_data['hot'])
    if valve_pos is not None:
        actuators.set_valve_position(valve_pos)
```

---

### **2. core/__init__.py**
**File patch:** `patches/core__init__.py.patch`

**Sostituire contenuto con:**
```python
from .pid_controller import PIDController
from .safety_monitor import SafetyMonitor
from .data_logger import DataLogger
from .autotuner import RelayAutotuner

__all__ = ['PIDController', 'SafetyMonitor', 'DataLogger', 'RelayAutotuner']
```

---

## 🚀 PROCEDURA INSTALLAZIONE

### **Step 1: Backup**
```bash
cd /home/giorgio/kiln

# Backup file correnti
cp app.py app.py.backup_v3.0.2
cp core/__init__.py core/__init__.py.backup_v3.0.2
```

### **Step 2: Copia Nuovi File**
```bash
# Copia autotuner.py
cp /path/to/core/autotuner.py core/

# Copia autotuning.html
cp /path/to/templates/autotuning.html templates/

# Copia documentazione
cp /path/to/AUTOTUNING_DOCS.md .
```

### **Step 3: Applica Patch app.py**

**Metodo Manuale (consigliato):**
```bash
nano app.py
```

Segui istruzioni in `patches/app.py.patch`:
1. Import RelayAutotuner
2. Inizializza autotuner
3. Aggiungi 7 routes
4. Aggiungi hook in temperature_monitor_thread

**Oppure Copia-Incolla:**
Apri `patches/app.py.patch` e copia le sezioni nei punti indicati.

### **Step 4: Applica Patch core/__init__.py**
```bash
nano core/__init__.py
```

Sostituisci contenuto con quello in `patches/core__init__.py.patch`

### **Step 5: Verifica File**
```bash
# Check file esistono
ls -l core/autotuner.py
ls -l templates/autotuning.html

# Check sintassi Python
python3 -m py_compile app.py
python3 -m py_compile core/autotuner.py
```

### **Step 6: Riavvia Sistema**
```bash
python3 app.py
```

**Output atteso:**
```
============================================================
Forno Ceramica v3.0
============================================================
...
✅ Autotuner inizializzato
...
✅ Tutti i componenti inizializzati
============================================================
```

### **Step 7: Test Accessibilità**
```bash
# Test pagina autotuning
curl http://localhost:5000/autotuning

# Test API status
curl http://localhost:5000/api/autotuning/status
```

---

## ✅ CHECKLIST POST-INSTALLAZIONE

- [ ] File `core/autotuner.py` presente
- [ ] File `templates/autotuning.html` presente
- [ ] File `AUTOTUNING_DOCS.md` presente
- [ ] `app.py` modificato (4 punti)
- [ ] `core/__init__.py` modificato
- [ ] Backup v3.0.2 creati
- [ ] Server avvia senza errori
- [ ] Pagina `/autotuning` accessibile
- [ ] API `/api/autotuning/status` risponde
- [ ] Import `calculate_program_times` NON presente

---

## 🧪 TEST FUNZIONALITÀ

### **Test 1: Interfaccia**
```bash
# Apri browser
http://localhost:5000/autotuning

# Verifica:
✓ Pagina carica
✓ Display temperatura visibile
✓ Pulsante "Avvia Autotuning" presente
✓ Stile identico a index.html
```

### **Test 2: API Backend**
```bash
# Status autotuner
curl http://localhost:5000/api/autotuning/status

# Response attesa:
{
  "running": false,
  "phase": "idle",
  "test_temperature": 500,
  "oscillations": 0,
  ...
}
```

### **Test 3: Avvio Test (opzionale)**
```bash
# SOLO se hardware pronto e forno sicuro
# Avvia via interfaccia web
# Osserva log server per conferma
```

---

## 📊 NUOVE API DISPONIBILI

| Endpoint | Metodo | Descrizione |
|----------|--------|-------------|
| `/autotuning` | GET | Pagina HTML autotuning |
| `/api/autotuning/start` | POST | Avvia test (body: {temperature: 500}) |
| `/api/autotuning/stop` | POST | Ferma test |
| `/api/autotuning/status` | GET | Stato corrente test |
| `/api/autotuning/results` | GET | Risultati finali PID |
| `/api/autotuning/chart_data` | GET | Dati grafico oscillazioni |
| `/api/pid/apply` | POST | Applica PID (body: {Kp, Ki, Kd}) |

---

## 🔮 PROSSIMI AGGIORNAMENTI

### **v3.0.4 - Fase 2 (Dopo Prime Cotture):**
- Logger performance PID durante cotture
- Analisi errore, overshoot, settling time
- Aggiustamento manuale parametri basato su dati

### **v3.1.0 - Fase 3 (PID Adattativo):**
- Multi-temperature autotuning (300°C, 600°C, 900°C)
- Gain scheduling automatico
- Interpolazione parametri

### **v3.2.0 - Fase 4 (Machine Learning):**
- Dataset storico cotture
- Training modello predittivo
- PID ottimizzato real-time

---

## 📝 CHANGELOG v3.0.3

### **Aggiunte:**
- ✅ Modulo `core/autotuner.py` - Relay feedback autotuning
- ✅ Template `templates/autotuning.html` - UI dedicata
- ✅ 7 nuove API routes per autotuning
- ✅ Integrazione autotuner in temperature monitor
- ✅ Notifiche ntfy per eventi autotuning
- ✅ Salvataggio risultati JSON in `data/logs/`
- ✅ Documentazione completa `AUTOTUNING_DOCS.md`

### **Modifiche:**
- 🔧 `app.py` - Aggiunti import, routes, hook monitor
- 🔧 `core/__init__.py` - Export RelayAutotuner

### **Fix:**
- ✅ Nessun breaking change
- ✅ Retrocompatibile con v3.0.2
- ✅ Tutte le funzionalità esistenti invariate

---

## 🚨 NOTE IMPORTANTI

### **Compatibilità:**
- ✅ **Retrocompatibile** con programmi salvati
- ✅ **Nessun cambio** a interfaccia cotture (`index.html`)
- ✅ **PID esistente** continua a funzionare
- ✅ **Autotuning opzionale** - non interferisce se non usato

### **Sicurezza:**
- ⚠️ Test autotuning porta forno a **500°C**
- ⚠️ **Non lasciare incustodito** durante test
- ⚠️ **Forno vuoto** durante autotuning
- ✅ Safety monitor sempre attivo
- ✅ Timeout automatico 1 ora
- ✅ Stop manuale sempre disponibile

### **Requisiti:**
- Sensore MCP9600 funzionante
- Motore stepper calibrato
- Sistema già operativo v3.0.2

---

## 📞 SUPPORTO

### **Problemi Installazione:**
1. Verifica file copiati correttamente
2. Check sintassi Python: `python3 -m py_compile app.py`
3. Leggi errori startup: `python3 app.py 2>&1 | tee autotuning_install.log`

### **Problemi Runtime:**
1. Check log server
2. Verifica API status: `curl localhost:5000/api/autotuning/status`
3. Consulta `AUTOTUNING_DOCS.md` sezione Troubleshooting

### **Domande Tecniche:**
- Leggi `AUTOTUNING_DOCS.md` completo
- Teoria: Sezione "Come Funziona"
- Configurazione: Sezione "Parametri Test"

---

## 📦 STRUTTURA FILE AGGIORNAMENTO

```
aggiornamento_v3.0.3/
├── core/
│   └── autotuner.py          ← NUOVO
│
├── templates/
│   └── autotuning.html       ← NUOVO
│
├── patches/
│   ├── app.py.patch          ← MODIFICHE app.py
│   └── core__init__.py.patch ← MODIFICHE core/__init__.py
│
├── AGGIORNAMENTO_v3.0.3.md   ← QUESTO FILE
└── AUTOTUNING_DOCS.md        ← DOCUMENTAZIONE
```

---

## ✅ RIEPILOGO

**File nuovi:** 2 (autotuner.py, autotuning.html)  
**File modificati:** 2 (app.py, core/__init__.py)  
**Routes aggiunte:** 7 API endpoints  
**Breaking changes:** Nessuno  
**Tempo installazione:** ~10 minuti  
**Compatibilità:** v3.0.2 → v3.0.3  

---

## 🎯 QUICK START

```bash
# 1. Backup
cp app.py app.py.backup

# 2. Copia nuovi file
cp autotuner.py core/
cp autotuning.html templates/

# 3. Modifica app.py (segui patches/app.py.patch)
nano app.py

# 4. Modifica core/__init__.py
nano core/__init__.py

# 5. Riavvia
python3 app.py

# 6. Testa
http://localhost:5000/autotuning
```

---

**Aggiornamento pronto per l'installazione!** 🚀

Per domande o problemi, consulta `AUTOTUNING_DOCS.md` o i file patch.
