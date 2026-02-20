# 🔄 Aggiornamento Sistema Pulegge - v3.0.1

## 📝 Modifiche Applicate

### ✅ Configurazione Hardware Definitiva

**Sistema trasmissione aggiornato:**
- Motore: NEMA17 1.8° (200 steps/giro)
- Puleggia motore: **20 denti**
- Puleggia valvola: **60 denti**
- Rapporto riduzione: **3:1**
- Apertura totale: **7 giri motore** = **1400 steps**

---

## 🔧 File Modificati

### **1. config.py**

**Prima:**
```python
VALVE_MAX_TURNS = 5  # DA CALIBRARE
VALVE_TOTAL_STEPS = 1000  # steps
```

**Dopo:**
```python
# Sistema pulegge
MOTOR_PULLEY_TEETH = 20
VALVE_PULLEY_TEETH = 60
GEAR_RATIO = 3.0  # 60/20

# Apertura valvola
MOTOR_TURNS_FULL_OPEN = 7
VALVE_TURNS_FULL_OPEN = 2.33  # 7/3
VALVE_TOTAL_STEPS = 1400  # 200 × 7
```

### **2. hardware/actuators.py**

**Aggiunte:**
- Documentazione sistema pulegge nell'header
- Calcolo `motor_turns` e `valve_turns` in `get_status()`
- Info rapporto riduzione in `calibrate()`

**Nuovo output status:**
```json
{
  "position_percent": 50.0,
  "position_steps": 700,
  "motor_turns": 3.5,      // ← NUOVO
  "valve_turns": 1.17,     // ← NUOVO
  "gear_ratio": 3.0        // ← NUOVO
}
```

---

## 📊 Calcoli Automatici

### **Rapporto Trasmissione**
```
Rapporto = 60 denti / 20 denti = 3:1

Effetto:
- 1 giro motore → 1/3 giro valvola (120°)
- 3 giri motore → 1 giro valvola (360°)
- 7 giri motore → 2.33 giri valvola (840°)
```

### **Steps Sistema**
```
Steps per 1% apertura = 1400 / 100 = 14 steps
Steps per 10% apertura = 140 steps
Steps per 50% apertura = 700 steps
```

### **Risoluzione Finale**
```
1 step motore = 1.8° motore
              = 0.6° valvola
              = 0.0714% apertura

Precisione: ±0.07% (eccellente!)
```

---

## 🎯 Vantaggi Sistema 3:1

### **Coppia**
- Coppia valvola = Coppia motore × 3
- Può gestire valvole più dure/grandi

### **Precisione**
- Risoluzione valvola: 0.6° invece di 1.8°
- Controllo più fine del flusso gas

### **Stabilità**
- Movimento più fluido
- Meno vibrazioni
- Holding torque aumentato

---

## 🚀 Come Aggiornare

### **1. Aggiorna File**

```bash
cd /home/pi/forno_ceramica

# Backup vecchi file
cp config.py config.py.old
cp hardware/actuators.py hardware/actuators.py.old

# Sostituisci con nuovi file dall'archivio
```

### **2. Verifica Configurazione**

```bash
# Apri config.py
nano config.py

# Verifica valori:
MOTOR_PULLEY_TEETH = 20
VALVE_PULLEY_TEETH = 60
MOTOR_TURNS_FULL_OPEN = 7
VALVE_TOTAL_STEPS = 1400
```

### **3. Riavvia Sistema**

```bash
# Ferma server se attivo
# CTRL+C oppure:
sudo systemctl stop forno

# Avvia con nuova config
python3 app.py
```

Output atteso:
```
============================================================
Sistema: Pulegge 20:60 denti (rapporto 3:1)
Range: 0 → 1400 steps (7 giri motore)
✅ Calibrazione completata
Apertura totale richiede: 7 giri motore
============================================================
```

---

## 🧪 Test Sistema

### **Test 1: Calibrazione**

```bash
# 1. Chiudi manualmente valvola
# 2. Calibra
curl -X POST http://localhost:5000/api/valve/calibrate \
  -d '{"manual_steps": 0}'

# Output:
# 🏠 Calibrazione valvola...
# Sistema: Pulegge 20:60 denti (rapporto 3:1)
# Range: 0 → 1400 steps (7 giri motore)
# ✅ Calibrazione completata
```

### **Test 2: Apertura Parziale**

```bash
# Apri 25%
curl -X POST http://localhost:5000/api/valve/position \
  -H "Content-Type: application/json" \
  -d '{"position": 25}'

# Verifica
curl http://localhost:5000/api/valve/status
```

Response attesa:
```json
{
  "position_percent": 25.0,
  "position_steps": 350,
  "motor_turns": 1.75,     // 350/200
  "valve_turns": 0.58,     // 1.75/3
  "gear_ratio": 3.0
}
```

**Verifica fisica:**
- Motore deve aver fatto ~1.75 giri
- Valvola deve essere ruotata ~210°

### **Test 3: Apertura Completa**

```bash
curl -X POST http://localhost:5000/api/valve/position \
  -d '{"position": 100}'
```

**Verifica fisica:**
- Motore fa 7 giri completi
- Valvola completamente aperta

---

## 📋 Tabella Riferimento Veloce

| Apertura | Steps | Giri Motore | Giri Valvola | Verifica Fisica |
|----------|-------|-------------|--------------|-----------------|
| 0%       | 0     | 0           | 0            | Chiusa          |
| 25%      | 350   | 1.75        | 0.58         | ~1/4 aperta     |
| 50%      | 700   | 3.5         | 1.17         | Metà aperta     |
| 75%      | 1050  | 5.25        | 1.75         | ~3/4 aperta     |
| 100%     | 1400  | 7.0         | 2.33         | Tutta aperta    |

---

## 🔍 Troubleshooting

### Problema: Posizione non corrisponde

**Causa:** Steps persi durante movimento

**Fix:**
```python
# In config.py - aumenta delay (più coppia, più lento)
STEPPER_SPEED_NORMAL = 0.002  # era 0.001
```

### Problema: Motore salta steps

**Cause possibili:**
1. Cinghia troppo lenta
2. Velocità troppo alta
3. Alimentazione insufficiente

**Fix:**
1. Aumenta tensione cinghia
2. Aumenta delay step
3. Verifica alimentazione motore (≥12V)

### Problema: Apertura non completa a 100%

**Fix:**
```python
# Verifica/correggi numero giri in config.py
MOTOR_TURNS_FULL_OPEN = 7  # Conta fisicamente i giri!
```

---

## 📐 Documentazione Tecnica

Vedi file **`PULLEY_SYSTEM.md`** per:
- Calcoli dettagliati sistema
- Formule di conversione
- Visualizzazione meccanica
- Manutenzione preventiva
- Troubleshooting avanzato

---

## ✅ Checklist Post-Aggiornamento

- [ ] File `config.py` aggiornato
- [ ] File `hardware/actuators.py` aggiornato
- [ ] Server riavviato
- [ ] Calibrazione eseguita
- [ ] Test 25% apertura OK
- [ ] Test 50% apertura OK
- [ ] Test 100% apertura OK
- [ ] Ripetibilità verificata (10 cicli)
- [ ] API `/api/valve/status` mostra `gear_ratio: 3.0`

---

## 🎯 Benefici Aggiornamento

✅ **Precisione aumentata** - 0.6° invece di 1.8° sulla valvola  
✅ **Coppia triplicata** - Valvole più dure gestite facilmente  
✅ **Controllo migliore** - 1400 steps vs 1000 steps  
✅ **Info dettagliate** - Giri motore e valvola separati  
✅ **Documentazione completa** - Calcoli verificabili  

---

**Versione:** v3.0.1  
**Data:** 2026-02-14  
**Compatibilità:** Retrocompatibile con interfaccia web esistente
