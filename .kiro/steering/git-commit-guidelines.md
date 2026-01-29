# Git Commit Guidelines

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

### Commit Message Rules

1. **All commit messages must be in English**
2. **Subject line max 50 characters**
3. **Use imperative mood:** "Add feature" not "Added feature"
4. **No period at the end of subject**
5. **Scope is optional but recommended**

### Good Commit Examples

```
✨ feat(api): Add cohort benchmark endpoint
🐛 fix(docker): Use correct venv path for uv sync
♻️ refactor(visualizer): Split into modular package
📝 docs(readme): Update installation instructions
👷 ci(docker): Enable build cache with cache bust
🔒 security(auth): Add rate limiting for login
⚡ perf(gait_analyzer): Optimize stride detection algorithm
✅ test(lap_detector): Add unit tests for anchor detection
🔧 chore(deps): Update FastAPI to v0.104.1
💄 style(api): Fix import order and formatting
```

## Branch Strategy

- **`develop`** - Active development branch for all work-in-progress
- **`main`** - Release-only branch, updated by squash-merge from `develop`

### Workflow Rules

1. **Always create commits on `develop`** (feature/fix/refactor/etc.)
2. **Never commit directly to `main`**
3. **When ready to release, squash all `develop` commits into one on `main`:**
   ```bash
   git checkout main
   git merge --squash develop
   git commit -m "🔀 merge(develop): <release summary>"
   git tag -a v1.x.x -m "Release v1.x.x - <release description>"
   git push origin main --tags
   ```
4. **Keep `main` clean with only release commits**

## Version Tagging

### Semantic Versioning

Follow [Semantic Versioning 2.0.0](https://semver.org/):

```
vMAJOR.MINOR.PATCH
```

- **MAJOR**: Incompatible API changes
- **MINOR**: Backward-compatible functionality additions  
- **PATCH**: Backward-compatible bug fixes

### Tag Format Rules

- **Use annotated tags:** `git tag -a v1.0.0 -m "message"`
- **Always prefix with `v`:** `v1.0.0`, `v1.2.3`, `v2.0.0`
- **Tag message should describe the release**

### Version Examples

```bash
# Major release (breaking changes)
git tag -a v2.0.0 -m "Release v2.0.0 - Major API redesign"

# Minor release (new features)
git tag -a v1.1.0 -m "Release v1.1.0 - Add user cohort management"

# Patch release (bug fixes)
git tag -a v1.0.1 -m "Release v1.0.1 - Fix trajectory rendering bug"
```

### Tag Management Commands

**Create and push tag:**
```bash
git tag -a v1.0.0 -m "Release v1.0.0 - Initial stable release"
git push origin v1.0.0
```

**List all tags:**
```bash
git tag
```

**Delete local tag:**
```bash
git tag -d v1.0.0
```

**Delete remote tag:**
```bash
git push origin :refs/tags/v1.0.0
# or
git push origin --delete v1.0.0
```

**View tag details:**
```bash
git show v1.0.0
```

## Release Notes Template

When creating a GitHub Release for a tag, include:

1. **What's New**: New features and improvements
2. **Bug Fixes**: Issues resolved
3. **Breaking Changes**: API changes requiring user action
4. **Dependencies**: Updated dependencies
5. **Contributors**: Acknowledge contributors

### Release Notes Example

```markdown
## What's New
- ✨ Added cohort benchmark analysis API
- ✨ Implemented real-time pose visualization
- ⚡ Improved gait analysis performance by 40%

## Bug Fixes
- 🐛 Fixed trajectory rendering for edge cases
- 🐛 Resolved MongoDB connection timeout issues
- 🐛 Fixed Docker volume mounting on Windows

## Breaking Changes
- 🔥 Removed deprecated `/v1/legacy` endpoints
- 🔥 Changed pose data format (see migration guide)

## Dependencies
- Updated FastAPI to v0.104.1
- Updated MongoDB driver to v4.6.0
- Added Redis caching support

## Contributors
Thanks to @contributor1 and @contributor2 for their contributions!
```

## AI Assistant Guidelines for Git

When I ask you to create commits or work with git:

1. **Always follow the emoji + type format**
2. **Choose appropriate scope based on the files changed**
3. **Keep subject lines under 50 characters**
4. **Use imperative mood in commit messages**
5. **Suggest appropriate version bumps for releases**
6. **Include relevant scope when multiple modules are affected**

### Multi-scope Commit Examples

```bash
# When changes affect multiple areas
✨ feat(api,db): Add user cohort management with MongoDB models
🐛 fix(docker,scripts): Resolve container startup and build issues
♻️ refactor(gait_analyzer,pose_processor): Extract common utilities
```