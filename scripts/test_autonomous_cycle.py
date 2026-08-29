"""
scripts/test_autonomous_cycle.py
==================================

Teste local do ciclo autônomo. Executa run_market_cycle() uma vez
e imprime o resultado. Usado para validação antes de ativar o scheduler.

Uso:
    python scripts/test_autonomous_cycle.py
"""

import os
import sys
import logging

# Garantir que o diretório raiz do projeto está no path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)

if __name__ == "__main__":
    print("=" * 60)
    print("ALPHAQUANT X — TESTE DO CICLO AUTÔNOMO")
    print("=" * 60)
    print()

    from engine.autonomous_cycle import run_market_cycle

    print("Iniciando ciclo de mercado...")
    print()
    run_market_cycle()
    print()
    print("Teste concluído.")
