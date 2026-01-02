"""
محلل أسئلة البكالوريا
يستخرج الأسئلة من PDF ويحللها ويصدر الإحصائيات
"""

import re
import os
import pandas as pd
from pathlib import Path
import pdfplumber
from gemini_client import GeminiClient


class BacAnalyzer:
    def __init__(self, pdf_folder, output_folder='output'):
        self.pdf_folder = Path(pdf_folder)
        self.output_folder = Path(output_folder)
        self.output_folder.mkdir(exist_ok=True)
        
        self.gemini = GeminiClient()
        self.questions = []
        
        # أنماط للتعرف على الأسئلة
        self.question_patterns = [
            r'(?:السؤال|التمرين|س)\s*(\d+)',
            r'(?:^|\n)(\d+)\s*[.)-]',
            r'(?:Question|Exercise)\s*(\d+)'
        ]
        
        # كلمات مفتاحية لتصنيف الأسئلة محلياً
        self.keywords = {
            'calculation': ['احسب', 'أحسب', 'calculate', 'عين', 'أوجد قيمة'],
            'proof': ['أثبت', 'برهن', 'prove', 'استنتج أن', 'بين أن'],
            'interpretation': ['فسر', 'علل', 'interpret', 'لماذا', 'ما سبب'],
            'representation': ['ارسم', 'مثل', 'draw', 'أنشئ منحنى', 'plot'],
            'equation_solving': ['حل المعادلة', 'solve', 'أوجد الحلول'],
            'deduction': ['استنتج', 'deduce', 'ماذا تستنتج', 'deduce']
        }
    
    def extract_text_from_pdfs(self):
        """استخراج النصوص من ملفات PDF"""
        pdf_files = list(self.pdf_folder.glob('*.pdf'))
        print(f"تم العثور على {len(pdf_files)} ملف PDF")
        
        texts = {}
        for pdf_file in pdf_files:
            try:
                # استخراج السنة من اسم الملف
                year = self._extract_year(pdf_file.name)
                
                with pdfplumber.open(pdf_file) as pdf:
                    text = ''
                    for page in pdf.pages:
                        text += page.extract_text() + '\n'
                    
                    texts[year] = text
                    print(f"تم استخراج نص من: {pdf_file.name} (السنة: {year})")
            
            except Exception as e:
                print(f"خطأ في قراءة {pdf_file.name}: {e}")
        
        return texts
    
    def _extract_year(self, filename):
        """استخراج السنة من اسم الملف"""
        match = re.search(r'(20\d{2}|19\d{2})', filename)
        return match.group(1) if match else filename.replace('.pdf', '')
    
    def split_into_questions(self, text):
        """تقسيم النص إلى أسئلة منفصلة"""
        questions = []
        
        # محاولة التقسيم بناءً على الأنماط
        for pattern in self.question_patterns:
            matches = list(re.finditer(pattern, text, re.MULTILINE))
            
            if len(matches) >= 2:  # إذا وجدنا على الأقل سؤالين
                for i, match in enumerate(matches):
                    start = match.start()
                    end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
                    
                    question_text = text[start:end].strip()
                    
                    # تنظيف النص
                    question_text = self._clean_text(question_text)
                    
                    if len(question_text) > 20:  # تجاهل النصوص القصيرة جداً
                        questions.append({
                            'id': match.group(1) if match.groups() else str(i + 1),
                            'text': question_text
                        })
                
                if questions:
                    break
        
        # إذا فشلت الطرق الأخرى، قسم بناءً على فقرات طويلة
        if not questions:
            paragraphs = text.split('\n\n')
            for i, para in enumerate(paragraphs):
                para = para.strip()
                if len(para) > 50:
                    questions.append({
                        'id': str(i + 1),
                        'text': self._clean_text(para)
                    })
        
        return questions
    
    def _clean_text(self, text):
        """تنظيف النص من الرموز الزائدة"""
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'[\r\n]+', ' ', text)
        return text.strip()
    
    def classify_question_rule_based(self, question_text):
        """تصنيف السؤال بناءً على قواعد محلية (بدون Gemini)"""
        text_lower = question_text.lower()
        
        scores = {q_type: 0 for q_type in self.keywords.keys()}
        
        for q_type, keywords in self.keywords.items():
            for keyword in keywords:
                if keyword in text_lower:
                    scores[q_type] += 1
        
        max_score = max(scores.values())
        
        if max_score == 0:
            return None  # فشل التصنيف المحلي
        
        # إذا كان هناك أكثر من نوع بنفس الدرجة
        high_score_types = [t for t, s in scores.items() if s == max_score]
        
        if len(high_score_types) > 1:
            q_type = 'mixed'
        else:
            q_type = high_score_types[0]
        
        # فحص إذا كان السؤال مركب
        is_composite = self._is_composite(question_text)
        
        return {
            'question_type': q_type,
            'is_composite': is_composite
        }
    
    def _is_composite(self, text):
        """فحص إذا كان السؤال مركباً"""
        # أنماط تدل على الأسئلة المركبة
        composite_patterns = [
            r'[أ|ا|1|أ|a]\s*[.)-]',
            r'[ب|2|ب|b]\s*[.)-]',
            r'الجزء\s+(?:الأول|الثاني)',
            r'(?:أولا|ثانيا|ثالثا)',
        ]
        
        count = 0
        for pattern in composite_patterns:
            count += len(re.findall(pattern, text))
        
        return count >= 2
    
    def classify_question_with_gemini(self, question_text):
        """استخدام Gemini للتصنيف (آخر خيار)"""
        return self.gemini.classify_question(question_text)
    
    def analyze_questions(self):
        """تحليل جميع الأسئلة"""
        pdf_texts = self.extract_text_from_pdfs()
        
        for year, text in pdf_texts.items():
            questions = self.split_into_questions(text)
            print(f"\nالسنة {year}: تم العثور على {len(questions)} سؤال")
            
            for q in questions:
                # محاولة التصنيف المحلي أولاً
                classification = self.classify_question_rule_based(q['text'])
                
                # إذا فشل، استخدم Gemini
                if classification is None:
                    print(f"  استخدام Gemini للسؤال {q['id']}...")
                    classification = self.classify_question_with_gemini(q['text'])
                
                self.questions.append({
                    'year': year,
                    'question_id': q['id'],
                    'question_text': q['text'][:500],  # حد أقصى 500 حرف للتخزين
                    'question_type': classification['question_type'],
                    'is_composite': classification['is_composite']
                })
        
        print(f"\n✓ تم تحليل {len(self.questions)} سؤال إجمالاً")
    
    def calculate_statistics(self):
        """حساب الإحصائيات المحلية"""
        df = pd.DataFrame(self.questions)
        
        # إحصاءات أنواع الأسئلة
        type_counts = df['question_type'].value_counts()
        total = len(df)
        
        stats = []
        for q_type, count in type_counts.items():
            stats.append({
                'question_type': q_type,
                'frequency': count,
                'probability_percentage': round((count / total) * 100, 2)
            })
        
        return pd.DataFrame(stats).sort_values('frequency', ascending=False)
    
    def identify_critical_questions(self):
        """تحديد الأسئلة الحرجة (الأكثر أهمية)"""
        df = pd.DataFrame(self.questions)
        
        # حساب تكرار كل نوع
        type_freq = df['question_type'].value_counts()
        top_types = type_freq.head(3).index.tolist()
        
        critical = []
        
        for _, row in df.iterrows():
            importance_score = 0
            reasons = []
            
            # معايير الأهمية
            if row['question_type'] in top_types:
                importance_score += 3
                rank = top_types.index(row['question_type']) + 1
                reasons.append(f"نوع متكرر (المرتبة {rank})")
            
            if row['is_composite']:
                importance_score += 2
                reasons.append("سؤال مركب")
            
            if importance_score > 0:
                critical.append({
                    'year': row['year'],
                    'question_id': row['question_id'],
                    'question_text': row['question_text'],
                    'question_type': row['question_type'],
                    'importance_score': importance_score,
                    'reasons': ' | '.join(reasons)
                })
        
        # ترتيب حسب الأهمية
        critical.sort(key=lambda x: x['importance_score'], reverse=True)
        
        return critical
    
    def export_results(self):
        """تصدير النتائج إلى ملفات"""
        # 1. تصدير جميع الأسئلة
        df_questions = pd.DataFrame(self.questions)
        df_questions.to_csv(
            self.output_folder / 'questions_analysis.csv',
            index=False,
            encoding='utf-8-sig'
        )
        print(f"✓ تم حفظ: questions_analysis.csv")
        
        # 2. تصدير إحصائيات الأنواع
        df_stats = self.calculate_statistics()
        df_stats.to_csv(
            self.output_folder / 'question_type_stats.csv',
            index=False,
            encoding='utf-8-sig'
        )
        print(f"✓ تم حفظ: question_type_stats.csv")
        
        # 3. تصدير الأسئلة الحرجة
        critical = self.identify_critical_questions()
        
        with open(self.output_folder / 'critical_questions.txt', 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write("الأسئلة الحرجة - الأكثر أهمية للمراجعة\n")
            f.write("=" * 80 + "\n\n")
            
            for i, q in enumerate(critical[:20], 1):  # أعلى 20 سؤال
                f.write(f"\n{'=' * 80}\n")
                f.write(f"#{i} | السنة: {q['year']} | السؤال: {q['question_id']}\n")
                f.write(f"النوع: {q['question_type']} | الأهمية: {q['importance_score']}\n")
                f.write(f"السبب: {q['reasons']}\n")
                f.write(f"{'-' * 80}\n")
                f.write(f"{q['question_text']}\n")
            
            f.write(f"\n{'=' * 80}\n")
            f.write(f"إجمالي الأسئلة الحرجة: {len(critical)}\n")
        
        print(f"✓ تم حفظ: critical_questions.txt")
        
        # طباعة ملخص
        print(f"\n{'=' * 60}")
        print("ملخص الإحصائيات:")
        print(f"{'=' * 60}")
        print(df_stats.to_string(index=False))
        print(f"{'=' * 60}\n")


def main():
    """الدالة الرئيسية"""
    # TODO: تغيير المسار حسب موقع ملفات PDF
    PDF_FOLDER = 'bac_pdfs'
    
    if not os.path.exists(PDF_FOLDER):
        print(f"⚠️ المجلد {PDF_FOLDER} غير موجود!")
        print("يرجى إنشاء المجلد ووضع ملفات PDF فيه")
        return
    
    analyzer = BacAnalyzer(PDF_FOLDER)
    
    print("بدء التحليل...\n")
    analyzer.analyze_questions()
    analyzer.export_results()
    
    print("\n✅ اكتمل التحليل بنجاح!")


if __name__ == '__main__':
    main()
