"""
Servizio Storage - Gestione programmi di cottura
"""

import json
import os
from datetime import datetime
from config import PROGRAMS_FILE, BACKUP_DIR


class StorageService:
    """
    Gestisce salvataggio/caricamento programmi su file JSON
    """
    
    def __init__(self, filepath=PROGRAMS_FILE):
        self.filepath = filepath
        
        # Crea directory se non esiste
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        os.makedirs(BACKUP_DIR, exist_ok=True)
        
        # Inizializza file se non esiste
        if not os.path.exists(filepath):
            self._save_programs({})
            print(f"📁 File programmi creato: {filepath}")
        else:
            print(f"📁 File programmi caricato: {filepath}")
    
    def load_programs(self):
        """
        Carica tutti i programmi dal file
        
        Returns:
            dict: Dizionario {nome_programma: dati_programma}
        """
        try:
            with open(self.filepath, 'r', encoding='utf-8') as f:
                programs = json.load(f)
            return programs
        except Exception as e:
            print(f"❌ Errore caricamento programmi: {e}")
            return {}
    
    def save_program(self, program_data):
        """
        Salva un singolo programma
        
        Args:
            program_data (dict): Dati programma con chiave 'name'
        
        Returns:
            bool: True se salvato con successo
        """
        try:
            programs = self.load_programs()
            
            name = program_data.get('name')
            if not name:
                print("❌ Nome programma mancante")
                return False
            
            # Aggiungi timestamp se non presente
            if 'created' not in program_data:
                program_data['created'] = datetime.now().isoformat()
            
            # Salva programma
            programs[name] = program_data
            
            self._save_programs(programs)
            print(f"💾 Programma salvato: {name}")
            return True
            
        except Exception as e:
            print(f"❌ Errore salvataggio programma: {e}")
            return False
    
    def get_program(self, name):
        """
        Carica un singolo programma
        
        Args:
            name (str): Nome programma
        
        Returns:
            dict: Dati programma o None se non trovato
        """
        programs = self.load_programs()
        return programs.get(name)
    
    def delete_program(self, name):
        """
        Elimina un programma
        
        Args:
            name (str): Nome programma
        
        Returns:
            bool: True se eliminato
        """
        try:
            programs = self.load_programs()
            
            if name in programs:
                del programs[name]
                self._save_programs(programs)
                print(f"🗑️ Programma eliminato: {name}")
                return True
            else:
                print(f"⚠️ Programma non trovato: {name}")
                return False
                
        except Exception as e:
            print(f"❌ Errore eliminazione programma: {e}")
            return False
    
    def list_programs(self):
        """
        Lista nomi tutti i programmi
        
        Returns:
            list: Nomi programmi ordinati
        """
        programs = self.load_programs()
        return sorted(programs.keys())
    
    def count_programs(self):
        """
        Conta programmi salvati
        
        Returns:
            int: Numero programmi
        """
        return len(self.load_programs())
    
    def create_backup(self):
        """
        Crea backup file programmi
        
        Returns:
            str: Path file backup
        """
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = os.path.join(BACKUP_DIR, f"programs_backup_{timestamp}.json")
            
            programs = self.load_programs()
            
            with open(backup_file, 'w', encoding='utf-8') as f:
                json.dump(programs, f, indent=2, ensure_ascii=False)
            
            print(f"📦 Backup creato: {backup_file}")
            return backup_file
            
        except Exception as e:
            print(f"❌ Errore creazione backup: {e}")
            return None
    
    def restore_backup(self, backup_file):
        """
        Ripristina da file backup
        
        Args:
            backup_file (str): Path file backup
        
        Returns:
            bool: True se ripristinato
        """
        try:
            with open(backup_file, 'r', encoding='utf-8') as f:
                programs = json.load(f)
            
            # Crea backup corrente prima di sovrascrivere
            self.create_backup()
            
            # Salva programmi da backup
            self._save_programs(programs)
            
            print(f"♻️ Backup ripristinato: {len(programs)} programmi")
            return True
            
        except Exception as e:
            print(f"❌ Errore ripristino backup: {e}")
            return False
    
    def _save_programs(self, programs):
        """
        Salva dizionario programmi su file
        
        Args:
            programs (dict): Dizionario programmi
        """
        with open(self.filepath, 'w', encoding='utf-8') as f:
            json.dump(programs, f, indent=2, ensure_ascii=False)
    
    def get_statistics(self):
        """
        Statistiche programmi
        
        Returns:
            dict: Stats
        """
        programs = self.load_programs()
        
        if not programs:
            return {
                'total': 0,
                'max_temp': 0,
                'avg_duration': 0
            }
        
        max_temps = [p.get('maxTemp', 0) for p in programs.values()]
        durations = [p.get('totalTime', 0) for p in programs.values()]
        
        return {
            'total': len(programs),
            'max_temp': max(max_temps) if max_temps else 0,
            'avg_duration': sum(durations) / len(durations) if durations else 0,
            'total_duration': sum(durations)
        }
