# Kiro Steering Configuration

This directory contains steering files that provide context and guidance to Kiro AI assistant for the RealSense Pose project.

## Steering Files Overview

| File | Purpose | Scope |
|------|---------|-------|
| `project-overview.md` | Project architecture, tech stack, and core principles | All interactions |
| `coding-conventions.md` | Python coding standards, file organization, and quality requirements | Code-related tasks |
| `api-design-guidelines.md` | FastAPI patterns, database integration, and API standards | API development |
| `git-commit-guidelines.md` | Commit message format, branching strategy, and release process | Git operations |
| `development-workflow.md` | Development environment, scripts, and troubleshooting | Development tasks |

## How Kiro Uses These Rules

### Automatic Application
- All steering files are automatically loaded when Kiro starts
- Rules are applied consistently across all interactions
- Workspace-level rules take precedence over global rules

### Context-Aware Assistance
- **Code modifications:** Follows coding conventions and architecture principles
- **API development:** Applies FastAPI standards and database patterns
- **Git operations:** Uses proper commit message format and branching strategy
- **Debugging:** References development workflow and troubleshooting guides

## Key Project Principles

### Architecture
- **Layered architecture** with clear dependency direction (downward only)
- **Facade pattern** for maintaining external compatibility
- **Single responsibility** principle for modules and files

### Code Quality
- **Type hints required** for all new/modified functions
- **File size limits** (400-600 lines) with splitting guidelines
- **Compile validation** required before commits

### Development Process
- **Branch strategy:** `develop` for active work, `main` for releases only
- **Commit format:** `<emoji> <type>(<scope>): <subject>`
- **Semantic versioning** for releases

## Quick Reference

### Common Commands
```bash
# Start development environment
.\scripts\run\run_api_with_db.ps1

# Validate code quality
python -m compileall src

# Run tests
pytest src/tests/

# Clean Docker environment
.\scripts\docker\docker_clean_all.ps1 --nuke
```

### Project Structure
```
src/
├── api/                    # FastAPI application layer
├── rehab_analyzer/         # Gait/lap/FFT analysis core
├── realsense_pose_extractor/ # Pose extraction core
├── db/                     # MongoDB models
├── utils/                  # Shared utilities
└── cli.py                  # CLI entry point
```

### Technology Stack
- **Backend:** FastAPI + MongoDB + Redis
- **Frontend:** Flutter Web UI
- **Infrastructure:** Docker + Kubernetes
- **Development:** uv (Python), PowerShell scripts

## Updating Steering Rules

When project conventions change:

1. **Update relevant steering file** in `.kiro/steering/`
2. **Test with Kiro** to ensure rules are applied correctly
3. **Commit changes** following git guidelines
4. **Inform team** about updated conventions

## Troubleshooting Steering

If Kiro isn't following expected patterns:

1. **Check file syntax** - Ensure markdown is properly formatted
2. **Verify file location** - Files must be in `.kiro/steering/`
3. **Restart Kiro** - Reload steering configuration
4. **Test specific scenarios** - Ask Kiro to perform tasks that should use the rules

## Examples of Steering in Action

### Code Generation
When asked to create a new API endpoint, Kiro will:
- Use FastAPI patterns from `api-design-guidelines.md`
- Follow file organization from `coding-conventions.md`
- Apply project architecture from `project-overview.md`

### Git Operations
When creating commits, Kiro will:
- Use emoji + type format from `git-commit-guidelines.md`
- Choose appropriate scope based on changed files
- Follow semantic versioning for releases

### Debugging Assistance
When troubleshooting issues, Kiro will:
- Reference common solutions from `development-workflow.md`
- Suggest appropriate diagnostic commands
- Follow project-specific debugging patterns

---

*This steering configuration ensures consistent, high-quality assistance tailored to the RealSense Pose project's specific needs and conventions.*