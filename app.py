#!/usr/bin/env python3
"""
Forno Ceramica v3.1 - Controller Principale
Architettura modulare con PID Adattivo
"""

import time
import threading
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS

# Import moduli custom
from config import *
from hardware import SensorManager, ActuatorManager
from core import PIDController, SafetyMonitor, DataLogger, Watchdog
from core.autotuner import RelayAutotuner
from core.pid_adaptive import AdaptivePIDManager
from core.pid_analyzer import PIDAnalyzer
from core.pid_learner import PIDLearner
from services import NotificationService, StorageService
from utils import calculate_cooling_rate, format_time

# ===== INIZIALIZZAZIONE FLASK =====
app = Flask(__name__)
CORS(app)

# ===== INIZIALIZZAZIONE COMPONENTI =====
print("="*60)
print(f"{SYSTEM_NAME}")
print("="*60)

# Hardware
sensors = SensorManager()
actuators = ActuatorManager()

# Core
pid = PIDController()
safety = SafetyMonitor()
logger = DataLogger()
autotuner = RelayAutotuner(test_temperature=500)

# PID Adattivo
adaptive = AdaptivePIDManager(pid)
analyzer = PIDAnalyzer()
learner = PIDLearner(adaptive.table)

# Services
notifications = NotificationService()
storage = StorageService()

# Watchdog (monitor sicurezza indipendente)
watchdog = Watchdog(actuators, notifications)

print("✅ Tutti i componenti inizializzati")
print("="*60)

# ===== DATI GLOBALI =====
temperature_data = {
    'hot': 0.0,
    'cold': 0.0,
    'delta': 0.0,
    'status': 'connecting',
    'timestamp': time.time(),
    'cooling_rate': 0.0
}

temp_history = []  # Per calcolo cooling rate

program_state = {
    'running': False,
    'program_name': '',
    'current_ramp': 0,
    'current_setpoint': 20.0,
    'start_time': None
}


# ===== THREAD MONITORAGGIO TEMPERATURE =====
def temperature_monitor_thread():
    """Thread continuo per lettura sensori"""
    global temperature_data, temp_history
    
    sensor_was_connected = False
    
    while True:
        # Heartbeat watchdog — segnala che questo thread è vivo
        watchdog.feed()
        
        # Leggi sensore
        temp_data = sensors.get_temperature_data()
        
        if temp_data['status'] == 'connected':
            temperature_data = temp_data
            
            # Segnala al watchdog che il sensore funziona
            watchdog.report_sensor_ok(temp_data['hot'])
            
            # Aggiungi a storico
            temp_history.append({
                'timestamp': time.time(),
                'temp': temp_data['hot']
            })
            
            # Mantieni solo ultime N letture
            if len(temp_history) > TEMP_HISTORY_SIZE:
                temp_history = temp_history[-TEMP_HISTORY_SIZE:]
            
            # Calcola cooling rate se sotto 700°C
            if temp_data['hot'] < 700 and temp_data['hot'] > 50:
                cooling_rate = calculate_cooling_rate(temp_history)
                temperature_data['cooling_rate'] = cooling_rate
            else:
                temperature_data['cooling_rate'] = 0.0
            
            # Notifica riconnessione
            if not sensor_was_connected:
                sensor_was_connected = True
                notifications.notify_sensor_reconnect(temp_data['hot'])
            
        else:
            temperature_data['status'] = 'error'
            
            # Segnala errore sensore al watchdog
            watchdog.report_sensor_error()
            
            # Verifica salute sensore (attiva emergency se necessario)
            safety.check_sensor_health(temp_data['status'])
            
            # Notifica errore
            if sensor_was_connected:
                sensor_was_connected = False
                notifications.notify_sensor_error()
        
        # Controlli sicurezza
        safety_result = safety.check_all(
            temperature_data['hot'],
            temperature_data['cold'],
            temperature_data['cooling_rate']
        )
        
        # Gestisci emergenze
        if safety_result['emergency_stop']:
            actuators.emergency_stop()
            notifications.notify_over_temp(temperature_data['hot'])
        
        # Notifiche allarmi
        for alarm in safety_result['alarms']:
            if alarm['code'] == 'FAST_COOLING':
                notifications.notify_fast_cooling(alarm['value'])
        
        # Controllo autotuning
        if autotuner.is_running:
            valve_pos = autotuner.compute_valve_position(temperature_data['hot'])
            if valve_pos is not None:
                actuators.set_valve_position(valve_pos)
                
            # Notifica completamento test
            if autotuner.phase == 'complete':
                if not hasattr(autotuner, '_completion_notified'):
                    notifications.send(
                        "🎯 Autotuning Completato",
                        f"PID ottimizzato calcolato!\nKp={autotuner.Kp:.4f}, Ki={autotuner.Ki:.6f}\nApplica risultati nella pagina autotuning.",
                        priority="high",
                        tags=["white_check_mark", "gear"]
                    )
                    
                    # Aggiorna tabella adattiva con risultati autotuning
                    adaptive.table.set_base_from_autotuning(
                        autotuner.Kp, autotuner.Ki, autotuner.Kd
                    )
                    
                    autotuner._completion_notified = True
                
                # Ferma autotuning
                autotuner.is_running = False
        
        # Controllo PID durante esecuzione programma
        if program_state['running'] and not autotuner.is_running:
            # Aggiorna PID adattivo in base alla temperatura corrente
            adaptive.update_tunings(temperature_data['hot'])
            
            # Calcola output PID
            valve_output = pid.compute(
                program_state['current_setpoint'],
                temperature_data['hot']
            )
            actuators.set_valve_position(valve_output)
            
            # Log temperatura con dati PID interni
            if logger.is_logging:
                logger.log_temperature(
                    temperature_data['hot'],
                    program_state['current_setpoint'],
                    valve_output,
                    temperature_data['cooling_rate'],
                    pid_data={
                        'kp': pid.kp,
                        'ki': pid.ki,
                        'kd': pid.kd,
                        'error': pid.last_error,
                        'integral': pid.integral,
                        'output': pid.last_output
                    }
                )
                
        time.sleep(SENSOR_UPDATE_INTERVAL)


# ===== FLASK ROUTES =====

@app.route('/')
def index():
    """Pagina principale"""
    return render_template('index.html')


@app.route('/api/temperatures')
def get_temperatures():
    """API temperature in tempo reale"""
    return jsonify(temperature_data)


@app.route('/api/status')
def get_status():
    """API stato sistema completo"""
    return jsonify({
        'system': {
            'name': SYSTEM_NAME,
            'version': SYSTEM_VERSION
        },
        'sensors': sensors.get_diagnostics(),
        'actuators': actuators.get_status(),
        'pid': pid.get_status(),
        'adaptive': adaptive.get_status(),
        'safety': safety.get_status(),
        'watchdog': watchdog.get_status(),
        'notifications': notifications.get_status(),
        'program': program_state
    })


# ===== ROUTES PROGRAMMI =====

@app.route('/api/programs', methods=['GET'])
def get_programs():
    """Ottieni tutti i programmi"""
    programs = storage.load_programs()
    return jsonify(programs)


@app.route('/api/programs', methods=['POST'])
def save_program():
    """Salva programma"""
    try:
        data = request.json
        success = storage.save_program(data)
        
        if success:
            return jsonify({'success': True, 'message': 'Programma salvato'})
        else:
            return jsonify({'success': False, 'error': 'Errore salvataggio'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/programs/<n>', methods=['GET'])
def get_program(n):
    """Ottieni singolo programma"""
    program = storage.get_program(n)
    if program:
        return jsonify(program)
    else:
        return jsonify({'error': 'Programma non trovato'}), 404


@app.route('/api/programs/<n>', methods=['DELETE'])
def delete_program(n):
    """Elimina programma"""
    success = storage.delete_program(n)
    if success:
        return jsonify({'success': True, 'message': 'Programma eliminato'})
    else:
        return jsonify({'success': False, 'error': 'Programma non trovato'}), 404


# ===== ROUTES ATTUATORI =====

@app.route('/api/valve/position', methods=['POST'])
def set_valve_position():
    """Imposta posizione valvola manualmente"""
    try:
        data = request.json
        position = float(data.get('position', 0))
        
        actual = actuators.set_valve_position(position)
        
        return jsonify({
            'success': True,
            'position': actual
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/valve/status')
def get_valve_status():
    """Stato valvola"""
    return jsonify(actuators.valve.get_status())


@app.route('/api/valve/calibrate', methods=['POST'])
def calibrate_valve():
    """Calibra valvola (azzera posizione)"""
    try:
        data = request.json or {}
        manual_steps = int(data.get('manual_steps', 0))
        
        actuators.calibrate_valve(manual_steps)
        
        return jsonify({
            'success': True,
            'message': 'Calibrazione completata'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# ===== ROUTES PID =====

@app.route('/api/pid/tunings', methods=['GET'])
def get_pid_tunings():
    """Ottieni parametri PID"""
    return jsonify(pid.get_tunings())


@app.route('/api/pid/tunings', methods=['POST'])
def set_pid_tunings():
    """Imposta parametri PID"""
    try:
        data = request.json
        kp = float(data.get('kp', PID_KP))
        ki = float(data.get('ki', PID_KI))
        kd = float(data.get('kd', PID_KD))
        
        pid.set_tunings(kp, ki, kd)
        
        return jsonify({
            'success': True,
            'tunings': pid.get_tunings()
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# ===== ROUTES LOGGING =====

@app.route('/api/log/current')
def get_current_log():
    """Ottieni log corrente"""
    return jsonify(logger.get_current_log())


@app.route('/api/log/start', methods=['POST'])
def start_logging():
    """Avvia logging"""
    try:
        data = request.json
        program_name = data.get('program_name', 'Programma')
        
        logger.start_logging(program_name)
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/log/stop', methods=['POST'])
def stop_logging():
    """Ferma logging"""
    logger.stop_logging()
    return jsonify({'success': True})


@app.route('/api/log/temperature', methods=['POST'])
def log_temperature():
    """Logga temperatura (chiamato da frontend)"""
    try:
        data = request.json
        temp = float(data.get('temp', 0))
        setpoint = float(data.get('setpoint', 0))
        valve_pos = float(data.get('valve_position', 0))
        cooling_rate = float(data.get('cooling_rate', 0))
        
        logger.log_temperature(temp, setpoint, valve_pos, cooling_rate)
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/log/event', methods=['POST'])
def log_event():
    """Logga evento"""
    try:
        data = request.json
        event_type = data.get('type', 'info')
        message = data.get('message', '')
        
        logger.log_event(event_type, message)
        
        # Invia notifiche per eventi importanti
        if event_type == 'ramp_complete':
            parts = message.split('→')
            if len(parts) == 2:
                ramp_info = parts[0].strip()
                temp_info = parts[1].strip()
                notifications.notify_ramp_complete(0, 0, temp_info.replace('°C completata', ''))
        
        elif event_type == 'hold_start':
            notifications.notify_hold_start(0, 0)
        
        elif event_type == 'cooling':
            temp = temperature_data['hot']
            notifications.notify_cooling_start(temp)
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# ===== ROUTES NOTIFICHE =====

@app.route('/api/notify', methods=['POST'])
def send_notification():
    """Invia notifica personalizzata"""
    try:
        data = request.json
        title = data.get('title', 'Forno Ceramica')
        message = data.get('message', '')
        priority = data.get('priority', 'default')
        tags = data.get('tags', [])
        
        success = notifications.send(title, message, priority, tags)
        
        return jsonify({'success': success})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# ===== ROUTES SICUREZZA =====

@app.route('/api/safety/status')
def get_safety_status():
    """Stato sicurezza"""
    return jsonify(safety.get_status())


@app.route('/api/safety/reset', methods=['POST'])
def reset_safety():
    """Reset emergenza (dopo intervento manuale)"""
    safety.reset_emergency()
    return jsonify({'success': True})


@app.route('/api/emergency/stop', methods=['POST'])
def emergency_stop():
    """STOP EMERGENZA"""
    actuators.emergency_stop()
    logger.stop_logging()
    
    # Chiudi anche valvola elettromagnetica se presente
    if watchdog.solenoid.enabled:
        watchdog.solenoid.close()
    
    return jsonify({
        'success': True,
        'message': 'EMERGENCY STOP eseguito'
    })


# ===== ROUTES WATCHDOG =====

@app.route('/api/watchdog/status')
def get_watchdog_status():
    """Stato watchdog"""
    return jsonify(watchdog.get_status())


@app.route('/api/watchdog/reset', methods=['POST'])
def reset_watchdog():
    """Reset watchdog dopo intervento manuale"""
    watchdog.reset()
    safety.reset_emergency()
    return jsonify({
        'success': True,
        'message': 'Watchdog e safety resettati'
    })


# ===== ROUTES AUTOTUNING =====

@app.route('/autotuning')
def autotuning_page():
    """Pagina autotuning PID"""
    return render_template('autotuning.html')


@app.route('/api/autotuning/start', methods=['POST'])
def start_autotuning():
    """Avvia test autotuning"""
    try:
        data = request.json or {}
        temperature = data.get('temperature', 500)
        
        autotuner.test_temperature = temperature
        autotuner.setpoint = temperature
        autotuner.start()
        
        notifications.send(
            "🎯 Autotuning Avviato",
            f"Test PID a {temperature}°C in corso...",
            priority="default",
            tags=["gear"]
        )
        
        return jsonify({'success': True, 'message': 'Autotuning avviato'})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/autotuning/stop', methods=['POST'])
def stop_autotuning():
    """Ferma test autotuning"""
    try:
        autotuner.stop()
        return jsonify({'success': True, 'message': 'Autotuning fermato'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/autotuning/status')
def get_autotuning_status():
    """Stato corrente autotuning"""
    return jsonify(autotuner.get_status())


@app.route('/api/autotuning/results')
def get_autotuning_results():
    """Risultati finali autotuning"""
    results = autotuner.get_results()
    if results:
        return jsonify(results)
    else:
        return jsonify({'error': 'Test non completato'}), 404


@app.route('/api/autotuning/chart_data')
def get_autotuning_chart_data():
    """Dati per grafico oscillazioni"""
    return jsonify(autotuner.get_chart_data())


@app.route('/api/pid/apply', methods=['POST'])
def apply_pid():
    """Applica parametri PID al controller"""
    try:
        data = request.json
        kp = float(data.get('Kp'))
        ki = float(data.get('Ki'))
        kd = float(data.get('Kd'))
        
        pid.set_tunings(kp, ki, kd)
        
        notifications.send(
            "⚙️ PID Aggiornato",
            f"Nuovi parametri: Kp={kp:.4f}, Ki={ki:.6f}, Kd={kd:.2f}",
            priority="default",
            tags=["gear"]
        )
        
        return jsonify({
            'success': True,
            'message': 'PID applicato',
            'tunings': pid.get_tunings()
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# ===== ROUTES PID ADATTIVO =====

@app.route('/api/adaptive/status')
def get_adaptive_status():
    """Stato PID adattivo"""
    return jsonify(adaptive.get_status())


@app.route('/api/adaptive/enable', methods=['POST'])
def enable_adaptive():
    """Abilita PID adattivo"""
    adaptive.enable()
    return jsonify({'success': True, 'enabled': True})


@app.route('/api/adaptive/disable', methods=['POST'])
def disable_adaptive():
    """Disabilita PID adattivo (torna a PID fisso)"""
    adaptive.disable()
    return jsonify({'success': True, 'enabled': False})


@app.route('/api/adaptive/table')
def get_adaptive_table():
    """Tabella completa parametri per fascia"""
    return jsonify(adaptive.table.get_table_summary())


@app.route('/api/adaptive/rollback', methods=['POST'])
def rollback_adaptive():
    """Rollback parametri a valori base"""
    data = request.json or {}
    band = data.get('band', None)
    
    if band is not None:
        adaptive.table.rollback_band(int(band))
        return jsonify({'success': True, 'message': f'Fascia {band}°C resettata'})
    else:
        adaptive.table.rollback_all()
        return jsonify({'success': True, 'message': 'Tutte le fasce resettate'})


# ===== ROUTES ANALISI =====

@app.route('/api/analysis/run', methods=['POST'])
def run_analysis():
    """Analizza log cotture e genera suggerimenti"""
    try:
        data = request.json or {}
        filepath = data.get('filepath', None)
        
        if filepath:
            result = analyzer.analyze_firing(filepath)
        else:
            results = analyzer.analyze_all_logs()
            if results:
                result = results[-1]
            else:
                return jsonify({'success': False, 'error': 'Nessun log trovato'})
        
        if result:
            learn_result = learner.process_analysis(result)
            
            return jsonify({
                'success': True,
                'analysis': result.to_dict(),
                'learning': learn_result
            })
        else:
            return jsonify({'success': False, 'error': 'Analisi fallita'})
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/analysis/aggregated')
def get_aggregated_analysis():
    """Metriche aggregate multi-cottura"""
    return jsonify(analyzer.get_aggregated_metrics())


# ===== ROUTES LEARNER =====

@app.route('/api/learner/status')
def get_learner_status():
    """Stato learner"""
    return jsonify(learner.get_status())


@app.route('/api/learner/mode', methods=['POST'])
def set_learner_mode():
    """Imposta modalità learner (suggest/auto)"""
    data = request.json or {}
    mode = data.get('mode', 'suggest')
    learner.set_mode(mode)
    return jsonify({'success': True, 'mode': mode})


@app.route('/api/learner/approve', methods=['POST'])
def approve_suggestions():
    """Approva suggerimenti in coda"""
    applied = learner.approve_pending()
    return jsonify({'success': True, 'applied': applied})


@app.route('/api/learner/reject', methods=['POST'])
def reject_suggestions():
    """Rifiuta suggerimenti in coda"""
    rejected = learner.reject_pending()
    return jsonify({'success': True, 'rejected': rejected})


@app.route('/api/learner/learn_all', methods=['POST'])
def learn_from_all():
    """Analizza tutti i log e applica apprendimento"""
    try:
        analyses = analyzer.analyze_all_logs()
        
        if len(analyses) < 2:
            return jsonify({
                'success': False,
                'error': f'Servono almeno 2 cotture (disponibili: {len(analyses)})'
            })
        
        result = learner.process_all_analyses(analyses)
        
        notifications.send(
            "🧠 PID Learning",
            f"Analizzate {len(analyses)} cotture.\n"
            f"Applicati: {result['applied']}, In coda: {result['pending']}",
            priority="default",
            tags=["brain"]
        )
        
        return jsonify({
            'success': True,
            'firings_analyzed': len(analyses),
            'learning': result
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# ===== CLEANUP =====
def cleanup():
    """Cleanup alla chiusura"""
    print("\n🧹 Cleanup sistema...")
    watchdog.stop()
    actuators.cleanup()
    # Chiudi valvola elettromagnetica per sicurezza
    if watchdog.solenoid.enabled:
        watchdog.solenoid.close()
    print("✅ Cleanup completato")


import atexit
atexit.register(cleanup)


# ===== MAIN =====
if __name__ == '__main__':
    # Avvia watchdog (prima del thread monitor)
    watchdog.start()
    print("🐕 Watchdog avviato")
    
    # Avvia thread monitoraggio
    monitor_thread = threading.Thread(target=temperature_monitor_thread, daemon=True)
    monitor_thread.start()
    
    print("✅ Thread monitoraggio avviato")
    
    # Notifica sistema online
    notifications.notify_system_start()
    
    # Avvia Flask
    print(f"🌐 Server web: http://{FLASK_HOST}:{FLASK_PORT}")
    print("="*60)
    print("Premi CTRL+C per fermare")
    print("="*60)
    
    app.run(
        host=FLASK_HOST,
        port=FLASK_PORT,
        debug=FLASK_DEBUG,
        use_reloader=False  # Evita doppio avvio thread
    )
