"""Тренажёр трейдера: игра на исторических котировках Мосбиржи.

Логика (moex, dataset, rounds, scoring, modes, stats, journal) не зависит
от Streamlit и покрыта pytest'ом. Интерфейс — ui.py, ui_stats.py и chart/
(игровой компонент); страница app_pages/trainer.py их склеивает.
"""
