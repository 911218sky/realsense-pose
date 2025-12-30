# Git Commit Guidelines

## Commit Message Language

All commit messages MUST be written in **English** to ensure:
- International team collaboration
- Consistent and professional git history
- Easy understanding for future maintainers

## Commit Message Format

Use conventional commit format:

```
<type>(<scope>): <short description>

[optional body with more details]
```

### Types
- `feat`: New feature
- `fix`: Bug fix
- `refactor`: Code refactoring (no functional change)
- `docs`: Documentation changes
- `style`: Code style/formatting changes
- `perf`: Performance improvements
- `test`: Adding or updating tests
- `chore`: Build process, dependencies, or tooling changes

### Examples

```
feat(video): add H.264 encoding support with FFmpeg fallback

- Add FFmpegConverter utility class for video transcoding
- Support HTTP Range Requests for video streaming
- Auto-detect available codecs with fallback chain
```

```
fix(api): resolve session deletion not removing video files
```

```
refactor(processor): extract video codec selection logic
```

## Rules

1. First line should be under 72 characters
2. Use imperative mood ("add" not "added", "fix" not "fixed")
3. No period at the end of the subject line
4. Separate subject from body with a blank line
5. Body should explain WHAT and WHY, not HOW
