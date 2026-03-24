<>:81: SyntaxWarning: invalid escape sequence '\d'
<>:81: SyntaxWarning: invalid escape sequence '\d'
/tmp/ipykernel_1074/3519802818.py:81: SyntaxWarning: invalid escape sequence '\d'
  df['유통기한_추출'] = df['유통기한'].str.extract('(\d+)').astype(float)
---------------------------------------------------------------------------
ModuleNotFoundError                       Traceback (most recent call last)
/tmp/ipykernel_1074/3519802818.py in <cell line: 0>()
      1 import pandas as pd
----> 2 import streamlit as st
      3 import plotly.express as px
      4 import plotly.graph_objects as go
      5 from datetime import datetime

ModuleNotFoundError: No module named 'streamlit'

---------------------------------------------------------------------------
NOTE: If your import is failing due to a missing package, you can
manually install dependencies using either !pip or !apt.

To view examples of installing some common dependencies, click the
"Open Examples" button below.
---------------------------------------------------------------------------
