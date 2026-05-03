# GitHub Copilot CLI — Quick Reference

## ✅ Status

**Skill is installed and ready to use.**

- **Location:** `~/.config/github-copilot/skills/search-wiki/SKILL.md`
- **Script:** `/mnt/c/dev/github/confluence-retriever/scripts/wiki_answer.py`
- **GitHub Copilot CLI version:** 1.0.39
- **Installed:** 2026-05-01

---

## Your Questions Answered

### 1. Is the skill installed?

✅ **YES** — at `~/.config/github-copilot/skills/search-wiki/SKILL.md`

**Verify:**
```bash
copilot
> /env
# Look for "Skills: search-wiki" in output
```

---

### 2. How do I test & verify it?

| Test | Command | Duration | What to Look For |
|------|---------|----------|------------------|
| **Quick** | `copilot` → `/env` | 30 sec | `search-wiki` in Skills section |
| **Interactive** | `copilot` → "How do I authenticate?" | 2 min | `[Running search-wiki...]` message |
| **Script** | `copilot -p "Where is the guide?" --allow-all` | 1 min | Auto-runs wiki search, returns results |
| **Direct** | `python3 wiki_answer.py --query "test"` | 30 sec | Markdown results (tests CLI independently) |

---

### 3. Does Copilot CLI have `/skillname` like Claude Code?

❌ **NO** — GitHub Copilot CLI works differently

| Aspect | Claude Code | GitHub Copilot CLI |
|--------|-------------|-------------------|
| **Invocation** | `/search-wiki query terms` | ❌ Not supported |
| **Trigger** | Explicit command | 🤖 **Auto-detection** |
| **How it works** | User types `/skillname` | Copilot analyzes question & offers skill |
| **Feel** | Explicit, command-driven | Natural, conversational |

**Why?** Copilot CLI uses intelligent skill auto-detection based on your natural language question, not explicit commands.

---

### 4. How do I trigger the skill?

Ask questions with **wiki-related keywords**:

| Keyword | Example | Triggers Skill |
|---------|---------|---|
| "How do I..." | "How do I authenticate?" | ✅ Yes |
| "Where is..." | "Where is the deployment guide?" | ✅ Yes |
| "Find..." | "Find the troubleshooting docs" | ✅ Yes |
| "What is..." | "What is the auth process?" | ✅ Yes |
| "Show me..." | "Show me the setup steps" | ✅ Yes |
| "Explain..." | "Explain our API rate limits" | ✅ Yes |
| "According to..." | "According to the docs, how do we...?" | ✅ Yes |

**How it works:**
1. You ask a question in `copilot`
2. Copilot analyzes it
3. Recognizes it needs wiki search
4. Offers to use `search-wiki` skill
5. You confirm (or auto-accept with `--allow-all`)
6. `wiki_answer.py` runs
7. Results synthesized with citations

---

### 5. How do I know it's triggered?

**Look for these signs:**

### Visual Indicators
```
✓ Message: "[Running search-wiki...]"
✓ Output: "# Wiki results for 'query'"
✓ Format: ## 1. Page Title
           - Space: Name (KEY)
           - URL: https://...
✓ Citations: [Reference: Page Title]
✓ Response synthesizes from wiki pages
```

### Expected Output Format
```
[Searching Confluence for your question...]

# Wiki results for 'authentication', 'API'

## 1. Authentication Setup Guide
- **Space:** IT (IT)
- **URL:** https://your-instance.atlassian.net/wiki/spaces/IT/pages/123
- **Excerpt:** To authenticate, use JWT tokens...

Based on the documentation I found:
1. Generate a JWT token at /auth/token
2. Include it in the Authorization header
3. [Reference: Authentication Setup Guide]
```

### Check Logs (If unsure)
```bash
tail -f ~/.config/github-copilot/logs/copilot.log | grep -i search-wiki
```

---

## Quick Start

### 30-Second Test

```bash
copilot
> /env

# Look for "search-wiki" in Skills section
# If present, skill is loaded ✓
```

### 2-Minute Full Test

```bash
copilot
> How do I authenticate to our API?

# Watch Copilot:
# 1. Detect wiki relevance
# 2. Offer search-wiki skill
# 3. Return "[Running search-wiki...]" 
# 4. Display "# Wiki results..."
# 5. Synthesize answer with citations
```

### Non-Interactive (Automation)

```bash
copilot -p "Where is the deployment guide?" --allow-all

# Auto-accepts skill usage
# Returns wiki results
# Exit code 0 on success
```

---

## Troubleshooting

### Skill not activating
- **Cause:** Question doesn't match trigger keywords
- **Fix:** Use "How do I...", "Where is...", "Find...", etc.

### Getting 401/403 auth errors
- **Cause:** CONFLUENCE_PAT expired or `.env` missing
- **Fix:** Check `.env` file, regenerate PAT if needed

### No results returned
- **Cause:** Query term doesn't exist in Confluence
- **Fix:** Verify page exists manually, try broader search term

### Skill loaded but never offered
- **Cause:** Questions not wiki-related enough
- **Fix:** Try explicit wiki questions: "How do I...", "Find...", etc.

---

## Documentation

| File | Purpose |
|------|---------|
| **COPILOT_CLI_TESTING.md** | Detailed testing guide with examples |
| **COPILOT_CLI_SETUP.md** | Installation & usage walkthrough |
| **COPILOT_CLI_QUICK_START.txt** | Simple 4-step setup reference |
| **.github/copilot-instructions.md** | Developer reference |
| **README.md** | Updated with Copilot CLI info |

---

## Key Points to Remember

1. **Copilot CLI ≠ Claude Code**
   - No `/skillname` syntax
   - Skills auto-detected, not explicit
   - More conversational, less command-driven

2. **The skill runs automatically**
   - Ask a wiki question
   - Copilot figures out you need `search-wiki`
   - Returns results

3. **Verify with `/env`**
   - Shows all loaded skills
   - Quick way to confirm installation

4. **Look for wiki keywords in responses**
   - `[Running search-wiki...]`
   - `# Wiki results for...`
   - Confluence URLs in citations

---

## Start Using Now

```bash
copilot
> How should I approach API authentication?

# Copilot will automatically use search-wiki and return
# relevant wiki pages synthesized into a direct answer!
```

🎉 **Enjoy your wiki searches!**
