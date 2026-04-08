# Contributing to Sales Bot

## Development Setup

```bash
# Fork and clone
git clone https://github.com/your-username/iphone-bot-demo
cd iphone-bot-demo

# Create virtualenv
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install pre-commit hooks
cp .git-hooks/pre-commit .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit

# Run tests
pytest tests/ -v
```

## Code Style

- **Formatting**: Black (line length 120)
- **Linting**: Flake8
- **Docstrings**: Google style
- **Type hints**: Required for public functions

```python
# Good
def calculate_total(items: List[Dict[str, Any]]) -> int:
    """
    Calculate total price from items.
    
    Args:
        items: List of item dictionaries
        
    Returns:
        Total price in ARS
    """
    return sum(item['price'] * item['qty'] for item in items)

# Bad
def calc(x):
    return sum(i['price']*i['qty'] for i in x)
```

## Testing

- Write tests for all new features
- Maintain >80% coverage
- Use pytest fixtures for setup
- Mock external APIs

```python
def test_create_hold(temp_db):
    """Test hold creation"""
    bl = BusinessLogic(temp_db)
    result = bl.crear_reserva("SKU-123", "User", "Phone")
    assert result['status'] == 'success'
```

## Pull Request Process

1. **Create feature branch**: `git checkout -b feature/my-feature`
2. **Make changes**: Follow code style
3. **Add tests**: Cover new code
4. **Run checks**: `pytest && black . && flake8`
5. **Commit**: Use conventional commits
6. **Push**: `git push origin feature/my-feature`
7. **Create PR**: Fill template completely

## Conventional Commits

```
feat: add multi-product cart
fix: resolve cache invalidation bug
docs: update API documentation
test: add integration tests for checkout
refactor: simplify authentication logic
perf: optimize database queries
chore: update dependencies
```

## Architecture Guidelines

### Module Organization
```
bot_sales/
  core/          # Core functionality
  security/      # Auth, encryption, validation
  integrations/  # External APIs
  intelligence/  # AI features
```

### Design Principles
- Single Responsibility
- Dependency Injection
- Fail gracefully
- Log everything
- Cache aggressively
- Test thoroughly

## Security

- Never commit secrets
- Use environment variables
- Sanitize all inputs
- Encrypt PII
- Follow OWASP Top 10

## Questions?

Open an issue or contact maintainers.

Thanks for contributing! 🎉
