# -*- coding: utf-8 -*-
"""Official Streamlit entry point for AI Council V19.4.

Deployment contract:
    streamlit run app.py

The application logic remains in main.py; this file is intentionally thin so
Streamlit Cloud and other hosts have one stable, explicit entry point.
"""
from __future__ import annotations

from main import main


if __name__ == "__main__":
    main()
