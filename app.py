#!/usr/bin/env python3
"""
Forno Ceramica v3.2 - Controller Principale
Architettura modulare con ProgramRunner server-side
"""

import time
import threading
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS

# Import moduli custom
from config import *
from hardware import SensorManager, ActuatorManager
from core import PIDController, SafetyMonitor, DataLogger, Watchdog, ProgramRunner
from core.autotuner import RelayAutotuner
from services import NotificationService, StorageService
from utils import calculate_cooling_rate, format_time
from utils.audio import (beep_startup, beep_program_start, beep_program_complete,
                         beep_program_stopped, beep_autotuning_start,
                         beep_autotuning_complete, beep_error, beep_emergency)

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

# Services
notifications = NotificationService()
storage = StorageService()

# Watchdog (monitor sicurezza indipendente)
watchdog = Watchdog(actuators, notifications)

# Collega DataLogger all'autotuner per log completi
autotuner.set_data_logger(logger)

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
    'name': '',
    'program_name': '',
    'ramps': [],
    'current_ramp': 0,
    'total_ramps': 0,
    'current_setpoint': 20.0,
    'target_temp': 0,
    'rate': 0,
    'phase': 'idle',
    'start_time': None,
    'ramp_progress': 0,
    'ramp_remaining_min': 0,
    'hold_remaining_min': 0,
    'total_remaining_min': 0,
    'elapsed_min': 0,
    'valve_output': 0
}

# Program Runner (motore esecuzione programmi)
runner = ProgramRunner(
    pid_controller=pid,
    actuators=actuators,
    sensors=sensors,
    logger=logger,
    notifications=notifications,
    program_state=program_state,
    temperature_data=temperature_data
)


# ===== THREAD MONITORAGGIO TEMPERATURE =====
def temperature_monitor_thread():
    """Thread continuo per lettura sensori e controlli sicurezza"""
    global temperature_data, temp_history

    # Parte True: la prima connessione NON manda notifica
    sensor_was_connected = True

    # Flag anti-spam
    overtemp_notified = False
    fast_cooling_notified = False

    while True:
        # Heartbeat watchdog
        watchdog.feed()

        # Leggi sensore
        temp_data = sensors.get_temperature_data()

        if temp_data['status'] == 'connected':
            temperature_data.update(temp_data)

            # Segnala al watchdog
            watchdog.report_sensor_ok(temp_data['hot'])

            # Storico
            temp_history.append({
                'timestamp': time.time(),
                'temp': temp_data['hot']
            })
            if len(temp_history) > TEMP_HISTORY_SIZE:
                temp_history = temp_history[-TEMP_HISTORY_SIZE:]

            # Cooling rate
            if temp_data['hot'] < 700 and temp_data['hot'] > 50:
                cooling_rate = calculate_cooling_rate(temp_history)
                temperature_data['cooling_rate'] = cooling_rate
            else:
                temperature_data['cooling_rate'] = 0.0

            # Notifica riconnessione (solo dopo errore reale)
            if not sensor_was_connected:
                sensor_was_connected = True
                notifications.notify_sensor_reconnect(temp_data['hot'])

        else:
            temperature_data['status'] = 'disconnected'

            if sensor_was_connected:
                sensor_was_connected = False
                notifications.notify_sensor_error()

            watchdog.report_sensor_error()
            safety.check_sensor_health(temp_data['status'])

        # Controlli sicurezza
        safety_result = safety.check_all(
            temperature_data.get('hot', 0),
            temperature_data.get('cold', 0),
            temperature_data.get('cooling_rate', 0)
        )

        # Gestisci emergenze (notifica una sola volta)
        if safety_result['emergency_stop']:
            actuators.emergency_stop()
            if runner.is_running:
                runner.emergency_stop()
            if not overtemp_notified:
                overtemp_notified = True
                notifications.notify_over_temp(temperature_data.get('hot', 0))
        else:
            overtemp_notified = False

        # Fast cooling (una sola volta)
        has_fast_cooling = False
        for alarm in safety_result['alarms']:
            if alarm['code'] == 'FAST_COOLING':
                has_fast_cooling = True
                if not fast_cooling_notified:
                    fast_cooling_notified = True
                    notifications.notify_fast_cooling(alarm['value'])
        if not has_fast_cooling:
            fast_cooling_notified = False

        # Autotuning (indipendente dal ProgramRunner)
        if autotuner.is_running:
            valve_pos = autotuner.compute_valve_position(temperature_data.get('hot', 0))
            if valve_pos is not None:
                actuators.set_valve_position(valve_pos)

            if autotuner.phase == 'complete':
                if not getattr(autotuner, '_completion_notified', False):
                    notifications.send(
                        "Autotuning Completato",
                        f"PID calcolato!\nKp={autotuner.Kp:.4f}, Ki={autotuner.Ki:.6f}",
                        priority="high",
                        tags=["white_check_mark", "gear"]
                    )
                    beep_autotuning_complete()
                    autotuner._completion_notified = True
                autotuner.is_running = False

        time.sleep(SENSOR_UPDATE_INTERVAL)


# ===== FLASK ROUTES =====

@app.route('/')
def index():
    """Pagina principale — monitoraggio"""
    return render_template('monitor.html')


@app.route('/gestione')
def gestione_page():
    """Pagina gestione programmi"""
    return render_template('gestione.html')


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


# ===== ROUTES ESECUZIONE PROGRAMMA =====

@app.route('/api/program/start', methods=['POST'])
def start_program():
    """Avvia esecuzione programma con ProgramRunner"""
    try:
        data = request.json
        program_name = data.get('program_name', 'Programma')
        ramps = data.get('ramps', [])

        if runner.is_running:
            return jsonify({'success': False, 'error': 'Un programma è già in esecuzione'})
        if autotuner.is_running:
            return jsonify({'success': False, 'error': 'Autotuning in corso'})

        success = runner.start(program_name, ramps)
        if success:
            beep_program_start()
            return jsonify({'success': True, 'message': f'Programma "{program_name}" avviato'})
        else:
            return jsonify({'success': False, 'error': 'Errore avvio programma'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/program/stop', methods=['POST'])
def stop_program():
    """Ferma programma in esecuzione"""
    if runner.is_running:
        runner.stop()
        beep_program_stopped()
    return jsonify({'success': True, 'message': 'Programma fermato'})


# ===== ROUTES LOGGING (compatibilità frontend) =====

@app.route('/api/log/start', methods=['POST'])
def start_logging():
    """Avvia programma — redirige al ProgramRunner"""
    try:
        data = request.json
        program_name = data.get('program_name', 'Programma')
        ramps = data.get('ramps', [])

        if runner.is_running:
            return jsonify({'success': False, 'error': 'Un programma è già in esecuzione'})
        if autotuner.is_running:
            return jsonify({'success': False, 'error': 'Autotuning in corso'})

        success = runner.start(program_name, ramps)
        if success:
            beep_program_start()
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Errore avvio programma'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/log/stop', methods=['POST'])
def stop_logging():
    """Ferma programma — redirige al ProgramRunner"""
    if runner.is_running:
        runner.stop()
        beep_program_stopped()
    return jsonify({'success': True})


@app.route('/api/log/current')
def get_current_log():
    """Ottieni log corrente"""
    return jsonify(logger.get_current_log())


@app.route('/api/log/temperature', methods=['POST'])
def log_temperature():
    """Logga temperatura (compatibilità frontend)"""
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


# ===== ROUTES VALVOLA =====

@app.route('/api/valve/position', methods=['POST'])
def set_valve_position():
    """Imposta posizione valvola manualmente"""
    if runner.is_running:
        return jsonify({'success': False, 'error': 'Impossibile: programma in esecuzione. Il PID controlla la valvola.'})
    try:
        data = request.json
        position = float(data.get('position', 0))
        actual = actuators.set_valve_position(position)
        return jsonify({'success': True, 'position': actual})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/valve/status')
def get_valve_status():
    """Stato valvola"""
    return jsonify(actuators.valve.get_status())


@app.route('/api/valve/calibrate', methods=['POST'])
def calibrate_valve():
    """Calibra valvola (azzera posizione)"""
    if runner.is_running:
        return jsonify({'success': False, 'error': 'Impossibile durante esecuzione programma'})
    try:
        data = request.json or {}
        manual_steps = int(data.get('manual_steps', 0))
        actuators.calibrate_valve(manual_steps)
        return jsonify({'success': True, 'message': 'Calibrazione completata'})
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
        return jsonify({'success': True, 'tunings': pid.get_tunings()})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


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
            "PID Aggiornato",
            f"Kp={kp:.4f}, Ki={ki:.6f}, Kd={kd:.2f}",
            priority="high",
            tags=["gear"]
        )
        return jsonify({'success': True, 'message': 'PID applicato', 'tunings': pid.get_tunings()})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# ===== ROUTES SICUREZZA =====

@app.route('/api/safety/status')
def get_safety_status():
    """Stato sicurezza"""
    return jsonify(safety.get_status())


@app.route('/api/safety/reset', methods=['POST'])
def reset_safety():
    """Reset emergenza"""
    safety.reset_emergency()
    return jsonify({'success': True})


@app.route('/api/emergency/stop', methods=['POST'])
def emergency_stop():
    """STOP EMERGENZA"""
    if runner.is_running:
        runner.emergency_stop()
    actuators.emergency_stop()
    if watchdog.solenoid.enabled:
        watchdog.solenoid.close()
    beep_emergency()
    return jsonify({'success': True, 'message': 'EMERGENCY STOP eseguito'})


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
    return jsonify({'success': True, 'message': 'Watchdog e safety resettati'})


# ===== ROUTES AUTOTUNING =====

@app.route('/autotuning')
def autotuning_page():
    """Pagina autotuning PID"""
    return render_template('autotuning.html')


@app.route('/api/autotuning/start', methods=['POST'])
def start_autotuning():
    """Avvia test autotuning a temperatura specificata"""
    if runner.is_running:
        return jsonify({'success': False, 'error': 'Impossibile: programma in esecuzione'})
    if autotuner.is_running:
        return jsonify({'success': False, 'error': 'Autotuning già in corso'})
    try:
        data = request.json or {}
        temperature = int(data.get('temperature', 500))
        
        # Validazione temperatura
        if temperature < 100:
            return jsonify({'success': False, 'error': 'Temperatura minima: 100°C'})
        if temperature > 1200:
            return jsonify({'success': False, 'error': 'Temperatura massima: 1200°C'})
        
        autotuner.test_temperature = temperature
        autotuner.setpoint = temperature
        autotuner.start()
        
        notifications.send(
            "Autotuning Avviato",
            f"Test PID a {temperature}°C in corso...",
            priority="high",
            tags=["gear"]
        )
        beep_autotuning_start()
        return jsonify({'success': True, 'message': f'Autotuning a {temperature}°C avviato'})
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


@app.route('/api/autotuning/history')
def get_autotuning_history():
    """Storico di tutti i test autotuning effettuati"""
    return jsonify(autotuner.get_history())


# ===== CLEANUP =====
def cleanup():
    """Cleanup alla chiusura"""
    print("\n🧹 Cleanup sistema...")
    if runner.is_running:
        runner.stop()
    watchdog.stop()
    actuators.cleanup()
    if watchdog.solenoid.enabled:
        watchdog.solenoid.close()
    print("✅ Cleanup completato")


import atexit
atexit.register(cleanup)


# ===== MAIN =====
if __name__ == '__main__':
    # Avvia watchdog
    watchdog.start()
    print("🐕 Watchdog avviato")

    # Avvia thread monitoraggio
    monitor_thread = threading.Thread(target=temperature_monitor_thread, daemon=True)
    monitor_thread.start()
    print("✅ Thread monitoraggio avviato")

    # Notifica sistema online
    notifications.notify_system_start()
    beep_startup()

    # Avvia Flask
    print(f"🌐 Server web: http://{FLASK_HOST}:{FLASK_PORT}")
    print("="*60)
    print("Premi CTRL+C per fermare")
    print("="*60)

    app.run(
        host=FLASK_HOST,
        port=FLASK_PORT,
        debug=FLASK_DEBUG,
        use_reloader=False
    )
