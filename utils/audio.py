"""
Audio - Generazione beep di sistema per Forno Ceramica

Genera toni sinusoidali WAV in memoria e li riproduce via ALSA (aplay).
Funziona con altoparlanti collegati via HDMI su Raspberry Pi.
Non richiede dipendenze esterne.

Tutti i suoni girano in thread separati per non bloccare il sistema.
Se l'audio non è disponibile, fallisce silenziosamente.
"""

import os
import struct
import math
import wave
import tempfile
import subprocess
import threading
import time


# Directory temporanea per i file WAV
_TEMP_DIR = tempfile.gettempdir()


def _generate_tone(frequency, duration_ms, volume=0.5, sample_rate=44100):
    """
    Genera un tono sinusoidale come bytes WAV.
    
    Args:
        frequency: Frequenza in Hz (es. 800)
        duration_ms: Durata in millisecondi
        volume: Volume 0.0-1.0
        sample_rate: Sample rate (default 44100)
    
    Returns:
        bytes: Dati audio PCM 16-bit mono
    """
    num_samples = int(sample_rate * duration_ms / 1000)
    samples = []
    
    for i in range(num_samples):
        t = i / sample_rate
        # Sinusoide con fade in/out per evitare click
        value = math.sin(2 * math.pi * frequency * t)
        
        # Fade in (primi 5ms)
        fade_in_samples = int(sample_rate * 0.005)
        if i < fade_in_samples:
            value *= i / fade_in_samples
        
        # Fade out (ultimi 5ms)
        fade_out_samples = int(sample_rate * 0.005)
        if i > num_samples - fade_out_samples:
            value *= (num_samples - i) / fade_out_samples
        
        value = int(value * volume * 32767)
        samples.append(struct.pack('<h', max(-32768, min(32767, value))))
    
    return b''.join(samples)


def _play_tones(tones):
    """
    Genera e riproduce una sequenza di toni.
    
    Args:
        tones: Lista di tuple (frequenza_hz, durata_ms, pausa_dopo_ms)
               Frequenza 0 = silenzio
    """
    try:
        filepath = os.path.join(_TEMP_DIR, 'kiln_beep.wav')
        sample_rate = 44100
        all_samples = b''
        
        for freq, duration_ms, pause_ms in tones:
            if freq > 0:
                all_samples += _generate_tone(freq, duration_ms, volume=0.6, sample_rate=sample_rate)
            if pause_ms > 0:
                # Silenzio
                silence_samples = int(sample_rate * pause_ms / 1000)
                all_samples += b'\x00\x00' * silence_samples
        
        # Scrivi file WAV
        with wave.open(filepath, 'w') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(sample_rate)
            wf.writeframes(all_samples)
        
        # Riproduci con aplay su HDMI (card 1, device 0)
        subprocess.run(
            ['aplay', '-q', '-D', 'plughw:1,0', filepath],
            timeout=10,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        
        # Cleanup
        try:
            os.remove(filepath)
        except OSError:
            pass
            
    except Exception as e:
        # Audio non disponibile — fallisci silenziosamente
        print(f"🔇 Audio non disponibile: {e}")


def _play_async(tones):
    """Riproduce toni in un thread separato (non blocca)"""
    t = threading.Thread(target=_play_tones, args=(tones,), daemon=True)
    t.start()


# ===== SUONI DI SISTEMA =====

def beep_startup():
    """
    Beep avvio sistema: 2 toni brevi ascendenti
    ♪ bip-BIP (conferma avvio ok)
    """
    _play_async([
        (800, 120, 80),    # tono basso breve
        (1200, 150, 0),    # tono alto leggermente più lungo
    ])


def beep_program_start():
    """
    Beep avvio programma: 3 toni ascendenti rapidi
    ♪ bip-bip-BIP (qualcosa sta partendo)
    """
    _play_async([
        (600, 100, 60),
        (900, 100, 60),
        (1200, 150, 0),
    ])


def beep_program_complete():
    """
    Beep programma completato: melodia positiva
    ♪ BIP-bip-BIP-BIIP (successo, festivo)
    """
    _play_async([
        (800, 120, 60),
        (1000, 120, 60),
        (1200, 120, 60),
        (1600, 250, 0),
    ])


def beep_program_stopped():
    """
    Beep programma fermato: 2 toni discendenti
    ♪ BIP-bop (interruzione)
    """
    _play_async([
        (1000, 150, 80),
        (600, 200, 0),
    ])


def beep_autotuning_start():
    """
    Beep avvio autotuning: 3 toni staccati uguali
    ♪ bip-bip-bip (test in corso)
    """
    _play_async([
        (1000, 100, 120),
        (1000, 100, 120),
        (1000, 100, 0),
    ])


def beep_autotuning_complete():
    """
    Beep autotuning completato: scala ascendente 4 note
    ♪ do-re-mi-FA (risultato pronto)
    """
    _play_async([
        (523, 120, 40),   # Do
        (659, 120, 40),   # Mi
        (784, 120, 40),   # Sol
        (1047, 300, 0),   # Do alto (lungo)
    ])


def beep_error():
    """
    Beep errore: 3 toni bassi rapidi
    ♪ bop-bop-bop (attenzione!)
    """
    _play_async([
        (400, 150, 100),
        (400, 150, 100),
        (400, 200, 0),
    ])


def beep_emergency():
    """
    Beep emergenza: tono lungo grave
    ♪ BOOOOP (allarme)
    """
    _play_async([
        (300, 500, 200),
        (300, 500, 0),
    ])
