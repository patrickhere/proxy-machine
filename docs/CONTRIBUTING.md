# Contributing to Proxy Machine

Thank you for your interest in contributing! This document provides guidelines for contributing to the project.

## Getting Started

### Prerequisites

- Python 3.10+
- uv (Python package manager)
- Git
- Basic knowledge of Magic: The Gathering card layouts

### Setup Development Environment

```bash
# Clone the repository
git clone <repo-url>
cd proxy-machine

# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create virtual environment
uv venv --python 3.10
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# Install dependencies
uv pip install -r requirements.txt

# Download bulk data (for testing)
uv run python tools/fetch_bulk.py --id all-cards
uv run python tools/fetch_bulk.py --id oracle-cards

# Build database
uv run python -c "from db.bulk_index import build_db_from_bulk_json, DB_PATH; build_db_from_bulk_json(DB_PATH)"

# Run tests
uv run pytest
```

## Development Workflow

See [mds/WORKFLOW.md](mds/WORKFLOW.md) for detailed development workflow.

### Quick Guidelines

1. **Create a feature branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes**
   - Follow existing code style
   - Add tests for new features
   - Update documentation

3. **Test your changes**
   ```bash
   uv run pytest
   uv run python tools/verify.py
   ```

4. **Commit with clear messages**
   ```bash
   git add -A
   git commit -m "Add feature: description"
   ```

5. **Push and create PR**
   ```bash
   git push origin feature/your-feature-name
   ```

## Code Style

### Python

- Follow PEP 8
- Use type hints where possible
- Keep functions focused and small
- Add docstrings to public functions

### Example

```python
def calculate_card_dimensions(dpi: int, card_width_inches: float) -> tuple[int, int]:
    """
    Calculate card dimensions in pixels.

    Args:
        dpi: Dots per inch for rendering
        card_width_inches: Card width in inches

    Returns:
        Tuple of (width_px, height_px)
    """
    width_px = int(card_width_inches * dpi)
    height_px = int(card_width_inches * 1.4 * dpi)  # Standard MTG ratio
    return width_px, height_px
```

## Testing

### Running Tests

```bash
# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/test_bulk_index.py

# Run with coverage
uv run pytest --cov=. --cov-report=html
```

### Writing Tests

- Place tests in `tests/` directory
- Name test files `test_*.py`
- Use descriptive test names
- Test edge cases

### Example Test

```python
def test_parse_deck_list():
    """Test deck list parsing with various formats."""
    decklist = "4 Lightning Bolt\n4 Counterspell"
    result = parse_deck_list(decklist)

    assert len(result) == 2
    assert result[0]['quantity'] == 4
    assert result[0]['name'] == 'Lightning Bolt'
```

## Documentation

### Updating Documentation

- **User guides:** `mds/guides/`
- **Development docs:** `mds/`
- **Deployment guides:** `docs/deployment/`
- **Sharing guides:** `docs/sharing/`

### Documentation Style

- Use clear, concise language
- Include code examples
- Add screenshots for UI features
- Keep examples generic (no personal info)

## Plugin Development

See [mds/guides/DEVELOPER_GUIDE.md](mds/guides/DEVELOPER_GUIDE.md) for plugin development.

### Plugin Structure

```python
from plugins.base import CardPlugin

class MyCustomPlugin(CardPlugin):
    """Custom card layout plugin."""

    def applies_to(self, card_data: dict) -> bool:
        """Check if this plugin should handle the card."""
        return card_data.get('layout') == 'my_custom_layout'

    def render(self, card_data: dict, context: dict) -> Image:
        """Render the card layout."""
        # Implementation here
        pass
```

## Submitting Changes

### Pull Request Process

1. **Update documentation** if needed
2. **Add tests** for new features
3. **Run all tests** and ensure they pass
4. **Update CHANGELOG.md** with your changes
5. **Create PR** with clear description

### PR Template

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Documentation update
- [ ] Performance improvement

## Testing
- [ ] All tests pass
- [ ] Added new tests
- [ ] Tested manually

## Checklist
- [ ] Code follows style guidelines
- [ ] Documentation updated
- [ ] CHANGELOG.md updated
```

## Reporting Issues

### Bug Reports

Include:
- Python version
- Operating system
- Steps to reproduce
- Expected vs actual behavior
- Error messages/logs

### Feature Requests

Include:
- Use case description
- Proposed solution
- Alternative solutions considered
- Examples (if applicable)

## Code of Conduct

### Our Standards

- Be respectful and inclusive
- Accept constructive criticism
- Focus on what's best for the project
- Show empathy towards others

### Unacceptable Behavior

- Harassment or discrimination
- Trolling or insulting comments
- Personal or political attacks
- Publishing others' private information

## Questions?

- Check [mds/GUIDE.md](mds/GUIDE.md) for usage help
- See [mds/WORKFLOW.md](mds/WORKFLOW.md) for development workflow
- Open an issue for questions or discussions

## License

By contributing, you agree that your contributions will be licensed under the same license as the project.

Thank you for contributing to Proxy Machine!
