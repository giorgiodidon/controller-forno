"""
Funzioni di Calcolo per Temperature e Tempi
"""

from config import COOLING_CALC_WINDOW


def calculate_cooling_rate(temp_history, time_window=COOLING_CALC_WINDOW):
    """
    Calcola velocità di raffreddamento
    
    Args:
        temp_history (list): Lista [{timestamp, temp}, ...]
        time_window (int): Finestra temporale in secondi (default 600 = 10min)
    
    Returns:
        float: Velocità raffreddamento °C/h (negativa se raffredda)
    """
    if len(temp_history) < 2:
        return 0.0
    
    import time
    
    # Filtra ultimi N secondi
    cutoff_time = time.time() - time_window
    recent = [t for t in temp_history if t['timestamp'] >= cutoff_time]
    
    if len(recent) < 2:
        return 0.0
    
    # Calcola delta temp / delta tempo
    dt = recent[-1]['timestamp'] - recent[0]['timestamp']
    dTemp = recent[-1]['temp'] - recent[0]['temp']
    
    if dt == 0:
        return 0.0
    
    # Converti in °C/h
    rate_per_hour = (dTemp / dt) * 3600
    
    return round(rate_per_hour, 1)


def calculate_ramp_time(start_temp, target_temp, rate_per_hour):
    """
    Calcola tempo necessario per una rampa
    
    Args:
        start_temp (float): Temperatura iniziale (°C)
        target_temp (float): Temperatura target (°C)
        rate_per_hour (float): Velocità rampa (°C/h)
    
    Returns:
        float: Tempo in minuti
    """
    if rate_per_hour <= 0:
        return 0.0
    
    delta_temp = abs(target_temp - start_temp)
    time_hours = delta_temp / rate_per_hour
    time_minutes = time_hours * 60
    
    return round(time_minutes, 1)


def calculate_program_times(ramps):
    """
    Calcola tempi totali per un programma
    
    Args:
        ramps (list): Lista rampe [{rate, target, hold}, ...]
    
    Returns:
        dict: {total_time, ramp_time, hold_time, ramps_with_times}
    """
    total_time = 0
    total_ramp_time = 0
    total_hold_time = 0
    
    current_temp = 20  # Temperatura iniziale
    updated_ramps = []
    
    for ramp in ramps:
        rate = max(float(ramp.get('rate', 100)), 10)  # Minimo 10°C/h
        target = float(ramp.get('target', 200))
        hold = float(ramp.get('hold', 0))
        
        # Calcola tempo rampa
        ramp_time = calculate_ramp_time(current_temp, target, rate)
        
        # Calcola tempo totale step
        step_time = ramp_time + hold
        
        # Aggiorna totali
        total_time += step_time
        total_ramp_time += ramp_time
        total_hold_time += hold
        
        # Salva rampa con tempi calcolati
        updated_ramps.append({
            'rate': rate,
            'target': target,
            'hold': hold,
            'ramp_time': round(ramp_time, 1),
            'total_time': round(step_time, 1)
        })
        
        current_temp = target
    
    return {
        'total_time': round(total_time, 1),
        'ramp_time': round(total_ramp_time, 1),
        'hold_time': round(total_hold_time, 1),
        'ramps': updated_ramps
    }


def format_time(minutes):
    """
    Formatta minuti in HH:MM
    
    Args:
        minutes (float): Minuti
    
    Returns:
        str: Formato "HH:MM"
    """
    hours = int(minutes // 60)
    mins = int(minutes % 60)
    return f"{hours:02d}:{mins:02d}"


def celsius_to_fahrenheit(celsius):
    """Converti Celsius in Fahrenheit"""
    return (celsius * 9/5) + 32


def fahrenheit_to_celsius(fahrenheit):
    """Converti Fahrenheit in Celsius"""
    return (fahrenheit - 32) * 5/9
