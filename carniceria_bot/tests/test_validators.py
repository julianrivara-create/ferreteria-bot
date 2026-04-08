"""
Unit Tests for Validators
"""

import pytest
from bot_sales.security.validators import Validator


class TestValidateDNI:
    """Tests for DNI validation"""
    
    def test_valid_dni_7_digits(self):
        valid, msg = Validator.validate_dni("1234567")
        assert valid is True
        assert msg == ""
    
    def test_valid_dni_8_digits(self):
        valid, msg = Validator.validate_dni("12345678")
        assert valid is True
        assert msg == ""
    
    def test_valid_dni_with_dots(self):
        valid, msg = Validator.validate_dni("12.345.678")
        assert valid is True
    
    def test_invalid_dni_too_short(self):
        valid, msg = Validator.validate_dni("123456")
        assert valid is False
        assert "7 u 8 dígitos" in msg
    
    def test_invalid_dni_too_long(self):
        valid, msg = Validator.validate_dni("123456789")
        assert valid is False
    
    def test_invalid_dni_letters(self):
        valid, msg = Validator.validate_dni("12345ABC")
        assert valid is False
        assert "números" in msg.lower()
    
    def test_invalid_dni_empty(self):
        valid, msg = Validator.validate_dni("")
        assert valid is False
    
    def test_invalid_dni_out_of_range_low(self):
        valid, msg = Validator.validate_dni("0000123")
        assert valid is False
        assert "rango" in msg.lower()
    
    def test_invalid_dni_out_of_range_high(self):
        valid, msg = Validator.validate_dni("100000000")
        assert valid is False


class TestValidateEmail:
    """Tests for email validation"""
    
    def test_valid_email(self):
        valid, msg = Validator.validate_email("test@example.com")
        assert valid is True
        assert msg == ""
    
    def test_valid_email_subdomain(self):
        valid, msg = Validator.validate_email("user@mail.company.com")
        assert valid is True
    
    def test_valid_email_plus(self):
        valid, msg = Validator.validate_email("user+tag@example.com")
        assert valid is True
    
    def test_invalid_email_no_at(self):
        valid, msg = Validator.validate_email("testexample.com")
        assert valid is False
    
    def test_invalid_email_no_domain(self):
        valid, msg = Validator.validate_email("test@")
        assert valid is False
    
    def test_invalid_email_no_tld(self):
        valid, msg = Validator.validate_email("test@example")
        assert valid is False
    
    def test_invalid_email_empty(self):
        valid, msg = Validator.validate_email("")
        assert valid is False
    
    def test_email_normalization(self):
        valid, msg = Validator.validate_email("  TEST@EXAMPLE.COM  ")
        assert valid is True


class TestValidatePhone:
    """Tests for phone validation"""
    
    def test_valid_phone_argentina(self):
        valid, msg = Validator.validate_phone("1122334455")
        assert valid is True
    
    def test_valid_phone_with_country_code(self):
        valid, msg = Validator.validate_phone("+541122334455")
        assert valid is True
    
    def test_valid_phone_with_dashes(self):
        valid, msg = Validator.validate_phone("11-2233-4455")
        assert valid is True
    
    def test_valid_phone_with_spaces(self):
        valid, msg = Validator.validate_phone("+54 11 2233 4455")
        assert valid is True
    
    def test_invalid_phone_too_short(self):
        valid, msg = Validator.validate_phone("1234567")
        assert valid is False
    
    def test_invalid_phone_too_long(self):
        valid, msg = Validator.validate_phone("12345678901234")
        assert valid is False
    
    def test_invalid_phone_empty(self):
        valid, msg = Validator.validate_phone("")
        assert valid is False


class TestValidateSKU:
    """Tests for SKU validation"""
    
    def test_valid_sku(self):
        valid, msg = Validator.validate_sku("IP15-128-BLK")
        assert valid is True
    
    def test_valid_sku_underscores(self):
        valid, msg = Validator.validate_sku("MBA_M2_256")
        assert valid is True
    
    def test_invalid_sku_empty(self):
        valid, msg = Validator.validate_sku("")
        assert valid is False
    
    def test_invalid_sku_too_short(self):
        valid, msg = Validator.validate_sku("AB")
        assert valid is False
    
    def test_invalid_sku_special_chars(self):
        valid, msg = Validator.validate_sku("IP15@128")
        assert valid is False


class TestValidatePrice:
    """Tests for price validation"""
    
    def test_valid_price(self):
        valid, msg = Validator.validate_price(1200000)
        assert valid is True
    
    def test_valid_price_float(self):
        valid, msg = Validator.validate_price(1200.50)
        assert valid is True
    
    def test_invalid_price_zero(self):
        valid, msg = Validator.validate_price(0)
        assert valid is False
    
    def test_invalid_price_negative(self):
        valid, msg = Validator.validate_price(-1000)
        assert valid is False
    
    def test_invalid_price_too_high(self):
        valid, msg = Validator.validate_price(20000000)
        assert valid is False
    
    def test_invalid_price_none(self):
        valid, msg = Validator.validate_price(None)
        assert valid is False


class TestValidateStock:
    """Tests for stock validation"""
    
    def test_valid_stock_positive(self):
        valid, msg = Validator.validate_stock(10)
        assert valid is True
    
    def test_valid_stock_zero(self):
        valid, msg = Validator.validate_stock(0)
        assert valid is True
    
    def test_invalid_stock_negative(self):
        valid, msg = Validator.validate_stock(-5)
        assert valid is False
    
    def test_invalid_stock_none(self):
        valid, msg = Validator.validate_stock(None)
        assert valid is False
    
    def test_high_stock_warning(self, caplog):
        # Should still be valid but log warning
        valid, msg = Validator.validate_stock(15000)
        assert valid is True


class TestValidateCustomerData:
    """Tests for full customer data validation"""
    
    def test_valid_customer_data(self, sample_customer):
        valid, errors = Validator.validate_customer_data(sample_customer)
        assert valid is True
        assert len(errors) == 0
    
    def test_invalid_customer_no_nombre(self):
        data = {'email': 'test@example.com', 'contacto': '1122334455'}
        valid, errors = Validator.validate_customer_data(data)
        assert valid is False
        assert 'nombre' in errors
    
    def test_invalid_customer_bad_email(self):
        data = {'nombre': 'Test', 'email': 'invalid-email', 'contacto': '1122334455'}
        valid, errors = Validator.validate_customer_data(data)
        assert valid is False
        assert 'email' in errors
    
    def test_invalid_customer_multiple_errors(self):
        data = {'nombre': '', 'email': 'bad', 'contacto': '123'}
        valid, errors = Validator.validate_customer_data(data)
        assert valid is False
        assert len(errors) >= 2
