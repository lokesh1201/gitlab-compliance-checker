# Contributing to gitlab-compliance-checker

Thank you for your interest in contributing to **gitlab-compliance-checker**! We welcome contributions of all kinds including bug reports, feature requests, documentation improvements, and code submissions.

## How to Report Issues

- Before opening a new issue, please search existing issues to avoid duplicates.
- When creating an issue, **please use the provided [Issue Template](.gitlab/issue_template.md)**.
  This template helps you provide all necessary details such as:
  - Clear and detailed bug reproduction steps
  - Environment information (tool version, Python version, OS)
  - Screenshots or logs if applicable

  The issue template streamlines triaging and helps maintainers diagnose problems quickly.

## Suggesting Features

- Open a new issue labeled `feature-request`.
- Please use the **[Issue Template](.gitlab/issue_template.md)** to describe the feature and its intended usage clearly.

## Code Contributions

- Fork the repository and create a branch from `main`.
- Follow the existing coding style and use [PEP 8](https://pep8.org/) conventions.
- Write descriptive commit messages following [Conventional Commits](https://www.conventionalcommits.org/):
  - `feat:` for new features
  - `fix:` for bug fixes
  - `docs:` for documentation changes
  - `chore:` for maintenance and tooling changes
- Add tests for new features or bug fixes.
- Run linters and tests before submitting a merge request.

- When submitting a merge request, please use the **[Merge Request Template](.gitlab/mr_template.md)**.
  This ensures you provide all necessary information such as:
  - Description of changes
  - Related issues (with Closes #issue_number if applicable)
  - Type of change (patch, feature, breaking)
  - Test status and checklist compliance

## Pull Request Process

- Submit a merge request targeting the `main` branch with all requested details filled in the template.
- Clearly state the semantic versioning impact in the merge request description.
- Respond to review feedback promptly.
- Ensure all continuous integration checks pass.

## Code Style and Testing

- This project uses `flake8` for linting and `black` for code formatting.
- Tests are run with `pytest`.
- Run tests locally before creating a merge request.

## Code of Conduct

Please read and follow the [Code of Conduct](CODE_OF_CONDUCT.md) to foster a welcoming and respectful community.

---

Thank you for helping to improve **gitlab-compliance-checker**!

---

### Helpful Links

- [Issue Template](.gitlab/issue_template.md)
- [Merge Request Template](.gitlab/mr_template.md)
