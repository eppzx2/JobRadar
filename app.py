"""Launch JobRadar from Python, or render it when Streamlit runs this file."""

import sys


def render():
    from dotenv import load_dotenv

    from database.store import connect
    from frontend.dashboard import dashboard

    load_dotenv()
    db = connect()
    try:
        dashboard(db)
    finally:
        db.close()


if __name__ == '__main__':
    # Streamlit executes its entry script as __main__, including on widget reruns.
    if 'streamlit.runtime.scriptrunner' in sys.modules:
        from streamlit.runtime.scriptrunner import get_script_run_ctx

        inside_dashboard = get_script_run_ctx(suppress_warning=True) is not None
    else:
        inside_dashboard = False

    if inside_dashboard:
        render()
    else:
        from launcher import main

        sys.exit(main())
