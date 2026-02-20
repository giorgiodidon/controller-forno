# 🎯 PID Autotuning - Documentazione Completa

## 📋 File Creati

### **1. `core/autotuner.py`**
Modulo principale autotuning con:
- ✅ Relay feedback (Åström-Hägglund)
- ✅ Rilevamento oscillazioni automatico
- ✅ Calcolo Ziegler-Nichols
- ✅ Salvataggio risultati JSON

### **2. `templates/autotuning.html`**
Interfaccia web dedicata con:
- ✅ Controlli test (avvia/ferma)
- ✅ Grafico oscillazioni real-time
- ✅ Display risultati PID
- ✅ Applicazione parametri

### **3. `AUTOTUNING_INTEGRATION.txt`**
Modifiche da applicare a `app.py`

---

## 🔬 Metodo: Relay Feedback

### **Perché Relay Feedback invece di Z-N Classico?**

**Ziegler-Nichols Classico:**
- ❌ Richiede portare sistema a oscillazione instabile
- ❌ Pericoloso per forni (temperature fuori controllo)
- ❌ Richiede intervento manuale (aumentare Kp gradualmente)

**Relay Feedback (Åström-Hägglund):**
- ✅ Oscillazioni controllate e sicure
- ✅ Completamente automatico
- ✅ Identifica Ku e Pu automaticamente
- ✅ Adatto a sistemi con inerzia termica (forni)

---

## 📊 Come Funziona

### **Fase 1: Riscaldamento**
```
Obiettivo: Portare forno a 500°C
Controllo: PID normale o manuale
Durata: ~15-20 minuti
```

### **Fase 2: Relay Feedback**
```
Logica:
  Se temp < 495°C (setpoint - isteresi):
    valvola = 25% (relay_high)
  
  Se temp > 505°C (setpoint + isteresi):
    valvola = 0% (relay_low)
  
  Altrimenti:
    mantieni stato precedente

Risultato: Sistema oscilla naturalmente
```

### **Fase 3: Raccolta Dati**
Il sistema rileva automaticamente:
- **Crossings:** Quando temp attraversa 500°C (↗️ up, ↘️ down)
- **Picchi:** Massimi e minimi oscillazione (🔺 max, 🔻 min)
- **Periodi:** Tempo tra crossings consecutivi

### **Fase 4: Calcolo PID**
```python
# 1. Periodo critico (media periodi)
Pu = media([T1, T2, T3, ...])

# 2. Ampiezza oscillazione
a = (media_picchi_max - media_picchi_min) / 2

# 3. Guadagno critico
Ku = (4 * d) / (π * a)
dove d = relay_high - relay_low = 25%

# 4. Formule Ziegler-Nichols CONSERVATIVE
Kp = 0.45 * Ku
Ki = 0.54 * Ku / Pu
Kd = 0  (per stabilità forno)
```

---

## 🚀 Procedura Uso

### **Step 1: Preparazione**
1. Forno vuoto e freddo
2. Valvola gas calibrata
3. Sensore MCP9600 funzionante
4. Sistema in idle

### **Step 2: Avvia Test**
```
1. Apri http://raspberry-ip:5000/autotuning
2. Clicca "▶️ Avvia Autotuning"
3. Conferma warning 500°C
```

### **Step 3: Monitoraggio** (15-30 min)
- 🔥 **Riscaldamento:** Display "Riscaldamento a 500°C..."
- 📈 **Test Relay:** Grafico mostra oscillazioni
- 📊 **Progress bar:** Indica oscillazioni completate (0/3 → 3/3)

### **Step 4: Risultati**
Quando completo, mostra:
```
Parametri Misurati:
- Ku: 2.450 (guadagno critico)
- Pu: 180.5 s (periodo critico)
- Ampiezza: 12.3°C

PID Consigliati:
- Kp: 1.1025
- Ki: 0.006621
- Kd: 0.0000
```

### **Step 5: Applicazione**
```
1. Clicca "✓ Applica PID al Sistema"
2. Conferma applicazione
3. PID attivo per prossime cotture
```

---

## 📈 Grafico Real-Time

### **Cosa Mostra:**
- **Linea rossa:** Temperatura forno (aggiornata ogni 2s)
- **Linea tratteggiata azzurra:** Setpoint 500°C
- **Punti verdi:** Crossings del setpoint
- **Triangoli arancioni:** Picchi max/min

### **Cosa Osservare:**
```
Oscillazione corretta:
     /\      /\      /\
    /  \    /  \    /  \
---/----\--/----\--/----\---  500°C
        \/      \/      \/

Ampiezza: ~10-20°C
Periodo: ~150-300s
Simmetria: Picchi equidistanti
```

---

## 💾 Salvataggio Risultati

### **File Generato:**
```
data/logs/autotuning_500C_20260218_143022.json
```

### **Contenuto:**
```json
{
  "test_info": {
    "date": "2026-02-18T14:30:22",
    "temperature": 500,
    "duration_minutes": 28.5,
    "oscillations": 3
  },
  "measurements": {
    "Ku": 2.45,
    "Pu": 180.5,
    "amplitude": 12.3
  },
  "pid_conservative": {
    "Kp": 1.1025,
    "Ki": 0.006621,
    "Kd": 0
  },
  "raw_data": {
    "crossings": [...],
    "peaks": [...]
  }
}
```

---

## 🎯 Parametri Test

### **Configurabili in `core/autotuner.py`:**

```python
# Temperatura test
test_temperature = 500  # °C

# Relay
relay_high = 25  # % apertura valvola
relay_low = 0    # % apertura valvola

# Isteresi
hysteresis = 5  # °C (±5°C)

# Criterio completamento
min_oscillations = 3  # Numero cicli richiesti

# Timeout sicurezza
max_duration = 3600  # secondi (1 ora)
```

---

## ⚙️ Integrazione con Sistema

### **Modifiche Necessarie:**

Seguire istruzioni in `AUTOTUNING_INTEGRATION.txt`:

1. ✅ Import `RelayAutotuner`
2. ✅ Inizializza `autotuner = RelayAutotuner()`
3. ✅ Aggiungi routes API
4. ✅ Integra in `temperature_monitor_thread()`

### **Compatibilità:**
- ✅ Non interferisce con cotture normali
- ✅ PID controller esistente compatibile
- ✅ Notifiche ntfy integrate
- ✅ Safety monitor attivo

---

## 🧪 Test Validazione

### **Prima di Usare su Pezzi Reali:**

**Test 1: Verifica Hardware**
```bash
# Check temperature sensor
curl http://localhost:5000/api/temperatures

# Check valve control
curl -X POST http://localhost:5000/api/valve/position \
  -d '{"position": 25}' -H "Content-Type: application/json"
```

**Test 2: Simulazione (opzionale)**
Modificare temporaneamente `test_temperature = 100` per test rapido

**Test 3: Autotuning Reale**
```
1. Test a 500°C (medio)
2. Verifica oscillazioni stabili
3. Applica PID
4. Test cottura semplice (bisquit 900°C)
5. Valuta performance
```

---

## 📊 Interpretazione Risultati

### **Ku (Guadagno Critico)**
```
Alto (>3.0): Sistema reattivo, può essere instabile
Medio (1.5-3.0): Bilanciato, ottimale
Basso (<1.5): Sistema lento, poco reattivo
```

### **Pu (Periodo Critico)**
```
Lungo (>300s): Sistema inerziale (normale per forno)
Medio (150-300s): Tipico forno ceramica
Breve (<150s): Sistema veloce (inusuale)
```

### **PID Consigliati**
```
Conservativi (0.45 * Ku):
✅ Più stabili
✅ Meno overshoot
✅ Consigliati per forni

Standard (0.6 * Ku):
⚠️ Più reattivi
⚠️ Possibile overshoot
⚠️ Solo se sistema molto stabile
```

---

## 🔮 Prossimi Step (Fase 2)

### **Dopo Prime Cotture:**

1. **Logging Dati Cottura**
   ```python
   # Durante esecuzione programma
   - Temperatura reale vs setpoint
   - Errore PID nel tempo
   - Overshoot/undershoot
   - Tempo settling
   ```

2. **Analisi Performance**
   ```
   Metriche:
   - Errore medio assoluto (MAE)
   - Overshoot massimo
   - Tempo raggiungimento target
   - Stabilità mantenimento
   ```

3. **Aggiustamento PID**
   ```python
   # Basato su dati reali
   if overshoot_troppo_alto:
       Kp *= 0.8  # Riduci proporzionale
   
   if settling_troppo_lento:
       Ki *= 1.2  # Aumenta integrale
   ```

4. **PID Adattativo** (Fase 3)
   ```python
   # Multi-setpoint
   PID_300C = {Kp: 1.2, Ki: 0.008, Kd: 0}
   PID_600C = {Kp: 1.0, Ki: 0.006, Kd: 0}
   PID_900C = {Kp: 0.8, Ki: 0.005, Kd: 0}
   
   # Interpolazione lineare tra setpoint
   ```

5. **Machine Learning** (Fase 4)
   ```python
   # Train su dati storici
   - Input: temp_attuale, setpoint, rate_richiesto
   - Output: pid_parameters_ottimali
   - Modello: Regression tree / Neural network
   ```

---

## 🚨 Sicurezza

### **Controlli Automatici:**
- ✅ Timeout 1 ora (test interrotto automaticamente)
- ✅ Safety monitor sempre attivo
- ✅ Temperatura max 1310°C (allarme)
- ✅ Valvola chiusa automaticamente se errore

### **Responsabilità Utente:**
- ⚠️ **NON lasciare incustodito** durante test
- ⚠️ **Monitorare** grafico oscillazioni
- ⚠️ **Stop manuale** se anomalie
- ⚠️ **Forno vuoto** durante autotuning

---

## 📞 Troubleshooting

### **Problema: Oscillazioni troppo ampie (>30°C)**
```
Soluzione: Ridurre relay_high
relay_high = 20  # invece di 25
```

### **Problema: Oscillazioni troppo piccole (<5°C)**
```
Soluzione: Aumentare relay_high o ridurre hysteresis
relay_high = 30
hysteresis = 3
```

### **Problema: Non raggiunge mai 3 oscillazioni**
```
Cause:
1. Isteresi troppo grande
2. Sistema troppo lento
3. Perdite calore eccessive

Soluzione: Aumentare max_duration o ridurre min_oscillations
```

### **Problema: PID calcolato instabile nelle cotture**
```
Soluzione: Usa PID conservativi (già default)
O riduci manualmente:
Kp = Kp_consigliato * 0.8
Ki = Ki_consigliato * 0.8
```

---

## ✅ Checklist Installazione

- [ ] File `core/autotuner.py` creato
- [ ] File `templates/autotuning.html` creato
- [ ] Modifiche `app.py` applicate (vedi AUTOTUNING_INTEGRATION.txt)
- [ ] Server riavviato
- [ ] Pagina `/autotuning` accessibile
- [ ] Test hardware verificato
- [ ] Primo test autotuning eseguito
- [ ] PID applicato al sistema
- [ ] Test cottura semplice OK

---

**Sistema pronto per autotuning PID professionale!** 🎯
