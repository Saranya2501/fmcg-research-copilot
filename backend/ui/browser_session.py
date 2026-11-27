"""Remember resume identifiers in this browser; chat content stays in SQLite."""
import streamlit as st
from streamlit.components.v2 import component

_storage = component(
    "fmcg_browser_session",
    js="""
    export default function({data, setStateValue}) {
        const key = 'fmcg.resume.v1';
        try {
            if (data.action === 'save') {
                localStorage.setItem(key, JSON.stringify(data.resume));
            } else {
                let resume = null;
                try { resume = JSON.parse(localStorage.getItem(key)); } catch (_) {}
                setStateValue('loaded', {resume});
            }
        } catch (_) {
            if (data.action === 'load') setStateValue('loaded', {resume: null});
        }
    }
    """,
)


def restore_browser_session():
    if st.query_params.get('session') or st.session_state.get('browser_resume_checked'):
        return
    result = _storage(key='load_browser_session', data={'action': 'load'},
                      default={'loaded': None}, on_loaded_change=lambda: None, height=0)
    if result.loaded is None:
        return
    st.session_state.browser_resume_checked = True
    resume = result.loaded.get('resume')
    if isinstance(resume, dict) and isinstance(resume.get('session'), str):
        st.query_params['session'] = resume['session']
        if isinstance(resume.get('chat'), str):
            st.query_params['chat'] = resume['chat']
        st.rerun()


def save_browser_session(session_id, chat_id):
    _storage(key='save_browser_session', data={
        'action': 'save', 'resume': {'session': session_id, 'chat': chat_id}
    }, height=0)
