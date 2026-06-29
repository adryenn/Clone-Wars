```markdown
# Clone-Wars Development Patterns

> Auto-generated skill from repository analysis

## Overview
This skill teaches the core development patterns and conventions used in the Clone-Wars repository, a Python-based project with no detected framework. You'll learn about file organization, import/export styles, commit message habits, and how to maintain consistency throughout the codebase. This guide also covers the project's approach to testing and suggests useful commands for daily workflows.

## Coding Conventions

### File Naming
- Use **snake_case** for all filenames.
  - Example: `clone_utils.py`, `data_loader.py`

### Import Style
- Use **relative imports** within the package.
  - Example:
    ```python
    from .utils import helper_function
    from .models import DataModel
    ```

### Export Style
- Use **named exports** (explicitly define what is exported).
  - Example:
    ```python
    __all__ = ['main_function', 'HelperClass']
    ```

### Commit Messages
- Freeform style, no strict prefixing.
- Average length: ~57 characters.
- Example:
  ```
  Add support for new data format in loader module
  ```

## Workflows

### Code Contribution
**Trigger:** When adding or updating code in the repository  
**Command:** `/contribute-code`

1. Create a new branch for your feature or bugfix.
2. Follow snake_case naming for all new files.
3. Use relative imports for internal modules.
4. Explicitly declare exports with `__all__` in your modules.
5. Write clear, concise commit messages (~57 chars).
6. Submit a pull request for review.

### Code Review
**Trigger:** When reviewing a teammate's pull request  
**Command:** `/review-code`

1. Check for adherence to snake_case file naming.
2. Ensure relative imports are used.
3. Verify that `__all__` is set for module exports.
4. Confirm commit messages are descriptive and concise.
5. Run tests (see Testing Patterns).

## Testing Patterns

- **Testing framework:** Unknown (not detected).
- **Test file pattern:** Files are named with a `.test.ts` suffix (suggests some TypeScript usage for tests, or possible legacy/test integration).
  - Example: `clone_utils.test.ts`
- **How to write tests:** (Assumed pattern)
  - Place test files alongside or in a `tests/` directory.
  - Name test files after the module under test, with `.test.ts` suffix.

## Commands
| Command           | Purpose                                      |
|-------------------|----------------------------------------------|
| /contribute-code  | Start the code contribution workflow         |
| /review-code      | Begin the code review workflow               |
```
