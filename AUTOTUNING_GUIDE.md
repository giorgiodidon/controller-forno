# Guida Autotuning PID — Forno Ceramica v3.1

## Cos'è l'autotuning e perché serve

L'autotuning trova automaticamente i parametri ottimali (Kp, Ki, Kd) del controller PID che regola la valvola del gas. Senza parametri corretti il forno può oscillare, superare la temperatura target, o essere troppo lento a raggiungere il setpoint. Ogni forno ha caratteristiche termiche diverse (massa, isolamento, potenza del bruciatore), quindi i parametri vanno trovati sperimentalmente.

Il metodo usato è il **Relay Feedback di Åström-Hägglund**: il sistema forza piccole oscillazioni controllate attorno a una temperatura target e, misurando ampiezza e periodo di queste oscillazioni, calcola i parametri PID ottimali. È il metodo standard industriale per sistemi termici lenti come i forni.

---

## Cosa succede durante il test

Il test si svolge in 3 fasi automatiche. Non devi fare nulla una volta avviato, ma devi restare nelle vicinanze del forno.

### Fase 1 — Riscaldamento (da temperatura ambiente a 480°C)

Il forno sale lentamente verso i 500°C. La valvola si apre in modo graduale e conservativo per proteggere i refrattari.

| Distanza dal target | Apertura valvola |
|---------------------|------------------|
| oltre 400°C         | 35%              |
| 300-400°C           | 30%              |
| 200-300°C           | 25%              |
| 100-200°C           | 20%              |
| 50-100°C            | 15%              |
| 20-50°C             | 10%              |
| sotto 20°C          | 5%               |

La velocità di riscaldamento è circa 50-80°C/h. Questo significa che partendo da temperatura ambiente (20°C) ci vorranno circa **6-8 ore** per raggiungere i 480°C dove inizia la fase relay.

**Durata stimata fase 1: 6-8 ore** (da 20°C a 480°C)

### Fase 2 — Test Relay (oscillazioni attorno a 500°C)

Quando la temperatura arriva a 480°C (20°C sotto il target), il sistema passa al controllo relay. La valvola alterna tra due posizioni fisse:

- **Temperatura sotto 495°C** (setpoint - isteresi): valvola apre a **25%**
- **Temperatura sopra 505°C** (setpoint + isteresi): valvola chiude a **0%**
- **Tra 495°C e 505°C**: mantiene la posizione precedente

Questo crea oscillazioni controllate. Il sistema deve completare almeno **3 oscillazioni complete** (3 cicli sopra-sotto-sopra il setpoint). Ogni oscillazione, dato l'inerzia termica del forno, durerà probabilmente tra 5 e 15 minuti.

**Durata stimata fase 2: 20-45 minuti**

### Fase 3 — Calcolo e risultati

Completate le oscillazioni, il sistema calcola automaticamente:

1. **Periodo critico (Pu)**: tempo medio di una oscillazione completa
2. **Ampiezza**: metà della differenza tra picco massimo e picco minimo
3. **Guadagno critico (Ku)**: calcolato dalla formula `Ku = 4d / (π × ampiezza)` dove d = 25% (ampiezza relay)
4. **Parametri PID** con formule Ziegler-Nichols:
   - Versione standard: Kp = 0.6×Ku, Ki = 1.2×Ku/Pu, Kd = 0.075×Ku×Pu
   - Versione conservativa (consigliata): Kp = 0.45×Ku, Ki = 0.54×Ku/Pu, Kd = 0

La valvola si chiude automaticamente e i risultati vengono salvati in `data/logs/` e inviati come notifica push al telefono.

**Durata fase 3: istantanea**

---

## Durata totale stimata

| Fase | Durata stimata | Note |
|------|---------------|------|
| Riscaldamento | 6-8 ore | Da 20°C a 480°C, rampa lenta |
| Test relay | 20-45 minuti | 3 oscillazioni attorno a 500°C |
| Calcolo | Istantaneo | Automatico |
| Raffreddamento | 8-12 ore | Naturale, forno chiuso |
| **Totale** | **~1 giornata** | Il forno va sorvegliato durante riscaldamento e test |

Se il forno è già caldo (ad esempio dopo una cottura interrotta), la fase di riscaldamento sarà molto più breve.

---

## Istruzioni passo-passo

### Preparazione

1. **Verifica che il forno sia vuoto** — non caricare pezzi durante l'autotuning
2. **Verifica connessioni** — il Raspberry deve essere acceso, il sensore MCP9600 collegato, il motore stepper funzionante
3. **Verifica gas** — la bombola/linea gas deve essere aperta e il pilota acceso
4. **Apri il browser** sul telefono o computer all'indirizzo `http://IP_RASPBERRY:5000`
5. **Verifica temperatura** — sulla pagina principale deve apparire la lettura della termocoppia (temperatura ambiente, circa 20-30°C)

### Avvio test

1. Vai alla pagina **Autotuning**: `http://IP_RASPBERRY:5000/autotuning`
2. Verifica che la temperatura visualizzata sia corretta
3. Premi il pulsante **▶️ Avvia Autotuning**
4. Conferma nel popup "Avviare test autotuning a 500°C?"
5. Il test parte. Vedrai:
   - LED giallo: riscaldamento in corso
   - Percentuale di progresso
   - Apertura valvola attuale

### Durante il test

- **Non aprire il forno** — altera le misurazioni
- **Non toccare la valvola** manualmente — il sistema la controlla
- **Puoi lasciare il forno** durante il riscaldamento (fase 1), ma torna per la fase relay
- **Controlla lo stato** dal telefono — la pagina si aggiorna ogni 2 secondi
- **Riceverai notifiche push** sul telefono a completamento test
- Se qualcosa va storto, premi **⏹️ Ferma Test** o usa l'emergency stop

### Completamento

1. Quando il test è completo, la pagina mostra i risultati:
   - Guadagno critico (Ku)
   - Periodo critico (Pu) in secondi
   - Ampiezza oscillazione in °C
   - Parametri PID consigliati (Kp, Ki, Kd)
2. Premi **✓ Applica PID al Sistema** per usare i nuovi parametri
3. I parametri vengono anche salvati nella tabella adattiva per tutte le fasce di temperatura
4. La valvola si chiude automaticamente — lascia raffreddare il forno naturalmente

### Timeout e sicurezza

- Se il test non si completa entro **12 ore**, viene interrotto automaticamente e la valvola si chiude
- Se il sensore si disconnette, il watchdog chiude la valvola
- Se la temperatura supera i limiti di sicurezza (1310°C), scatta l'emergency stop
- Puoi fermare il test in qualsiasi momento dal browser o dall'API

---

## Dopo l'autotuning: PID adattivo

I parametri trovati dall'autotuning vengono usati come punto di partenza. Il sistema ha anche un modulo di **apprendimento adattivo** che migliora i parametri nel tempo:

1. **Dopo ogni cottura completata**, puoi analizzare i log chiamando `POST /api/analysis/run`
2. Il sistema valuta la qualità del controllo PID per ogni fascia di temperatura (0-200°C, 200-400°C, ecc.)
3. Se trova problemi (overshoot, oscillazioni, errore stazionario), propone piccoli aggiustamenti (±5-10%)
4. In modalità `suggest` (default) i suggerimenti vanno approvati manualmente prima di essere applicati
5. I parametri non possono mai uscire dai limiti di sicurezza, indipendentemente da cosa suggerisce il sistema

Le API per il PID adattivo:

| Endpoint | Descrizione |
|----------|-------------|
| `GET /api/adaptive/status` | Stato attuale e tabella parametri |
| `GET /api/adaptive/table` | Tabella completa per fascia |
| `POST /api/adaptive/enable` | Abilita PID adattivo |
| `POST /api/adaptive/disable` | Disabilita (torna a PID fisso) |
| `POST /api/adaptive/rollback` | Reset ai valori originali |
| `POST /api/analysis/run` | Analizza log cotture |
| `POST /api/learner/learn_all` | Analisi + apprendimento completo |
| `GET /api/learner/status` | Suggerimenti in coda |
| `POST /api/learner/approve` | Approva suggerimenti |
| `POST /api/learner/reject` | Rifiuta suggerimenti |

---

## Quando ripetere l'autotuning

Ripeti il test se:

- Hai cambiato il bruciatore o la valvola del gas
- Hai modificato l'isolamento del forno
- Hai cambiato tipo di termocoppia o posizione del sensore
- Le cotture mostrano costantemente problemi di controllo che il PID adattivo non riesce a correggere
- Sono passati molti mesi e le prestazioni sono degradate

Non è necessario ripetere l'autotuning se cambi solo il tipo di cottura (gres, porcellana, ecc.) — il PID adattivo si occupa di ottimizzare i parametri per le diverse fasce di temperatura in base ai dati delle cotture reali.
