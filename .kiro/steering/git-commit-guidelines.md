# Git Commit Guidelines

Scope: All commits to this repository

## Commit Message Format

```
<emoji> <type>(<scope>): <subject>
```

### Type + Emoji Reference

| Type | Emoji | Description |
|------|-------|-------------|
| feat | ✨ | New feature |
| fix | 🐛 | Bug fix |
| refactor | ♻️ | Code refactoring (no feature/fix) |
| docs | 📝 | Documentation changes |
| style | 💄 | Code style (formatting, whitespace) |
| perf | ⚡ | Performance improvement |
| test | ✅ | Adding or updating tests |
| ci | 👷 | CI/CD configuration |
| chore | 🔧 | Maintenance tasks |
| security | 🔒 | Security fixes |
| config | ⚙️ | Configuration changes |
| merge | 🔀 | Merge commits |

### Scope Examples

- `api` - API routes and endpoints
- `db` - Database models and queries
- `docker` - Docker and container config
- `scripts` - Build/run scripts
- `pose_processor` - Pose processing module
- `gait_analyzer` - Gait analysis module
- `users` - User management
- `auth` - Authentication

### Rules

1. All commit messages must be in English
2. Subject line max 50 characters
3. Use imperative mood: "Add feature" not "Added feature"
4. No period at the end of subject
5. Scope is optional but recommended

### Examples

```
✨ feat(api): Add cohort benchmark endpoint
🐛 fix(docker): Use correct venv path for uv sync
♻️ refactor(visualizer): Split into modular package
📝 docs(readme): Update installation instructions
👷 ci(docker): Enable build cache with cache bust
🔒 security(auth): Add rate limiting for login
```

## Branch Strategy

- `main` - Production releases only (tagged versions)
- `develop` - Active development branch

### Workflow

1. All development happens on `develop`
2. When ready to release:
   ```bash
   git checkout main
   git merge --squash develop
   git commit -m "🔀 merge(develop): <release summary>"
   git tag v1.x.x
   git push origin main --tags
   ```
3. Keep `main` clean with only release commits
