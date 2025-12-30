---
inclusion: always
---

# API Change Notification Guidelines

## Scope
All API changes under `src/api/v1/` directory

## Rule

**After adding or modifying any API functionality, you MUST:**

1. **Update `FRONTEND_API_CHANGES.md`** with a clear summary in **English**
2. **Include the following information:**
   - Date of change
   - API endpoint(s) affected (method + path)
   - What changed (new fields, removed fields, behavior changes)
   - Request/Response schema changes
   - Breaking changes (if any)
   - Migration notes for frontend developers

## Format Template

```markdown
## [YYYY-MM-DD] - <Feature/Fix Description>

### Endpoint: `<METHOD> /api/v1/<path>`

**Changes:**
- Added: <new fields/features>
- Modified: <changed behavior>
- Removed: <deprecated fields>

**Request Schema:**
```json
{
  "field": "type"
}
```

**Response Schema:**
```json
{
  "field": "type"
}
```

**Breaking Changes:** Yes/No
- <details if yes>

**Frontend Action Required:**
- <what frontend needs to do>
```

## Examples

### Good Example
```markdown
## [2024-12-30] - Add Video Streaming Support

### Endpoint: `GET /api/v1/sessions/{session_id}/video`

**Changes:**
- Added: HTTP Range Request support for video streaming
- Added: H.264 codec with FFmpeg fallback
- Modified: Response now returns video/mp4 instead of video/avi

**Response Headers:**
- `Accept-Ranges: bytes`
- `Content-Type: video/mp4`

**Breaking Changes:** No

**Frontend Action Required:**
- Update video player to use native HTML5 `<video>` tag
- Remove custom AVI decoder if used
```

## Enforcement

- This notification is **mandatory** for all API changes
- Must be done **before** committing the changes
- Frontend developers rely on this documentation for integration
