# Confluence PAT Setup

## Config File Location

The CLI reads credentials from a `.env` file in the **project root**:

```
confluence-retriever/.env
```

Standard `.env` key=value format — gitignored, never committed.

---

## Setup Steps

### 1. Generate a Personal Access Token

Go to your Confluence instance:

```
https://your-instance.atlassian.net/plugins/servlet/de.resolution.apitokenauth/admin
```

Or via your Confluence profile → Personal Access Tokens.

### 2. Create the .env file

```bash
cp .env.example .env
```

Then edit `.env` and fill in your values:

```
CONFLUENCE_URL=https://your-instance.atlassian.net
CONFLUENCE_PAT=your_personal_access_token_here
```

### 3. Lock file permissions (Linux/macOS)

```bash
chmod 600 .env
```

### 4. Verify it works

```bash
python3 scripts/wiki_answer.py --query "test" --limit 1
```

Exit code 0 with a result means the PAT and URL are correct.

---

## File Format

```
CONFLUENCE_URL=https://your-instance.atlassian.net
CONFLUENCE_PAT=ATCTT3xFfGH0A1b2C3d4E5f6G7h8I9j0...
```

Not:
```
ATCTT3xFfGH0...           ← Wrong — no variable name
export CONFLUENCE_PAT=... ← Wrong — no shell syntax
```

---

## Troubleshooting

| Exit code | Cause | Fix |
|-----------|-------|-----|
| 2 | `.env` file not found, or `CONFLUENCE_URL`/`CONFLUENCE_PAT` missing | Create `.env` from `.env.example` |
| 3 | Auth failed (401/403) | Regenerate PAT at your Confluence instance |
| 4 | Network error | Check VPN/connectivity to your Confluence host |

**Test connectivity manually:**

```bash
curl -H "Authorization: Bearer $(grep CONFLUENCE_PAT .env | cut -d= -f2)" \
  "$(grep CONFLUENCE_URL .env | cut -d= -f2)/rest/api/content/search?cql=text~%22test%22"
```

A JSON response with `"results"` confirms the PAT and URL are valid.
