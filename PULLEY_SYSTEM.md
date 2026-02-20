# Sistema Trasmissione Pulegge - Specifiche Tecniche

## 🔧 Configurazione Hardware

### **Motore Stepper**
- **Modello:** NEMA17
- **Angolo step:** 1.8°
- **Steps per giro:** 200 steps/rivoluzione
- **Driver:** A4988
- **Modalità:** Full step (no microstepping)

### **Sistema Pulegge**
```
Motore [20 denti] ──┐
                    │ Cinghia
Valvola [60 denti] ──┘
```

- **Puleggia motore:** 20 denti
- **Puleggia valvola:** 60 denti
- **Rapporto riduzione:** 3:1 (riduttore)

---

## 📐 Calcoli Sistema

### **Rapporto di Trasmissione**

```
Rapporto = Denti_Valvola / Denti_Motore
         = 60 / 20
         = 3:1
```

**Significato:**
- 1 giro motore → 1/3 giro valvola (120° valvola)
- 3 giri motore → 1 giro valvola (360° valvola)

### **Apertura Completa Valvola**

**Dati misurati:**
- Giri motore per apertura totale: **7 giri**

**Calcoli:**
```
Giri valvola = Giri_motore / Rapporto
             = 7 / 3
             = 2.33 giri valvola
             = 840° rotazione valvola
```

**Steps totali motore:**
```
Steps totali = Steps_per_giro × Giri_motore
             = 200 × 7
             = 1400 steps
```

---

## 🎯 Risoluzione Sistema

### **Risoluzione Motore**
```
1 step motore = 1.8° motore
              = 0.6° valvola  (1.8° / 3)
              = 0.0714% apertura
```

### **Risoluzione Controllo**
Con 1400 steps totali:
```
1% apertura = 14 steps motore
            = 4.67 steps valvola (teorici)
```

**Precisione posizionamento:** ±0.07% (ottima!)

---

## 📊 Tabella Conversioni

| Apertura % | Steps Motore | Giri Motore | Giri Valvola | Gradi Valvola |
|------------|--------------|-------------|--------------|---------------|
| 0%         | 0            | 0           | 0            | 0°            |
| 10%        | 140          | 0.70        | 0.23         | 84°           |
| 25%        | 350          | 1.75        | 0.58         | 210°          |
| 50%        | 700          | 3.50        | 1.17         | 420°          |
| 75%        | 1050         | 5.25        | 1.75         | 630°          |
| 100%       | 1400         | 7.00        | 2.33         | 840°          |

---

## ⚙️ Vantaggi Riduzione 3:1

### **✅ Pro**
1. **Coppia triplicata** - Motore può aprire valvole più dure
2. **Precisione aumentata** - 0.6° invece di 1.8° sulla valvola
3. **Stabilità** - Meno vibrazioni, movimento più fluido
4. **Holding torque** - Valvola resta in posizione senza corrente

### **⚠️ Contro**
1. **Velocità ridotta** - 3x più lenta (non critico per forno)
2. **Ingombro** - Sistema pulegge + cinghia

---

## 🔍 Verifiche Pratiche

### **Test Calibrazione**

1. **Chiudi manualmente** valvola completamente
2. **Calibra** sistema (azzera contatore)
3. **Comanda apertura 100%** (1400 steps)
4. **Verifica** valvola completamente aperta

### **Test Precisione**

```python
# Test posizioni intermedie
actuators.set_valve_position(25)   # 350 steps
actuators.set_valve_position(50)   # 700 steps
actuators.set_valve_position(75)   # 1050 steps

# Verifica stato
status = actuators.get_status()
print(f"Giri motore: {status['motor_turns']}")
print(f"Giri valvola: {status['valve_turns']}")
```

### **Test Ripetibilità**

```python
# Ciclo apri/chiudi 10 volte
for i in range(10):
    actuators.set_valve_position(100)  # Apri
    time.sleep(2)
    actuators.set_valve_position(0)    # Chiudi
    time.sleep(2)

# Verifica posizione finale = 0 steps
```

---

## 📈 Velocità Operativa

### **Tempo Apertura Completa**

Con delay step di **0.001s** (1ms):

```
Tempo totale = Steps × (delay × 2)
             = 1400 × 0.002
             = 2.8 secondi
```

Con delay step di **0.002s** (2ms, più coppia):

```
Tempo totale = 1400 × 0.004
             = 5.6 secondi
```

**Ottimale per forno:** 5-6 secondi (coppia elevata, nessuna fretta)

---

## 🛠️ Configurazione in config.py

```python
# ===== STEPPER CONFIGURATION =====
STEPS_PER_REVOLUTION = 200  # NEMA17 1.8°

# Sistema pulegge
MOTOR_PULLEY_TEETH = 20     # Denti puleggia motore
VALVE_PULLEY_TEETH = 60     # Denti puleggia valvola
GEAR_RATIO = 3.0            # 60/20 = 3:1

# Apertura valvola
MOTOR_TURNS_FULL_OPEN = 7   # Misurato fisicamente
VALVE_TURNS_FULL_OPEN = 2.33  # 7/3

# Steps totali
VALVE_TOTAL_STEPS = 1400    # 200 × 7
```

---

## 🎨 Visualizzazione Sistema

```
┌──────────────┐
│ NEMA17       │
│ 200 steps    │◄── Driver A4988
│              │
└──────┬───────┘
       │ Albero motore
       ▼
  ╔═══════╗  20 denti
  ║ ●●●●● ║◄────── Puleggia motore
  ╚═══╤═══╝
      │
      │ Cinghia dentata
      │
  ╔═══▼═══╗  60 denti
  ║ ●●●●● ║◄────── Puleggia valvola
  ╚═══╤═══╝
      │
      ▼
┌──────────────┐
│ VALVOLA GAS  │
│ 2.33 giri    │◄── Apertura totale
│ 0% → 100%    │
└──────────────┘
```

---

## 📊 API Response con Info Pulegge

```json
GET /api/valve/status

{
  "position_percent": 50.0,
  "position_steps": 700,
  "target_percent": 50.0,
  "total_steps": 1400,
  "motor_turns": 3.5,      // ← Giri motore
  "valve_turns": 1.17,     // ← Giri valvola (3.5/3)
  "gear_ratio": 3.0,       // ← Rapporto riduzione
  "enabled": true
}
```

---

## 🔧 Manutenzione

### **Controlli Periodici**

- ✅ **Tensione cinghia** - Deve essere tesa ma non eccessivamente
- ✅ **Allineamento pulegge** - Devono essere perfettamente allineate
- ✅ **Usura denti** - Verificare periodicamente
- ✅ **Lubrificazione** - NO sulla cinghia, SI sui cuscinetti valvola

### **Troubleshooting**

**Problema:** Valvola non si apre completamente a 100%
- Verifica tensione cinghia
- Controlla alimentazione motore (>12V consigliato)
- Aumenta delay step (più coppia)

**Problema:** Steps persi (posizione non corrisponde)
- Riduzione troppo veloce → aumenta delay
- Cinghia salta → aumenta tensione
- Carico eccessivo → verifica valvola non bloccata

**Problema:** Vibrazioni eccessive
- Velocità troppo alta → aumenta delay
- Risonanza meccanica → cambia velocità

---

## 📐 Formula Generale

Per adattare a configurazioni diverse:

```python
# Parametri da misurare:
DENTI_MOTORE = 20
DENTI_VALVOLA = 60
GIRI_MOTORE_APERTURA = 7  # Misura fisica

# Calcoli automatici:
GEAR_RATIO = DENTI_VALVOLA / DENTI_MOTORE
VALVE_TOTAL_STEPS = STEPS_PER_REVOLUTION * GIRI_MOTORE_APERTURA
VALVE_TURNS = GIRI_MOTORE_APERTURA / GEAR_RATIO
```

---

## ✅ Checklist Installazione

- [ ] Pulegge montate e allineate
- [ ] Cinghia tesa correttamente
- [ ] Motore fissato saldamente
- [ ] Driver A4988 configurato (full step)
- [ ] Pin GPIO collegati (STEP, DIR, ENABLE)
- [ ] Alimentazione motore collegata (12-24V)
- [ ] `config.py` aggiornato con valori corretti
- [ ] Calibrazione eseguita (valvola chiusa = 0 steps)
- [ ] Test apertura 100% completato
- [ ] Ripetibilità verificata

---

**Sistema pronto per produzione!** 🎯
