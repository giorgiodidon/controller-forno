"""
Services - Servizi esterni (notifiche, storage, ecc)
"""

from .notifications import NotificationService
from .storage import StorageService

__all__ = ['NotificationService', 'StorageService']
