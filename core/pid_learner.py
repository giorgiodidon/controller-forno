"""
PID Learner - Apprendimento incrementale dai dati delle cotture
Prende i suggerimenti del PIDAnalyzer e li applica alla tabella adattiva
con regole conservative e limiti di sicurezza.

Principi:
  - Aggiustamenti piccoli e graduali (mai salti bruschi)
  - Storico completo di ogni modifica per rollback
  - Mai più di MAX_ADJUSTMENT_PERCENT per iterazione
  - Richiede conferma umana opzionale (modalità suggest vs auto)
  - Convergenza: riduce aggiustamenti se qualità già buona
"""

import json
import os
from datetime import datetime
from config import LOGS_DIR


# File storico apprendimento
LEARNING_HISTORY_FILE = os.path.join(LOGS_DIR, 'pid_learning_history.json')

# Percentuali aggiustamento per magnitude
ADJUSTMENT_PERCENT = {
    'small': 5,    # ±5%
    'large': 10,   # ±10%
}

# Dopo quante cotture analizzate il learner può agire
MIN_FIRINGS_TO_LEARN = 2

# Se la qualità è già 'good' o 'excellent', non toccare
SKIP_IF_QUALITY = ('excellent', 'good')


class PIDLearner:
    """
    Applica apprendimento incrementale alla tabella PID adattiva.
    """
    
    def __init__(self, adaptive_table):
        """
        Args:
            adaptive_table: Istanza di AdaptivePIDTable
        """
        self.table = adaptive_table
        self.mode = 'suggest'  # 'suggest' = solo suggerisce, 'auto' = applica
        self.history = []      # Storico completo apprendimento
        self.pending_suggestions = []  # Suggerimenti in attesa di conferma
        
        self._load_history()
    
    def _load_history(self):
        """Carica storico apprendimento"""
        if os.path.exists(LEARNING_HISTORY_FILE):
            try:
                with open(LEARNING_HISTORY_FILE, 'r') as f:
                    data = json.load(f)
                self.history = data.get('history', [])
                self.mode = data.get('mode', 'suggest')
            except Exception:
                self.history = []
    
    def _save_history(self):
        """Salva storico"""
        os.makedirs(LOGS_DIR, exist_ok=True)
        data = {
            'mode': self.mode,
            'last_updated': datetime.now().isoformat(),
            'total_adjustments': len(self.history),
            'history': self.history[-100:]  # Ultimi 100 per non crescere troppo
        }
        try:
            with open(LEARNING_HISTORY_FILE, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"⚠️ Errore salvataggio history learner: {e}")
    
    def process_analysis(self, analysis):
        """
        Processa il risultato di un'analisi e genera/applica aggiustamenti.
        
        Args:
            analysis: FiringAnalysis dal PIDAnalyzer
            
        Returns:
            dict: {applied: int, skipped: int, pending: int, details: list}
        """
        suggestions = analysis.suggestions
        
        if not suggestions:
            print("🧠 Learner: nessun suggerimento dall'analisi")
            return {'applied': 0, 'skipped': 0, 'pending': 0, 'details': []}
        
        print(f"\n🧠 PID Learner: elaboro {len(suggestions)} suggerimenti...")
        
        # Filtra suggerimenti per fasce già buone
        filtered = self._filter_suggestions(suggestions, analysis.band_metrics)
        
        if self.mode == 'auto':
            result = self._apply_suggestions(filtered)
        else:
            result = self._queue_suggestions(filtered)
        
        return result
    
    def process_all_analyses(self, analyses):
        """
        Processa multiple analisi e genera suggerimenti aggregati.
        Utile quando si analizzano tutte le cotture passate.
        
        Args:
            analyses: Lista di FiringAnalysis
            
        Returns:
            dict: Risultato aggregato
        """
        if len(analyses) < MIN_FIRINGS_TO_LEARN:
            print(f"🧠 Learner: servono almeno {MIN_FIRINGS_TO_LEARN} cotture "
                  f"(disponibili: {len(analyses)})")
            return {'applied': 0, 'skipped': 0, 'pending': 0, 'details': []}
        
        # Usa l'analisi più recente come base per i suggerimenti,
        # ma verifica coerenza con le precedenti
        latest = analyses[-1]
        
        # Verifica se i problemi sono ricorrenti (non episodici)
        confirmed_suggestions = self._confirm_recurring(latest.suggestions, analyses)
        
        if self.mode == 'auto':
            return self._apply_suggestions(confirmed_suggestions)
        else:
            return self._queue_suggestions(confirmed_suggestions)
    
    def _filter_suggestions(self, suggestions, band_metrics):
        """Filtra suggerimenti: salta fasce con qualità già buona"""
        filtered = []
        
        for sugg in suggestions:
            band = sugg['band']
            metrics = band_metrics.get(band, {})
            quality = metrics.get('quality', 'no_data')
            
            if quality in SKIP_IF_QUALITY:
                continue
            
            filtered.append(sugg)
        
        skipped = len(suggestions) - len(filtered)
        if skipped > 0:
            print(f"   ✓ Saltati {skipped} suggerimenti (fasce già buone)")
        
        return filtered
    
    def _confirm_recurring(self, suggestions, analyses):
        """
        Verifica che un problema sia ricorrente in almeno 2 cotture.
        Evita di reagire a problemi episodici.
        
        Returns:
            list: Solo suggerimenti confermati
        """
        if len(analyses) < 2:
            return suggestions
        
        # Conta quante cotture hanno problemi nella stessa fascia+parametro
        problem_count = {}  # (band, param, direction) → count
        
        for analysis in analyses[-5:]:  # Ultime 5 cotture
            for sugg in analysis.suggestions:
                key = (sugg['band'], sugg['param'], sugg['direction'])
                problem_count[key] = problem_count.get(key, 0) + 1
        
        # Conferma solo se il problema appare in almeno 2 cotture
        confirmed = []
        for sugg in suggestions:
            key = (sugg['band'], sugg['param'], sugg['direction'])
            if problem_count.get(key, 0) >= 2:
                confirmed.append(sugg)
        
        filtered = len(suggestions) - len(confirmed)
        if filtered > 0:
            print(f"   ✓ Filtrati {filtered} problemi episodici (non ricorrenti)")
        
        return confirmed
    
    def _apply_suggestions(self, suggestions):
        """
        Applica suggerimenti alla tabella (modalità auto).
        
        Returns:
            dict: Risultato applicazione
        """
        applied = 0
        skipped = 0
        details = []
        
        # Raggruppa per fascia (evita aggiustamenti multipli sullo stesso param)
        by_band = {}
        for sugg in suggestions:
            band = sugg['band']
            if band not in by_band:
                by_band[band] = []
            by_band[band].append(sugg)
        
        for band, band_suggestions in by_band.items():
            # Prendi i parametri attuali della fascia
            current = self.table.bands[band]['current']
            new_params = dict(current)
            reasons = []
            
            # Applica ogni suggerimento (se non conflittuale)
            applied_params = set()
            
            for sugg in band_suggestions:
                param = sugg['param']
                
                # Evita aggiustamenti conflittuali sullo stesso parametro
                if param in applied_params:
                    skipped += 1
                    continue
                
                direction = sugg['direction']
                magnitude = sugg['magnitude']
                percent = ADJUSTMENT_PERCENT.get(magnitude, 5)
                
                # Calcola nuovo valore
                old_val = current[param]
                if direction == 'increase':
                    new_val = old_val * (1 + percent / 100)
                else:
                    new_val = old_val * (1 - percent / 100)
                
                new_params[param] = new_val
                applied_params.add(param)
                reasons.append(sugg['reason'])
            
            # Applica alla tabella (con safety capping interno)
            reason_str = "; ".join(reasons)
            result = self.table.update_band(
                band, 
                new_params['Kp'], new_params['Ki'], new_params['Kd'],
                reason=reason_str
            )
            
            if result:
                applied += len(applied_params)
                details.append({
                    'band': band,
                    'params_changed': list(applied_params),
                    'new_values': result,
                    'reasons': reasons
                })
                
                # Salva nello storico
                self.history.append({
                    'timestamp': datetime.now().isoformat(),
                    'band': band,
                    'old_params': dict(current),
                    'new_params': result,
                    'reasons': reasons,
                    'mode': 'auto'
                })
        
        self._save_history()
        
        print(f"\n🧠 Learner: {applied} aggiustamenti applicati, {skipped} saltati")
        
        return {
            'applied': applied,
            'skipped': skipped,
            'pending': 0,
            'details': details
        }
    
    def _queue_suggestions(self, suggestions):
        """
        Accoda suggerimenti per conferma umana (modalità suggest).
        """
        self.pending_suggestions = []
        
        for sugg in suggestions:
            band = sugg['band']
            param = sugg['param']
            current = self.table.bands[band]['current']
            
            direction = sugg['direction']
            magnitude = sugg['magnitude']
            percent = ADJUSTMENT_PERCENT.get(magnitude, 5)
            
            old_val = current[param]
            if direction == 'increase':
                new_val = old_val * (1 + percent / 100)
            else:
                new_val = old_val * (1 - percent / 100)
            
            self.pending_suggestions.append({
                'band': band,
                'param': param,
                'old_value': old_val,
                'new_value': round(new_val, 6),
                'change_percent': percent if direction == 'increase' else -percent,
                'reason': sugg['reason']
            })
        
        print(f"\n🧠 Learner: {len(self.pending_suggestions)} suggerimenti in attesa di conferma")
        
        return {
            'applied': 0,
            'skipped': 0,
            'pending': len(self.pending_suggestions),
            'details': self.pending_suggestions
        }
    
    def approve_pending(self):
        """
        Approva e applica tutti i suggerimenti in coda.
        Chiamato dall'utente via API.
        
        Returns:
            int: Numero aggiustamenti applicati
        """
        if not self.pending_suggestions:
            print("🧠 Nessun suggerimento in coda")
            return 0
        
        applied = 0
        
        # Raggruppa per fascia
        by_band = {}
        for sugg in self.pending_suggestions:
            band = sugg['band']
            if band not in by_band:
                by_band[band] = {}
            by_band[band][sugg['param']] = sugg
        
        for band, params in by_band.items():
            current = dict(self.table.bands[band]['current'])
            new_params = dict(current)
            reasons = []
            
            for param, sugg in params.items():
                new_params[param] = sugg['new_value']
                reasons.append(sugg['reason'])
            
            result = self.table.update_band(
                band,
                new_params['Kp'], new_params['Ki'], new_params['Kd'],
                reason="Approvazione manuale: " + "; ".join(reasons)
            )
            
            if result:
                applied += len(params)
                self.history.append({
                    'timestamp': datetime.now().isoformat(),
                    'band': band,
                    'old_params': current,
                    'new_params': result,
                    'reasons': reasons,
                    'mode': 'approved'
                })
        
        self.pending_suggestions = []
        self._save_history()
        
        print(f"✅ Applicati {applied} aggiustamenti approvati")
        return applied
    
    def reject_pending(self):
        """Rifiuta tutti i suggerimenti in coda"""
        count = len(self.pending_suggestions)
        self.pending_suggestions = []
        print(f"❌ Rifiutati {count} suggerimenti")
        return count
    
    def set_mode(self, mode):
        """
        Imposta modalità operativa.
        
        Args:
            mode: 'suggest' (richiede conferma) o 'auto' (applica automaticamente)
        """
        if mode not in ('suggest', 'auto'):
            print(f"⚠️ Modalità non valida: {mode}")
            return
        
        self.mode = mode
        self._save_history()
        print(f"🧠 Learner modalità: {mode}")
    
    def get_status(self):
        """Stato per API"""
        return {
            'mode': self.mode,
            'pending_suggestions': len(self.pending_suggestions),
            'total_adjustments': len(self.history),
            'pending_details': self.pending_suggestions,
            'last_adjustment': self.history[-1] if self.history else None
        }
