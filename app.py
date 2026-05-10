"""SUMMARIZE - Video Summarizer.

Streamlit entry point. All implementation lives in the ``webapp``
package; this file exists so ``streamlit run app.py`` keeps working.
"""

from webapp.config import coerce_int, normalize_config_section
from webapp.ui import main

if __name__ == "__main__":
    main()
