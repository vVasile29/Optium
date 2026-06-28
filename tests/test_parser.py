"""Tests for the parser module."""

from services.parser import extract_subject


class TestExtractSubject:
    def test_how_good_for(self):
        result = extract_subject("How good is a Tesla for commuting?")
        assert result["parsed"] is True
        assert result["subject"] == "Tesla"
        assert result["goal"] == "commuting"

    def test_how_good_no_goal(self):
        result = extract_subject("How good is Python?")
        assert result["parsed"] is True
        assert result["subject"] == "Python"
        assert result["goal"] is None

    def test_how_does_perform_for(self):
        result = extract_subject("How does Java perform for web development?")
        assert result["parsed"] is True
        assert result["subject"] == "Java"
        assert result["goal"] == "web development"

    def test_rate_my(self):
        result = extract_subject("Rate my portfolio")
        assert result["parsed"] is True
        assert result["subject"] == "portfolio"
        assert result["goal"] is None

    def test_evaluate(self):
        result = extract_subject("Evaluate Django")
        assert result["parsed"] is True
        assert result["subject"] == "Django"

    def test_review(self):
        result = extract_subject("Review这台电脑")  # non-English
        assert result["parsed"] is True
        assert result["subject"] == "这台电脑"

    def test_what_do_you_think(self):
        result = extract_subject("What do you think about Rust?")
        assert result["parsed"] is True
        assert result["subject"] == "Rust"

    def test_no_match(self):
        result = extract_subject("Hello world")
        assert result["parsed"] is False
        assert result["subject"] == "This option"

    def test_empty_string(self):
        result = extract_subject("")
        assert result["parsed"] is False
        assert result["subject"] == "This option"

    def test_strip_articles(self):
        result = extract_subject("How good is the new iPhone?")
        assert result["subject"] == "new iPhone"

    def test_multi_word_subject(self):
        result = extract_subject("How good is a Tesla Model 3 for daily commuting?")
        assert result["subject"] == "Tesla Model 3"
        assert result["goal"] == "daily commuting"

    def test_trailing_question_mark(self):
        result = extract_subject("Evaluate Python?")
        assert result["subject"] == "Python"
