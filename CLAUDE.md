See README.md for business logic description

Before making changes, create a git worktree. Never edit ~/src/jobwatch directly.

Never create a PR without instruction from the user.

## Code style

- Models are defined using SQLAlchemy 2.0 type annotations - don't add `mapped_column` if it's not needed
- Prefer obvious, uncomplicated code over excessive comments. If a comment is added, it should be direct and to the point.
