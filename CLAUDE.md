See README.md for business logic description

Before making changes, create a git worktree. Never edit ~/src/jobwatch directly.

Never create a PR without instruction from the user.

Web UI uses bootstrap for styling

## Code style

- Models are defined using SQLAlchemy 2.0 type annotations - don't add `mapped_column` if it's not needed
- Prefer obvious, uncomplicated code over excessive comments. If a comment is added, it should be direct and to the point.
- Use declarative style for unit test utils where possible, and keep arguments minimal: `user()` instead of `create_user(name="")`
- Committing in unit tests is a no-op and generally not required
- Don't use session.flush() unless required. Relationships can be set directly: job=job, rather than flushing and using job_id=job.id.