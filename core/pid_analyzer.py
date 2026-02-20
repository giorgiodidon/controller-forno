"""
PID Analyzer - Analisi performance PID dai log delle cotture
Segmenta per fasce di temperatura e calcola metriche di qualità controllo.

Metriche calcolate per fascia:
  - Overshoot: superamento massimo del setpoint (%)
  - Errore medio (MAE): errore assoluto medio in °C
  - Errore RMS: errore quadratico medio in °C
  - Oscillation Index: frequenza inversioni di segno dell'errore
  - Settling Time: tempo per entrare in banda di tolleranza
  - Tracking Error: errore durante le rampe (non in hold)
"""

import json
import os
import math
from datetime import datetime
from config import LOGS_DIR


# Fasce di temperatura per analisi (coerenti con pid_adaptive.py)
ANALYSIS_BANDS = [0, 200, 400, 600, 800, 1000, 1200]

# Soglie qualità
QUALITY_THRESHOLDS = {
    'overshoot_good': 5.0,       # °C - overshoot accettabile
    'overshoot_bad': 15.0,       # °C - overshoot problematico
    'mae_good': 3.0,             # °C - errore medio accettabile
    'mae_bad': 10.0,             # °C - errore medio problematico
    'rms_good': 5.0,             # °C
    'rms_bad': 15.0,             # °C
    'oscillation_good': 0.1,     # Indice basso = stabile
    'oscillation_bad': 0.3,      # Indice alto = oscillante
}


class FiringAnalysis:
    """Risultato analisi di una singola cottura"""
    
    def __init__(self, filename):
        self.filename = filename
        self.program_name = ""
        self.date = ""
        self.duration_minutes = 0
        self.total_samples = 0
        self.band_metrics = {}   # {band: {overshoot, mae, rms, ...}}
        self.overall_score = 0   # 0-100
        self.suggestions = []    # Lista suggerimenti per fascia
    
    def to_dict(self):
        return {
            'filename': self.filename,
            'program_name': self.program_name,
            'date': self.date,
            'duration_minutes': round(self.duration_minutes, 1),
            'total_samples': self.total_samples,
            'band_metrics': self.band_metrics,
            'overall_score': self.overall_score,
            'suggestions': self.suggestions
        }


class PIDAnalyzer:
    """
    Analizza log delle cotture e produce metriche performance PID.
    """
    
    def __init__(self):
        self.analyses = []  # Storico analisi
        os.makedirs(LOGS_DIR, exist_ok=True)
    
    def analyze_firing(self, log_filepath):
        """
        Analizza un singolo file di log cottura.
        
        Args:
            log_filepath (str): Path al file JSON del log
            
        Returns:
            FiringAnalysis: Risultato analisi, o None se errore
        """
        try:
            with open(log_filepath, 'r') as f:
                log_data = json.load(f)
        except Exception as e:
            print(f"❌ Errore lettura log {log_filepath}: {e}")
            return None
        
        filename = os.path.basename(log_filepath)
        analysis = FiringAnalysis(filename)
        
        # Estrai metadati
        analysis.program_name = log_data.get('program_name', 'Sconosciuto')
        analysis.date = log_data.get('start_time', '')
        
        # Estrai dati temperatura
        temperatures = log_data.get('temperatures', [])
        if len(temperatures) < 10:
            print(f"⚠️ Log {filename}: troppi pochi campioni ({len(temperatures)})")
            return None
        
        analysis.total_samples = len(temperatures)
        analysis.duration_minutes = temperatures[-1].get('time', 0) if temperatures else 0
        
        # Segmenta per fasce di temperatura e analizza
        band_data = self._segment_by_band(temperatures)
        
        for band, samples in band_data.items():
            if len(samples) < 5:
                continue  # Skip fasce con pochi dati
            
            metrics = self._calculate_band_metrics(samples, band)
            analysis.band_metrics[band] = metrics
        
        # Calcola score complessivo e suggerimenti
        analysis.overall_score = self._calculate_overall_score(analysis.band_metrics)
        analysis.suggestions = self._generate_suggestions(analysis.band_metrics)
        
        # Salva analisi
        self.analyses.append(analysis)
        self._save_analysis(analysis)
        
        print(f"📊 Analisi completata: {filename}")
        print(f"   Score: {analysis.overall_score}/100")
        print(f"   Fasce analizzate: {len(analysis.band_metrics)}")
        if analysis.suggestions:
            print(f"   Suggerimenti: {len(analysis.suggestions)}")
        
        return analysis
    
    def analyze_all_logs(self):
        """
        Analizza tutti i log nella directory.
        
        Returns:
            list: Lista di FiringAnalysis
        """
        results = []
        
        if not os.path.exists(LOGS_DIR):
            return results
        
        for filename in sorted(os.listdir(LOGS_DIR)):
            # Solo file di esecuzione programma (non autotuning o analisi)
            if filename.startswith('execution_') and filename.endswith('.json'):
                filepath = os.path.join(LOGS_DIR, filename)
                analysis = self.analyze_firing(filepath)
                if analysis:
                    results.append(analysis)
        
        print(f"\n📊 Analizzati {len(results)} log cottura")
        return results
    
    def get_latest_analysis(self):
        """Ritorna analisi più recente"""
        if self.analyses:
            return self.analyses[-1]
        return None
    
    def _segment_by_band(self, temperatures):
        """
        Segmenta campioni per fascia di temperatura.
        Usa il setpoint per determinare la fascia (non la temp attuale).
        
        Returns:
            dict: {band_temp: [samples]}
        """
        band_data = {band: [] for band in ANALYSIS_BANDS}
        
        for sample in temperatures:
            setpoint = sample.get('setpoint', 0)
            temp = sample.get('temp', 0)
            
            # Trova fascia appropriata basata sul setpoint
            assigned_band = ANALYSIS_BANDS[0]
            for band in ANALYSIS_BANDS:
                if setpoint >= band:
                    assigned_band = band
            
            band_data[assigned_band].append(sample)
        
        return band_data
    
    def _calculate_band_metrics(self, samples, band):
        """
        Calcola metriche per una fascia di temperatura.
        
        Args:
            samples: Lista campioni della fascia
            band: Fascia temperatura
            
        Returns:
            dict: Metriche calcolate
        """
        errors = []
        abs_errors = []
        squared_errors = []
        sign_changes = 0
        prev_sign = None
        
        max_overshoot = 0
        settling_samples = 0
        in_tolerance = False
        tolerance = 5.0  # °C tolleranza per settling
        
        for sample in samples:
            temp = sample.get('temp', 0)
            setpoint = sample.get('setpoint', 0)
            
            if setpoint == 0:
                continue
            
            error = temp - setpoint  # Positivo = sopra setpoint
            errors.append(error)
            abs_errors.append(abs(error))
            squared_errors.append(error ** 2)
            
            # Overshoot (solo positivo = sopra setpoint)
            if error > max_overshoot:
                max_overshoot = error
            
            # Conta inversioni segno errore (oscillazione)
            current_sign = 1 if error >= 0 else -1
            if prev_sign is not None and current_sign != prev_sign:
                sign_changes += 1
            prev_sign = current_sign
            
            # Settling: conta campioni fuori tolleranza
            if abs(error) > tolerance:
                settling_samples += 1
                in_tolerance = False
            else:
                in_tolerance = True
        
        n = len(errors)
        if n == 0:
            return self._empty_metrics()
        
        # Calcola metriche
        mae = sum(abs_errors) / n
        rms = math.sqrt(sum(squared_errors) / n)
        oscillation_index = sign_changes / n if n > 1 else 0
        settling_percent = (settling_samples / n) * 100
        
        # Bias (errore medio con segno - indica se sistematicamente sopra/sotto)
        bias = sum(errors) / n
        
        # Qualifica
        quality = self._rate_quality(mae, rms, max_overshoot, oscillation_index)
        
        return {
            'samples': n,
            'overshoot': round(max_overshoot, 1),
            'mae': round(mae, 2),
            'rms': round(rms, 2),
            'bias': round(bias, 2),
            'oscillation_index': round(oscillation_index, 4),
            'settling_out_percent': round(settling_percent, 1),
            'quality': quality
        }
    
    def _empty_metrics(self):
        """Metriche vuote per fasce senza dati"""
        return {
            'samples': 0,
            'overshoot': 0, 'mae': 0, 'rms': 0, 'bias': 0,
            'oscillation_index': 0, 'settling_out_percent': 0,
            'quality': 'no_data'
        }
    
    def _rate_quality(self, mae, rms, overshoot, osc_index):
        """
        Classifica qualità del controllo.
        
        Returns:
            str: 'excellent', 'good', 'acceptable', 'poor'
        """
        score = 0
        
        # MAE
        if mae <= QUALITY_THRESHOLDS['mae_good']:
            score += 3
        elif mae <= QUALITY_THRESHOLDS['mae_bad']:
            score += 1
        
        # Overshoot
        if overshoot <= QUALITY_THRESHOLDS['overshoot_good']:
            score += 3
        elif overshoot <= QUALITY_THRESHOLDS['overshoot_bad']:
            score += 1
        
        # Oscillazione
        if osc_index <= QUALITY_THRESHOLDS['oscillation_good']:
            score += 2
        elif osc_index <= QUALITY_THRESHOLDS['oscillation_bad']:
            score += 1
        
        if score >= 7:
            return 'excellent'
        elif score >= 5:
            return 'good'
        elif score >= 3:
            return 'acceptable'
        else:
            return 'poor'
    
    def _calculate_overall_score(self, band_metrics):
        """
        Calcola score complessivo 0-100 pesato per numero campioni.
        """
        if not band_metrics:
            return 0
        
        total_score = 0
        total_weight = 0
        
        quality_scores = {
            'excellent': 100,
            'good': 75,
            'acceptable': 50,
            'poor': 25,
            'no_data': 0
        }
        
        for band, metrics in band_metrics.items():
            samples = metrics.get('samples', 0)
            quality = metrics.get('quality', 'no_data')
            
            if samples > 0:
                total_score += quality_scores.get(quality, 0) * samples
                total_weight += samples
        
        if total_weight == 0:
            return 0
        
        return round(total_score / total_weight)
    
    def _generate_suggestions(self, band_metrics):
        """
        Genera suggerimenti concreti di aggiustamento PID per fascia.
        
        Returns:
            list: [{band, param, direction, magnitude, reason}]
        """
        suggestions = []
        
        for band, metrics in band_metrics.items():
            if metrics.get('quality') in ('no_data', 'excellent'):
                continue
            
            overshoot = metrics.get('overshoot', 0)
            mae = metrics.get('mae', 0)
            bias = metrics.get('bias', 0)
            osc_index = metrics.get('oscillation_index', 0)
            
            # Overshoot alto → riduci Kp
            if overshoot > QUALITY_THRESHOLDS['overshoot_bad']:
                suggestions.append({
                    'band': band,
                    'param': 'Kp',
                    'direction': 'decrease',
                    'magnitude': 'large',   # -10%
                    'reason': f'Overshoot {overshoot:.1f}°C nella fascia {band}-{band+200}°C'
                })
            elif overshoot > QUALITY_THRESHOLDS['overshoot_good']:
                suggestions.append({
                    'band': band,
                    'param': 'Kp',
                    'direction': 'decrease',
                    'magnitude': 'small',   # -5%
                    'reason': f'Overshoot moderato {overshoot:.1f}°C nella fascia {band}-{band+200}°C'
                })
            
            # Errore stazionario (bias) → aggiusta Ki
            if bias > 5.0:
                # Sistematicamente SOPRA setpoint → Ki troppo alto o Kp troppo alto
                suggestions.append({
                    'band': band,
                    'param': 'Ki',
                    'direction': 'decrease',
                    'magnitude': 'small',
                    'reason': f'Bias positivo {bias:.1f}°C (sopra setpoint) in fascia {band}°C'
                })
            elif bias < -5.0:
                # Sistematicamente SOTTO setpoint → Ki troppo basso
                suggestions.append({
                    'band': band,
                    'param': 'Ki',
                    'direction': 'increase',
                    'magnitude': 'small',
                    'reason': f'Bias negativo {bias:.1f}°C (sotto setpoint) in fascia {band}°C'
                })
            
            # Oscillazione alta → riduci Kp e/o Kd
            if osc_index > QUALITY_THRESHOLDS['oscillation_bad']:
                suggestions.append({
                    'band': band,
                    'param': 'Kp',
                    'direction': 'decrease',
                    'magnitude': 'small',
                    'reason': f'Oscillazione alta ({osc_index:.3f}) in fascia {band}°C'
                })
                suggestions.append({
                    'band': band,
                    'param': 'Kd',
                    'direction': 'decrease',
                    'magnitude': 'small',
                    'reason': f'Oscillazione alta, riduci derivativo in fascia {band}°C'
                })
            
            # MAE alto senza oscillazione → aumenta Kp (risposta più aggressiva)
            if (mae > QUALITY_THRESHOLDS['mae_bad'] and 
                osc_index < QUALITY_THRESHOLDS['oscillation_good']):
                suggestions.append({
                    'band': band,
                    'param': 'Kp',
                    'direction': 'increase',
                    'magnitude': 'small',
                    'reason': f'Errore medio alto ({mae:.1f}°C) senza oscillazione in fascia {band}°C'
                })
        
        return suggestions
    
    def _save_analysis(self, analysis):
        """Salva risultato analisi su file"""
        filename = f"analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = os.path.join(LOGS_DIR, filename)
        
        try:
            with open(filepath, 'w') as f:
                json.dump(analysis.to_dict(), f, indent=2)
        except Exception as e:
            print(f"⚠️ Errore salvataggio analisi: {e}")
    
    def get_aggregated_metrics(self):
        """
        Aggrega metriche da tutte le analisi disponibili.
        Utile per avere un quadro complessivo multi-cottura.
        
        Returns:
            dict: {band: {avg_mae, avg_overshoot, ...}}
        """
        if not self.analyses:
            return {}
        
        # Accumula metriche per fascia
        accumulated = {band: {
            'mae_sum': 0, 'overshoot_sum': 0, 'rms_sum': 0,
            'bias_sum': 0, 'osc_sum': 0, 'count': 0
        } for band in ANALYSIS_BANDS}
        
        for analysis in self.analyses:
            for band, metrics in analysis.band_metrics.items():
                if metrics.get('samples', 0) > 0:
                    b = int(band)
                    accumulated[b]['mae_sum'] += metrics['mae']
                    accumulated[b]['overshoot_sum'] += metrics['overshoot']
                    accumulated[b]['rms_sum'] += metrics['rms']
                    accumulated[b]['bias_sum'] += metrics['bias']
                    accumulated[b]['osc_sum'] += metrics['oscillation_index']
                    accumulated[b]['count'] += 1
        
        # Media
        result = {}
        for band, acc in accumulated.items():
            if acc['count'] > 0:
                n = acc['count']
                result[band] = {
                    'avg_mae': round(acc['mae_sum'] / n, 2),
                    'avg_overshoot': round(acc['overshoot_sum'] / n, 1),
                    'avg_rms': round(acc['rms_sum'] / n, 2),
                    'avg_bias': round(acc['bias_sum'] / n, 2),
                    'avg_oscillation': round(acc['osc_sum'] / n, 4),
                    'firings_analyzed': n
                }
        
        return result
