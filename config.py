import os
import streamlit as st

def set_environment():
    for key, value in st.secrets.items():
        os.environ[key] = str(value)
