#!/usr/bin/env python3
"""
Test Integrazione Stepper Motor
Verifica che il codice testato funzioni nell'architettura modulare
"""

import sys
import time

# Import moduli
from hardware.actuators import ActuatorManager
from config import STEPS_PER_REVOLUTION

def test_basic_movement():
    """Test movimenti base come codice originale"""
    print("="*60)
    print("TEST INTEGRAZIONE STEPPER MOTOR")
    print("="*60)
    
    try:
        # Inizializza actuator manager
        print("\n1. Inizializzazione...")
        actuators = ActuatorManager()
        
        # Calibra (azzera posizione)
        print("\n2. Calibrazione...")
        actuators.calibrate_valve()
        
        # Test mezzo giro avanti (come codice originale)
        print("\n3. Test mezzo giro AVANTI (100 steps)...")
        half_revolution = STEPS_PER_REVOLUTION // 2  # 100 steps
        
        # Invece di chiamare direttamente step(), usiamo set_position
        # 100 steps = 7.14% apertura (100/1400 * 100)
        target_percent = (half_revolution / actuators.valve.total_steps) * 100
        
        print(f"   Apertura {target_percent:.1f}% ({half_revolution} steps)")
        actuators.set_valve_position(target_percent)
        
        # Pausa
        print("\n4. Pausa 1 secondo...")
        time.sleep(1)
        
        # Status intermedio
        status = actuators.get_status()
        print(f"\n   Status: {status['valve']['position_steps']} steps")
        
        # Test mezzo giro indietro (ritorno a 0)
        print("\n5. Test mezzo giro INDIETRO (ritorno a 0)...")
        actuators.set_valve_position(0)
        
        # Status finale
        print("\n6. Verifica finale...")
        status = actuators.get_status()
        print(f"   Posizione: {status['valve']['position_steps']} steps")
        print(f"   Percentuale: {status['valve']['position_percent']}%")
        
        if status['valve']['position_steps'] == 0:
            print("\n✅ TEST SUPERATO - Motore ritornato a posizione iniziale")
        else:
            print(f"\n⚠️ WARNING - Posizione finale: {status['valve']['position_steps']} (atteso: 0)")
        
        # Cleanup
        print("\n7. Cleanup...")
        actuators.cleanup()
        
        print("\n" + "="*60)
        print("TEST COMPLETATO CON SUCCESSO")
        print("="*60)
        
    except KeyboardInterrupt:
        print("\n\n⏸️ Interrotto da utente")
        actuators.cleanup()
        
    except Exception as e:
        print(f"\n\n❌ ERRORE: {e}")
        import traceback
        traceback.print_exc()
        actuators.cleanup()


def test_full_range():
    """Test range completo 0-100%"""
    print("\n" + "="*60)
    print("TEST RANGE COMPLETO (0% → 100% → 0%)")
    print("="*60)
    
    try:
        actuators = ActuatorManager()
        actuators.calibrate_valve()
        
        # Test posizioni intermedie
        positions = [0, 25, 50, 75, 100, 75, 50, 25, 0]
        
        for pos in positions:
            print(f"\n→ Posizione {pos}%...")
            actuators.set_valve_position(pos)
            
            status = actuators.get_status()
            actual = status['valve']['position_percent']
            steps = status['valve']['position_steps']
            
            print(f"   Reale: {actual}% ({steps} steps)")
            
            time.sleep(0.5)
        
        print("\n✅ Test range completato")
        actuators.cleanup()
        
    except Exception as e:
        print(f"\n❌ Errore: {e}")
        actuators.cleanup()


if __name__ == "__main__":
    print("\nSeleziona test:")
    print("1. Test base (mezzo giro avanti/indietro)")
    print("2. Test range completo (0-100%)")
    print("3. Entrambi")
    
    choice = input("\nScelta (1/2/3): ").strip()
    
    if choice == "1":
        test_basic_movement()
    elif choice == "2":
        test_full_range()
    elif choice == "3":
        test_basic_movement()
        time.sleep(2)
        test_full_range()
    else:
        print("Scelta non valida")
