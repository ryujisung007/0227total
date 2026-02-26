"""
통합 데이터 모듈
- common: 식품 R&D 공통 데이터 (매출, 브랜드, 배합비, 원가, 공정 등)
- label_engine: 표시사항 적부판정 엔진 (법령 스키마, 판정 로직, KB)
"""
from data.common import *
from data.label_engine import (
    REGULATION_SCHEMA, ALLERGENS_22, CSV_TEMPLATE, SAMPLE_LABELS,
    KB_DIR,
    extract_pdf, save_knowledge, load_knowledge, load_all_knowledge,
    search_knowledge, check_compliance, get_summary,
    call_openai,
    # re-export under label_ prefix to avoid name collisions
)
# Alias to avoid collision with common.py's render_chatbot
from data.label_engine import render_chatbot as render_label_chatbot
from data.label_engine import render_api_key_input as render_label_api_key_input
