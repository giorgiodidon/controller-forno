# 🔧 Integrazione Codice Testato A4988 - v3.0.2

## 📝 Modifiche Applicate

### ✅ **Integrato Codice Funzionante dalla Chat "a4988"**

---

## 🔌 **1. Pin GPIO Aggiornati**

### **Prima (teorico):**
```python
STEPPER_STEP_PIN = 17
STEPPER_DIR_PIN = 27
STEPPER_ENABLE_PIN = 22  # Gestito via software
```

### **Dopo (testato e funzionante):**
```python
STEPPER_STEP_PIN = 18   # GPIO 18 (Pin fisico 12) - Giallo
STEPPER_DIR_PIN = 17    # GPIO 17 (Pin fisico 11) - Verde
# ENABLE collegato a GND sull'A4988 (sempre abilitato)
# Resistori 10kΩ su STEP e DIR collegati a GND
```

**Motivo:** Configurazione hardware testata e funzionante

---

## ⚡ **2. Velocità Step Aggiornata**

### **Prima:**
```python
STEPPER_SPEED_NORMAL = 0.001  # 1ms
STEPPER_SPEED_SLOW = 0.002    # 2ms
```

### **Dopo:**
```python
STEPPER_SPEED_NORMAL = 0.01   # 10ms - TESTATO
STEPPER_SPEED_SLOW = 0.02     # 20ms
```

**Motivo:** 
- 10ms funziona perfettamente in test reali
- 1ms era troppo veloce (rischio steps persi)
- Movimento più stabile e affidabile

---

## 🔒 **3. Setup GPIO Sicuro**

### **Modifiche in `_setup_gpio()`:**

```python
# PRIMA
GPIO.setup(STEPPER_STEP_PIN, GPIO.OUT)
GPIO.setup(STEPPER_DIR_PIN, GPIO.OUT)
GPIO.setup(STEPPER_ENABLE_PIN, GPIO.OUT)
GPIO.output(STEPPER_ENABLE_PIN, GPIO.HIGH)  # Disabilitato

# DOPO
GPIO.setup(STEPPER_STEP_PIN, GPIO.OUT, initial=GPIO.LOW)  # ← Sicuro
GPIO.setup(STEPPER_DIR_PIN, GPIO.OUT, initial=GPIO.LOW)   # ← Sicuro
# ENABLE fisicamente a GND (sempre abilitato)
```

**Benefici:**
- Pin partono LOW (motore fermo)
- Nessuno spike all'avvio
- ENABLE sempre attivo (più semplice)

---

## 🎯 **4. Metodo step() Migliorato**

### **Aggiunta Pausa Stabilizzazione:**

```python
def step(self, direction, steps, speed=0.01):
    GPIO.output(STEPPER_DIR_PIN, GPIO.HIGH if direction else GPIO.LOW)
    time.sleep(0.1)  # ← NUOVO: Pausa per stabilizzare direzione
    
    for i in range(steps):
        GPIO.output(STEPPER_STEP_PIN, GPIO.HIGH)
        time.sleep(speed)
        GPIO.output(STEPPER_STEP_PIN, GPIO.LOW)
        time.sleep(speed)
```

**Motivo:** 
- Driver A4988 ha bisogno di tempo per cambiare direzione
- Senza pausa → primi steps possono essere in direzione sbagliata
- 0.1s è sufficiente per stabilizzare

---

## 🛑 **5. Shutdown Sicuro (CRITICO)**

### **Prima:**
```python
def cleanup(self):
    self.set_position(0)
    self.disable()
    GPIO.cleanup()  # ← PROBLEMA: crea stati floating
```

### **Dopo:**
```python
def cleanup(self):
    self.set_position(0)
    
    # Porta pin a LOW
    GPIO.output(STEPPER_STEP_PIN, GPIO.LOW)
    GPIO.output(STEPPER_DIR_PIN, GPIO.LOW)
    time.sleep(0.5)
    
    # NON fare GPIO.cleanup() ← IMPORTANTE
    print("✅ Pin GPIO a LOW - Motore fermo")
```

**Motivo CRITICO:**
- `GPIO.cleanup()` porta pin in stato INPUT (floating)
- Pin floating → segnali casuali → motore gira da solo!
- Mantenendo OUTPUT LOW → motore garantito fermo

---

## ❌ **6. Rimossi Metodi enable/disable**

**Non più necessari** perché ENABLE è fisicamente a GND.

**Rimosso:**
```python
def enable(self): ...
def disable(self): ...
```

**Semplificato:**
- Motore sempre abilitato
- Meno complessità
- Codice più pulito

---

## 📊 **7. Status API Aggiornato**

### **Campo Rimosso:**
```json
{
  "enabled": true  // ← Rimosso (sempre true)
}
```

**Motivo:** Campo inutile, motore sempre abilitato

---

## 🧪 **Test Disponibili**

### **Test Standalone:**
```bash
cd /home/giorgio/kiln
python3 test_stepper_integration.py
```

**Opzioni:**
1. Test base (mezzo giro avanti/indietro)
2. Test range completo (0→100→0%)
3. Entrambi

### **Test Via App:**
```bash
# Avvia server
python3 app.py

# In altro terminale
curl -X POST http://localhost:5000/api/valve/position \
  -H "Content-Type: application/json" \
  -d '{"position": 50}'
```

---

## 🔍 **Verifiche Post-Integrazione**

### ✅ **Checklist:**

- [ ] Server avvia senza errori
- [ ] GPIO configurati con pin corretti (18, 17)
- [ ] Log mostra "ENABLE collegato a GND"
- [ ] Test mezzo giro funziona
- [ ] Motore si ferma correttamente
- [ ] CTRL+C non fa girare motore
- [ ] Riavvio sistema non fa girare motore

---

## 📐 **Configurazione Hardware Finale**

```
Raspberry Pi GPIO → A4988 Driver → NEMA17 Motor
                                      ↓
                                  Puleggia 20 denti
                                      ↓
                                   Cinghia
                                      ↓
                                  Puleggia 60 denti
                                      ↓
                                  Valvola Gas

Pin Connections:
- GPIO 18 (Fisico 12) → STEP (+ resistore 10kΩ a GND)
- GPIO 17 (Fisico 11) → DIR  (+ resistore 10kΩ a GND)
- GND                 → ENABLE (sempre abilitato)
- 12-24V              → VMOT (alimentazione motore)
- 5V / 3.3V           → VDD (logica driver)
```

---

## ⚡ **Prestazioni Sistema**

### **Velocità Operativa:**
```
Delay step: 10ms (0.01s)
Steps totali: 1400 (apertura completa)
Tempo apertura 0→100%: 28 secondi
Tempo apertura 0→50%: 14 secondi
```

### **Precisione:**
```
1% apertura = 14 steps
Risoluzione angolare motore: 1.8°
Risoluzione angolare valvola: 0.6° (con gear ratio 3:1)
```

---

## 🚨 **Note Sicurezza**

### **IMPORTANTE:**

1. **Mai usare `GPIO.cleanup()`** alla fine del programma
   - Crea stati floating
   - Motore può girare da solo
   - Usare solo pin OUTPUT LOW

2. **Resistori 10kΩ obbligatori**
   - Su pin STEP e DIR
   - Collegati a GND
   - Evitano segnali spuri

3. **ENABLE sempre a GND**
   - Motore sempre pronto
   - Nessuna gestione software
   - Più semplice e affidabile

---

## 📄 **File Modificati**

1. ✅ `config.py` - Pin GPIO e velocità
2. ✅ `hardware/actuators.py` - Logica stepper
3. ✅ `test_stepper_integration.py` - Test nuovo

---

## 🔄 **Compatibilità**

### **Retrocompatibile:**
- ✅ API REST identiche
- ✅ Interfaccia web identica
- ✅ Programmi salvati compatibili
- ✅ Notifiche funzionanti

### **Breaking Changes:**
- ⚠️ Pin GPIO diversi (richiede ricablaggio)
- ⚠️ Campo `enabled` rimosso da status API

---

## 📈 **Vantaggi Integrazione**

✅ **Codice testato** in condizioni reali  
✅ **Velocità ottimizzata** per stabilità  
✅ **Shutdown sicuro** senza stati floating  
✅ **Setup semplificato** (ENABLE fisico)  
✅ **Meno codice** (rimossi enable/disable)  
✅ **Più affidabile** (meno bug potenziali)  

---

## 🎯 **Prossimi Step**

1. **Ricabla hardware** con pin corretti:
   - GPIO 18 → STEP
   - GPIO 17 → DIR
   - ENABLE → GND

2. **Test sistema:**
   ```bash
   python3 test_stepper_integration.py
   ```

3. **Verifica app completa:**
   ```bash
   python3 app.py
   ```

4. **Calibra valvola:**
   - Chiudi manualmente
   - Calibra via API/interfaccia
   - Test apertura 0→100%

---

**Versione:** v3.0.2  
**Data:** 2026-02-14  
**Status:** ✅ Pronto per test hardware
