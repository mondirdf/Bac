"""
Gemini API Client
يستخدم فقط لاستخراج نوع السؤال وتحديد إذا كان مركب
"""

import os
import json
import requests
import time


class GeminiClient:
    def __init__(self):
        self.api_key = os.getenv('GEMINI_API_KEY')
        if not self.api_key:
            raise ValueError("يجب تعيين GEMINI_API_KEY في متغيرات البيئة")
        
        self.api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={self.api_key}"
        self.valid_types = [
            'calculation', 'proof', 'interpretation', 
            'representation', 'equation_solving', 'deduction', 'mixed'
        ]
    
    def classify_question(self, question_text):
        """
        استدعاء Gemini لتصنيف السؤال
        Returns: dict with keys: question_type, is_composite
        """
        prompt = f"""أنت محلل أسئلة امتحانات. صنّف السؤال التالي إلى أحد الأنواع التالية فقط:
- calculation (حساب رقمي)
- proof (إثبات أو برهان)
- interpretation (تفسير أو تحليل)
- representation (رسم أو تمثيل)
- equation_solving (حل معادلة)
- deduction (استنتاج منطقي)
- mixed (مزيج من الأنواع)

حدد أيضاً إذا كان السؤال مركب (يحتوي على عدة أجزاء).

السؤال:
{question_text}

أرجع JSON فقط بهذا الشكل (بدون أي نص إضافي):
{{"question_type": "...", "is_composite": true/false}}"""

        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 100
            }
        }
        
        try:
            response = requests.post(
                self.api_url,
                headers={'Content-Type': 'application/json'},
                json=payload,
                timeout=30
            )
            
            if response.status_code != 200:
                print(f"خطأ في Gemini API: {response.status_code}")
                return self._default_classification()
            
            result = response.json()
            text = result['candidates'][0]['content']['parts'][0]['text']
            
            # استخراج JSON من النص
            return self._parse_gemini_response(text)
            
        except Exception as e:
            print(f"خطأ في استدعاء Gemini: {e}")
            return self._default_classification()
    
    def _parse_gemini_response(self, text):
        """استخراج JSON من رد Gemini"""
        try:
            # محاولة استخراج JSON مباشرة
            text = text.strip()
            
            # إزالة markdown code blocks إن وجدت
            if '```json' in text:
                text = text.split('```json')[1].split('```')[0]
            elif '```' in text:
                text = text.split('```')[1].split('```')[0]
            
            # البحث عن JSON في النص
            start = text.find('{')
            end = text.rfind('}') + 1
            
            if start >= 0 and end > start:
                json_str = text[start:end]
                data = json.loads(json_str)
                
                # التحقق من صحة البيانات
                q_type = data.get('question_type', 'mixed')
                if q_type not in self.valid_types:
                    q_type = 'mixed'
                
                is_comp = data.get('is_composite', False)
                if not isinstance(is_comp, bool):
                    is_comp = str(is_comp).lower() == 'true'
                
                return {
                    'question_type': q_type,
                    'is_composite': is_comp
                }
            
        except Exception as e:
            print(f"خطأ في تحليل رد Gemini: {e}")
        
        return self._default_classification()
    
    def _default_classification(self):
        """التصنيف الافتراضي عند الفشل"""
        return {
            'question_type': 'mixed',
            'is_composite': False
        }
