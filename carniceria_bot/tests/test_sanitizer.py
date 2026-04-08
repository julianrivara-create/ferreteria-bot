"""
Unit Tests for Input Sanitizer
"""

import pytest
from bot_sales.security.sanitizer import InputSanitizer, sanitize_input


class TestHTMLSanitization:
    """Tests for HTML escaping"""
    
    def test_sanitize_basic_html(self):
        result = InputSanitizer.sanitize_html('<script>alert("xss")</script>')
        assert '<script>' not in result
        assert '&lt;script&gt;' in result
    
    def test_sanitize_html_tags(self):
        result = InputSanitizer.sanitize_html('<b>bold</b>')
        assert '<b>' not in result
        assert '&lt;b&gt;' in result
    
    def test_sanitize_html_empty(self):
        result = InputSanitizer.sanitize_html('')
        assert result == ''
    
    def test_sanitize_html_none(self):
        result = InputSanitizer.sanitize_html(None)
        assert result == ''


class TestXSSDetection:
    """Tests for XSS attack detection"""
    
    def test_detect_script_tag(self):
        assert InputSanitizer.detect_xss('<script>alert(1)</script>') is True
    
    def test_detect_javascript_protocol(self):
        assert InputSanitizer.detect_xss('javascript:alert(1)') is True
    
    def test_detect_onerror(self):
        assert InputSanitizer.detect_xss('<img src=x onerror=alert(1)>') is True
    
    def test_detect_iframe(self):
        assert InputSanitizer.detect_xss('<iframe src="evil.com"></iframe>') is True
    
    def test_no_xss_in_normal_text(self):
        assert InputSanitizer.detect_xss('This is a normal message') is False
    
    def test_case_insensitive_detection(self):
        assert InputSanitizer.detect_xss('<SCRIPT>alert(1)</SCRIPT>') is True


class TestPathSanitization:
    """Tests for path traversal prevention"""
    
    def test_remove_dot_dot_slash(self):
        result = InputSanitizer.sanitize_path('../../../etc/passwd')
        assert '../' not in result
    
    def test_remove_dot_dot_backslash(self):
        result = InputSanitizer.sanitize_path('..\\..\\..\\windows\\system32')
        assert '..\\' not in result
    
    def test_normal_path(self):
        result = InputSanitizer.sanitize_path('uploads/images/photo.jpg')
        assert result == 'uploads/images/photo.jpg'


class TestUserInputSanitization:
    """Tests for general user input sanitization"""
    
    def test_truncate_long_input(self):
        long_text = 'a' * 20000
        result = InputSanitizer.sanitize_user_input(long_text, max_length=100)
        assert len(result) <= 100
    
    def test_remove_null_bytes(self):
        result = InputSanitizer.sanitize_user_input('hello\x00world')
        assert '\x00' not in result
    
    def test_normalize_whitespace(self):
        result = InputSanitizer.sanitize_user_input('hello    world   test')
        assert '    ' not in result
        assert 'hello world test' in result
    
    def test_html_escape_in_user_input(self):
        result = InputSanitizer.sanitize_user_input('<script>alert(1)</script>')
        assert '<script>' not in result


class TestEmailSanitization:
    """Tests for email sanitization"""
    
    def test_valid_email(self):
        result = InputSanitizer.sanitize_email('TEST@EXAMPLE.COM')
        assert result == 'test@example.com'
    
    def test_email_with_spaces(self):
        result = InputSanitizer.sanitize_email('  test@example.com  ')
        assert result == 'test@example.com'
    
    def test_invalid_email(self):
        result = InputSanitizer.sanitize_email('not-an-email')
        assert result is None
    
    def test_email_with_xss(self):
        result = InputSanitizer.sanitize_email('test<script>@example.com')
        assert result is None


class TestPhoneSanitization:
    """Tests for phone sanitization"""
    
    def test_phone_with_spaces(self):
        result = InputSanitizer.sanitize_phone('+54 11 2233 4455')
        assert ' ' not in result
        assert result == '+541122334455'
    
    def test_phone_with_letters(self):
        result = InputSanitizer.sanitize_phone('11-2233-4455ABC')
        assert 'ABC' not in result
    
    def test_phone_keep_valid_chars(self):
        result = InputSanitizer.sanitize_phone('+54(11)2233-4455')
        assert '+54' in result
        assert '(' in result


class TestDictSanitization:
    """Tests for dictionary sanitization"""
    
    def test_sanitize_simple_dict(self):
        data = {
            'name': '<script>alert(1)</script>',
            'email': 'test@example.com'
        }
        result = InputSanitizer.sanitize_dict(data)
        assert '<script>' not in result['name']
        assert '&lt;' in result['name']
    
    def test_sanitize_nested_dict(self):
        data = {
            'user': {
                'name': '<b>test</b>',
                'details': {
                    'bio': '<script>xss</script>'
                }
            }
        }
        result = InputSanitizer.sanitize_dict(data)
        assert '<script>' not in result['user']['details']['bio']
    
    def test_sanitize_dict_with_lists(self):
        data = {
            'tags': ['<script>test</script>', 'normal tag']
        }
        result = InputSanitizer.sanitize_dict(data)
        assert '<script>' not in result['tags'][0]
    
    def test_max_depth_protection(self):
        # Deeply nested dict should not crash
        data = {'a': {'b': {'c': {'d': {'e': {'f': 'deep'}}}}}}
        result = InputSanitizer.sanitize_dict(data, max_depth=3)
        assert result is not None


class TestSanitizeFunction:
    """Tests for convenience sanitize_input function"""
    
    def test_sanitize_string(self):
        result = sanitize_input('<script>test</script>')
        assert '<script>' not in result
    
    def test_sanitize_dict(self):
        data = {'key': '<b>value</b>'}
        result = sanitize_input(data)
        assert '<b>' not in result['key']
    
    def test_sanitize_other_types(self):
        assert sanitize_input(123) == 123
        assert sanitize_input(None) is None
