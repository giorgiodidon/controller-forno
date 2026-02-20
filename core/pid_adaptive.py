"""
PID Adattivo - Gain Scheduling basato su temperatura
Apprende dai dati reali delle cotture per ottimizzare i parametri PID
per fascia di temperatura.

Funzionamento:
  - Mantiene una lookup table temperatura → (Kp, Ki, Kd)
  - Interpola linearmente tra le fasce per transizioni morbide
  - Aggiorna i parametri del PID controller in tempo reale
  - Persistenza su file JSON
  - Hard-cap di sicurezza su tutti i parametri
"""

import json
import os
import time
from datetime import datetime
from config import LOGS_DIR, PID_KP, PID_KI, PID_KD


# File persistenza tabella adattiva
ADAPTIVE_TABLE_FILE = os.path.join(LOGS_DIR, 'pid_adaptive_table.json')

# Fasce di temperatura (°C) - bordi inferiori
TEMP_BANDS = [0, 200, 400, 600, 800, 1000, 1200]

# Hard-cap sicurezza: i parametri non possono MAI uscire da questi range
# Indipendentemente da cosa suggerisce il learner
SAFETY_LIMITS = {
    'Kp': {'min': 0.5, 'max': 10.0},
    'Ki': {'min': 0.001, 'max': 0.2},
    'Kd': {'min': 0.0, 'max': 8.0}
}

# Massima deviazione consentita rispetto ai valori base (autotuning)
# Il learner non può modificare più di questa percentuale
MAX_DEVIATION_PERCENT = 50  # ±50% max dal valore base


class AdaptivePIDTable:
    """
    Tabella adattiva temperatura → parametri PID
    
    Ogni fascia ha:
      - base: parametri originali (da autotuning, immutabili)
      - current: parametri attuali (modificati dal learner)
      - history: storico modifiche con timestamp e motivazione
    """
    
    def __init__(self):
        self.bands = {}       # {temp_band: {base, current, history}}
        self.metadata = {}    # Info generali
        self.is_loaded = False
        
        # Carica tabella esistente o crea default
        self._load_or_create()
    
    def _load_or_create(self):
        """Carica tabella da file o crea con valori default"""
        if os.path.exists(ADAPTIVE_TABLE_FILE):
            try:
                with open(ADAPTIVE_TABLE_FILE, 'r') as f:
                    data = json.load(f)
                
                self.bands = data.get('bands', {})
                self.metadata = data.get('metadata', {})
                
                # Converti chiavi stringa → int (JSON salva come stringa)
                self.bands = {int(k): v for k, v in self.bands.items()}
                
                self.is_loaded = True
                print(f"📊 Tabella PID adattiva caricata ({len(self.bands)} fasce)")
                return
                
            except Exception as e:
                print(f"⚠️ Errore caricamento tabella adattiva: {e}")
                print("   Creo tabella default...")
        
        # Crea tabella default con parametri attuali da config
        self._create_default_table()
    
    def _create_default_table(self):
        """Crea tabella con valori default da autotuning/config"""
        default_params = {
            'Kp': PID_KP,
            'Ki': PID_KI,
            'Kd': PID_KD
        }
        
        self.bands = {}
        for temp in TEMP_BANDS:
            self.bands[temp] = {
                'base': dict(default_params),       # Immutabile (riferimento)
                'current': dict(default_params),    # Modificabile dal learner
                'history': []                        # Storico modifiche
            }
        
        self.metadata = {
            'created': datetime.now().isoformat(),
            'last_updated': datetime.now().isoformat(),
            'source': 'default_from_config',
            'base_params': default_params,
            'total_adjustments': 0,
            'total_firings_analyzed': 0
        }
        
        self._save()
        self.is_loaded = True
        print(f"📊 Tabella PID adattiva creata (default Kp={PID_KP}, Ki={PID_KI}, Kd={PID_KD})")
    
    def set_base_from_autotuning(self, kp, ki, kd):
        """
        Aggiorna i valori BASE di tutte le fasce con risultati autotuning.
        Chiamare dopo un autotuning completato.
        Resetta anche i valori current a quelli nuovi.
        
        Args:
            kp, ki, kd: Parametri da autotuning
        """
        new_base = {'Kp': kp, 'Ki': ki, 'Kd': kd}
        
        for temp in TEMP_BANDS:
            self.bands[temp]['base'] = dict(new_base)
            self.bands[temp]['current'] = dict(new_base)
            self.bands[temp]['history'].append({
                'timestamp': datetime.now().isoformat(),
                'action': 'autotuning_reset',
                'old_params': None,
                'new_params': dict(new_base),
                'reason': 'Nuovi parametri da autotuning'
            })
        
        self.metadata['last_updated'] = datetime.now().isoformat()
        self.metadata['source'] = f'autotuning_{datetime.now().strftime("%Y%m%d")}'
        self.metadata['base_params'] = dict(new_base)
        
        self._save()
        print(f"🎯 Tabella adattiva aggiornata da autotuning: Kp={kp:.4f} Ki={ki:.6f} Kd={kd:.2f}")
    
    def get_params_for_temp(self, temperature):
        """
        Ritorna parametri PID interpolati per la temperatura data.
        Interpolazione lineare tra la fascia inferiore e superiore.
        
        Args:
            temperature (float): Temperatura attuale in °C
            
        Returns:
            dict: {'Kp': float, 'Ki': float, 'Kd': float}
        """
        sorted_bands = sorted(self.bands.keys())
        
        # Sotto la fascia minima
        if temperature <= sorted_bands[0]:
            return dict(self.bands[sorted_bands[0]]['current'])
        
        # Sopra la fascia massima
        if temperature >= sorted_bands[-1]:
            return dict(self.bands[sorted_bands[-1]]['current'])
        
        # Trova le due fasce tra cui interpolare
        lower_band = sorted_bands[0]
        upper_band = sorted_bands[-1]
        
        for i in range(len(sorted_bands) - 1):
            if sorted_bands[i] <= temperature < sorted_bands[i + 1]:
                lower_band = sorted_bands[i]
                upper_band = sorted_bands[i + 1]
                break
        
        # Fattore interpolazione (0.0 = lower, 1.0 = upper)
        band_range = upper_band - lower_band
        if band_range == 0:
            factor = 0.0
        else:
            factor = (temperature - lower_band) / band_range
        
        # Interpola ogni parametro
        lower_params = self.bands[lower_band]['current']
        upper_params = self.bands[upper_band]['current']
        
        interpolated = {}
        for param in ['Kp', 'Ki', 'Kd']:
            interpolated[param] = lower_params[param] + factor * (upper_params[param] - lower_params[param])
        
        return interpolated
    
    def update_band(self, temp_band, new_kp, new_ki, new_kd, reason=""):
        """
        Aggiorna parametri di una fascia specifica.
        Applica hard-cap di sicurezza e limite deviazione dal base.
        
        Args:
            temp_band (int): Fascia temperatura (deve essere in TEMP_BANDS)
            new_kp, new_ki, new_kd: Nuovi parametri proposti
            reason (str): Motivazione dell'aggiornamento
            
        Returns:
            dict: Parametri effettivamente applicati (dopo capping)
        """
        if temp_band not in self.bands:
            print(f"⚠️ Fascia {temp_band}°C non valida")
            return None
        
        old_params = dict(self.bands[temp_band]['current'])
        base_params = self.bands[temp_band]['base']
        
        # Applica limiti
        proposed = {'Kp': new_kp, 'Ki': new_ki, 'Kd': new_kd}
        capped = {}
        
        for param, value in proposed.items():
            # Hard-cap assoluto
            value = max(SAFETY_LIMITS[param]['min'], 
                       min(SAFETY_LIMITS[param]['max'], value))
            
            # Limite deviazione dal base
            base_val = base_params[param]
            if base_val > 0:
                max_val = base_val * (1 + MAX_DEVIATION_PERCENT / 100)
                min_val = base_val * (1 - MAX_DEVIATION_PERCENT / 100)
                value = max(min_val, min(max_val, value))
            
            # Secondo hard-cap dopo deviazione (per sicurezza)
            value = max(SAFETY_LIMITS[param]['min'],
                       min(SAFETY_LIMITS[param]['max'], value))
            
            capped[param] = round(value, 6)
        
        # Applica
        self.bands[temp_band]['current'] = capped
        self.bands[temp_band]['history'].append({
            'timestamp': datetime.now().isoformat(),
            'action': 'learner_update',
            'old_params': old_params,
            'new_params': dict(capped),
            'reason': reason
        })
        
        self.metadata['last_updated'] = datetime.now().isoformat()
        self.metadata['total_adjustments'] = self.metadata.get('total_adjustments', 0) + 1
        
        self._save()
        
        print(f"📊 Fascia {temp_band}°C aggiornata: "
              f"Kp={capped['Kp']:.4f} Ki={capped['Ki']:.6f} Kd={capped['Kd']:.2f} "
              f"({reason})")
        
        return capped
    
    def rollback_band(self, temp_band):
        """
        Riporta una fascia ai valori base (autotuning originale)
        
        Args:
            temp_band (int): Fascia da resettare
        """
        if temp_band not in self.bands:
            return
        
        base = self.bands[temp_band]['base']
        old = dict(self.bands[temp_band]['current'])
        
        self.bands[temp_band]['current'] = dict(base)
        self.bands[temp_band]['history'].append({
            'timestamp': datetime.now().isoformat(),
            'action': 'rollback',
            'old_params': old,
            'new_params': dict(base),
            'reason': 'Rollback manuale a valori base'
        })
        
        self._save()
        print(f"↩️ Fascia {temp_band}°C → rollback a base: Kp={base['Kp']:.4f}")
    
    def rollback_all(self):
        """Riporta TUTTE le fasce ai valori base"""
        for temp in TEMP_BANDS:
            self.rollback_band(temp)
        print("↩️ Tutte le fasce resettate ai valori base")
    
    def get_table_summary(self):
        """Ritorna tabella completa per API/display"""
        summary = {
            'metadata': self.metadata,
            'bands': {}
        }
        
        for temp in sorted(self.bands.keys()):
            band = self.bands[temp]
            base = band['base']
            curr = band['current']
            
            # Calcola deviazione percentuale dal base
            deviation = {}
            for param in ['Kp', 'Ki', 'Kd']:
                if base[param] > 0:
                    dev = ((curr[param] - base[param]) / base[param]) * 100
                    deviation[param] = round(dev, 1)
                else:
                    deviation[param] = 0.0
            
            summary['bands'][temp] = {
                'base': base,
                'current': curr,
                'deviation_percent': deviation,
                'adjustments': len(band['history'])
            }
        
        return summary
    
    def _save(self):
        """Salva tabella su file JSON"""
        os.makedirs(LOGS_DIR, exist_ok=True)
        
        # Converti chiavi int → str per JSON
        data = {
            'metadata': self.metadata,
            'bands': {str(k): v for k, v in self.bands.items()}
        }
        
        try:
            with open(ADAPTIVE_TABLE_FILE, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"❌ Errore salvataggio tabella adattiva: {e}")


class AdaptivePIDManager:
    """
    Manager che collega la tabella adattiva al PID controller.
    Chiamato dal loop principale per aggiornare i parametri in tempo reale.
    """
    
    def __init__(self, pid_controller):
        """
        Args:
            pid_controller: Istanza di PIDController
        """
        self.pid = pid_controller
        self.table = AdaptivePIDTable()
        
        # Stato
        self.enabled = True
        self.current_band = None          # Fascia corrente
        self.last_update_temp = None      # Ultima temp a cui ho aggiornato
        self.update_threshold = 10        # Aggiorna solo se temp cambia di >10°C
        self.last_params = None           # Ultimi parametri applicati
        
        print("🧠 PID Adattivo inizializzato")
    
    def update_tunings(self, current_temp):
        """
        Aggiorna i parametri PID in base alla temperatura corrente.
        Chiamare ad ogni ciclo del loop principale.
        Aggiorna solo se la temperatura è cambiata significativamente.
        
        Args:
            current_temp (float): Temperatura attuale in °C
        """
        if not self.enabled:
            return
        
        # Evita aggiornamenti troppo frequenti
        if (self.last_update_temp is not None and 
            abs(current_temp - self.last_update_temp) < self.update_threshold):
            return
        
        # Ottieni parametri interpolati
        params = self.table.get_params_for_temp(current_temp)
        
        # Applica al PID controller
        self.pid.set_tunings(params['Kp'], params['Ki'], params['Kd'])
        
        self.last_update_temp = current_temp
        self.last_params = params
        
        # Determina fascia corrente
        sorted_bands = sorted(self.table.bands.keys())
        for band in reversed(sorted_bands):
            if current_temp >= band:
                self.current_band = band
                break
    
    def enable(self):
        """Abilita PID adattivo"""
        self.enabled = True
        print("🧠 PID Adattivo ABILITATO")
    
    def disable(self):
        """Disabilita PID adattivo (usa parametri fissi da config)"""
        self.enabled = False
        self.pid.set_tunings(PID_KP, PID_KI, PID_KD)
        print("🧠 PID Adattivo DISABILITATO (parametri fissi)")
    
    def get_status(self):
        """Stato per API"""
        return {
            'enabled': self.enabled,
            'current_band': self.current_band,
            'last_update_temp': self.last_update_temp,
            'last_params': self.last_params,
            'table_summary': self.table.get_table_summary()
        }
