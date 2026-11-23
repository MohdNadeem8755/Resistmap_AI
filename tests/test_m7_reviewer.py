from m7_code_review_bot.reviewer import review_diff

def test_detects_secret_with_exact_line():
    result = review_diff([{"path": "app.py", "content": "API_KEY = 'super-secret-value'\n"}])
    assert result.findings[0].rule == "hard-coded-secret"
    assert result.findings[0].line == 1

def test_clean_code_stays_quiet():
    result = review_diff([{"path": "math.py", "content": "def add(a, b):\n    return a + b\n"}])
    assert result.clean

def test_long_function_is_line_level():
    content = "def process():\n" + "    value = 1\n" * 55
    result = review_diff([{"path": "worker.py", "content": content}])
    assert any(f.rule == "long-function" and f.line == 1 for f in result.findings)
