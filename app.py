"""SUMMARIZE - Video Summarizer.

Streamlit entry point. All implementation lives in the ``webapp``
package; this file exists so ``streamlit run app.py`` keeps working.
"""

from webapp.ui import main

if __name__ == "__main__":
    main()
