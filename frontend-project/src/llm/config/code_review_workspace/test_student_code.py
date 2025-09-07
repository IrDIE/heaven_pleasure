# Код тестов для функции

def test_answer_question_empty_input():
    retriever = HybridRetriever(vs, bm25, docs)
    assert answer_question('', retriever) == ('Не найдено в материалах.', [])
