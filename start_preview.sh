#!/bin/bash
cd /Users/sushantakumarsahoo/Downloads/Gemini_Crypto/backend
export PYTHONPATH=/Users/sushantakumarsahoo/Downloads/Gemini_Crypto/backend/venv/lib/python3.9/site-packages
export PATH=/Users/sushantakumarsahoo/Downloads/Gemini_Crypto/backend/venv/bin:$PATH
exec /Users/sushantakumarsahoo/Downloads/Gemini_Crypto/backend/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8001
