from a2flow_content.service import markdown_to_text


def test_markdown_to_text_preserves_literal_content_and_code() -> None:
    source = "# 标题\n\nuser_id 与 a*b\n\n`code_value`\n\n```python\nx_y = a * b\n```"
    result = markdown_to_text(source)
    assert "user_id" in result
    assert "a*b" in result
    assert "code_value" in result
    assert "x_y = a * b" in result
    assert "# 标题" not in result
