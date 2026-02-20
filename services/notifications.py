"""
Servizio Notifiche Push via ntfy.sh
"""

import requests
from config import NTFY_TOPIC, NTFY_URL, NTFY_ENABLED


class NotificationService:
    """
    Gestisce invio notifiche push via ntfy.sh
    """
    
    def __init__(self, enabled=NTFY_ENABLED):
        self.topic = NTFY_TOPIC
        self.url = NTFY_URL
        self.enabled = enabled
        
        if self.enabled:
            print(f"🔔 Notifiche abilitate: {self.topic}")
        else:
            print("🔕 Notifiche disabilitate")
    
    def send(self, title, message, priority="high", tags=None):
        """
        Invia notifica push usando HTTP headers
        
        Args:
            title (str): Titolo notifica
            message (str): Corpo messaggio
            priority (str): max, high, default, low, min
            tags (list): Lista emoji/tag (es. ["fire", "warning"])
        
        Returns:
            bool: True se inviata con successo
        """
        if not self.enabled:
            return False
        
        try:
            # Headers HTTP: requests usa latin-1, quindi encode UTF-8 manualmente
            headers = {}
            
            # Title: encode UTF-8 poi decode come latin-1 (trick per passare bytes)
            if title:
                headers['Title'] = title.encode('utf-8').decode('latin-1')
            
            # Priority: solo ASCII, nessun problema
            if priority:
                headers['Priority'] = priority
            
            # Tags: solo nomi ASCII (es. "fire", "white_check_mark")
            if tags:
                headers['Tags'] = ','.join(tags)
            
            response = requests.post(
                self.url,  # URL già include topic: https://ntfy.sh/forno_giorgio
                data=message.encode('utf-8'),
                headers=headers,
                timeout=5
            )
            
            if response.status_code == 200:
                print(f"✅ Notifica inviata: {title}")
                return True
            else:
                print(f"⚠️ Errore notifica HTTP {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ Errore invio notifica: {e}")
            return False
    
    # ===== NOTIFICHE PREDEFINITE =====
    
    def notify_system_start(self):
        """Sistema avviato"""
        return self.send(
            "🚀 Sistema Avviato",
            "Forno Ceramica v3.0 online",
            priority="high",
            tags=["rocket"]
        )
    
    def notify_program_start(self, program_name):
        """Programma avviato"""
        return self.send(
            "🔥 Programma Avviato",
            f'Inizio cottura: "{program_name}"',
            priority="high",
            tags=["fire"]
        )
    
    def notify_program_complete(self, program_name, duration_minutes):
        """Programma completato"""
        return self.send(
            "✅ Programma Completato",
            f'Cottura terminata: {program_name}\nDurata: {duration_minutes:.0f} minuti',
            priority="high",
            tags=["white_check_mark", "tada"]
        )
    
    def notify_ramp_complete(self, ramp_num, total_ramps, target_temp):
        """Rampa completata"""
        return self.send(
            "📈 Rampa Completata",
            f'Rampa {ramp_num}/{total_ramps} → {target_temp}°C raggiunta',
            priority="high",
            tags=["chart_with_upwards_trend"]
        )
    
    def notify_hold_start(self, temperature, duration_minutes):
        """Inizio mantenimento"""
        return self.send(
            "⏱️ Mantenimento Avviato",
            f'{temperature}°C per {duration_minutes} minuti',
            priority="high",
            tags=["hourglass"]
        )
    
    def notify_cooling_start(self, temperature):
        """Raffreddamento iniziato"""
        return self.send(
            "❄️ Raffreddamento",
            f'Temperatura sotto 700°C: {temperature}°C',
            priority="high",
            tags=["snowflake"]
        )
    
    def notify_over_temp(self, temperature):
        """ALLARME sovratemperatura"""
        return self.send(
            "🚨 ALLARME SOVRATEMPERATURA",
            f'Temperatura critica: {temperature}°C\nLimite: 1310°C\nSPEGNERE IMMEDIATAMENTE!',
            priority="max",
            tags=["rotating_light", "fire"]
        )
    
    def notify_sensor_error(self):
        """Errore sensore"""
        return self.send(
            "❌ Errore Sensore",
            "MCP9600 disconnesso o malfunzionante",
            priority="high",
            tags=["x", "warning"]
        )
    
    def notify_sensor_reconnect(self, temperature):
        """Sensore riconnesso"""
        return self.send(
            "✅ Sensore Connesso",
            f"MCP9600 operativo - Temperatura: {temperature}°C",
            priority="high",
            tags=["white_check_mark"]
        )
    
    def notify_fast_cooling(self, rate):
        """Raffreddamento troppo veloce"""
        return self.send(
            "⚠️ Raffreddamento Rapido",
            f'Velocità: {rate}°C/h\nRischio shock termico!',
            priority="high",
            tags=["warning", "snowflake"]
        )
    
    def notify_program_stopped(self):
        """Programma fermato manualmente"""
        return self.send(
            "⏸️ Programma Fermato",
            "Esecuzione interrotta manualmente",
            priority="high",
            tags=["pause_button"]
        )
    
    def enable(self):
        """Abilita notifiche"""
        self.enabled = True
        print("🔔 Notifiche abilitate")
    
    def disable(self):
        """Disabilita notifiche"""
        self.enabled = False
        print("🔕 Notifiche disabilitate")
    
    def get_status(self):
        """Stato servizio"""
        return {
            'enabled': self.enabled,
            'topic': self.topic,
            'url': self.url
        }
