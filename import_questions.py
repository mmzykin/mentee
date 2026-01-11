#!/usr/bin/env python3
"""
Импорт вопросов из текстового файла в базу данных.

Формат файла:
TOPIC: topic_id

Q: Текст вопроса?
A) Вариант 1
B) Вариант 2
C) Правильный вариант
D) Вариант 4
ANSWER: C
EXPLAIN: Объяснение

Q: Следующий вопрос?...
"""

import re
import sys
import database as db


def parse_questions_file(filepath: str):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    questions = []
    current_topic = None
    
    # Split by TOPIC markers
    topic_sections = re.split(r'\nTOPIC:\s*', content)
    
    for section in topic_sections:
        if not section.strip():
            continue
        
        lines = section.strip().split('\n')
        topic_id = lines[0].strip()
        
        # Verify topic exists
        topic = db.get_topic(topic_id)
        if not topic:
            print(f"⚠️  Тема {topic_id} не найдена, пропускаю...")
            continue
        
        # Split by Q: markers
        questions_raw = re.split(r'\nQ:\s*', '\n'.join(lines[1:]))
        
        for q_raw in questions_raw:
            if not q_raw.strip():
                continue
            
            q_lines = q_raw.strip().split('\n')
            question_text = q_lines[0].strip()
            
            options = []
            correct_idx = 0
            explanation = None
            
            for line in q_lines[1:]:
                line = line.strip()
                if line.startswith("ANSWER:"):
                    letter = line.split(":")[1].strip().upper()
                    correct_idx = {'A': 0, 'B': 1, 'C': 2, 'D': 3, 'E': 4}.get(letter, 0)
                elif line.startswith("EXPLAIN:"):
                    explanation = line.split(":", 1)[1].strip()
                elif len(line) > 2 and line[1] == ')':
                    options.append({"text": line[2:].strip()})
            
            if len(options) >= 2 and question_text:
                questions.append({
                    'topic_id': topic_id,
                    'question_text': question_text,
                    'options': options,
                    'correct_idx': correct_idx,
                    'explanation': explanation
                })
    
    return questions


def import_questions(questions):
    db.init_db()
    
    print(f"\n📝 Импорт {len(questions)} вопросов...")
    added = 0
    
    for q in questions:
        q_id = db.add_question(
            q['topic_id'],
            q['question_text'],
            q['options'],
            q['correct_idx'],
            0.1,
            q['explanation']
        )
        if q_id:
            added += 1
            topic = db.get_topic(q['topic_id'])
            topic_name = topic['name'] if topic else q['topic_id']
            print(f"  ✅ [{topic_name}] {q['question_text'][:50]}...")
    
    print(f"\n🎉 Готово! Добавлено: {added} вопросов")
    print(f"   Всего в базе: {db.get_all_questions_count()} вопросов")


def main():
    if len(sys.argv) < 2:
        print("Usage: python import_questions.py <questions_file.txt>")
        print("Example: python import_questions.py questions_python.txt")
        sys.exit(1)
    
    filepath = sys.argv[1]
    print(f"📂 Парсинг файла: {filepath}")
    
    questions = parse_questions_file(filepath)
    print(f"📊 Найдено: {len(questions)} вопросов")
    
    if questions:
        import_questions(questions)
    else:
        print("❌ Вопросы не найдены. Проверь формат файла.")


if __name__ == "__main__":
    main()
