# Testing & Verifying search-wiki Skill in GitHub Copilot CLI

## Installation Status

✅ **INSTALLED** at: `~/.copilot/skills/search-wiki/SKILL.md`

Also installable at the shared agent-standard path: `~/.agents/skills/search-wiki/SKILL.md`

**Script location:** `/mnt/c/dev/github/confluence-retriever/scripts/wiki_answer.py`

**Installed via:** `python3 install.py --target copilot`

---

## Key Difference from Claude Code

| Feature | Claude Code | GitHub Copilot CLI |
|---------|------------|-------------------|
| Explicit skill invocation | `/search-wiki query` | ❌ Not supported |
| Skill trigger method | Direct command | 🤖 **Auto-detection** |
| How skills are called | User explicitly invokes | Copilot detects relevance & offers |
| Confirmation required | No (auto-runs) | Yes (unless `--allow-all`) |

**Bottom line:** GitHub Copilot CLI **automatically detects** when a skill is relevant. You don't explicitly call it — Copilot offers it when appropriate.

---

## Quick Test (3 minutes)

### Method 1: Verify Skill Is Loaded

```bash
copilot
```

Then type:
```
/env
```

Look for output like:
```
Skills: search-wiki
  Description: Search a Confluence wiki and synthesize...
```

### Method 2: Trigger the Skill Automatically

In the same `copilot` session, ask:

```
How do I authenticate to our API?
```

**Expected behavior:**
- Copilot analyzes your question
- Recognizes it's a wiki-related question
- Offers to use search-wiki skill
- You confirm (or it auto-runs with `--allow-all`)
- Displays wiki results with citations

**What to look for (verification):**
- Message: `[Running search-wiki...]` or `Searching Confluence...`
- Output format: `# Wiki results for 'authentication', 'API'`
- Page references: URLs from your Confluence instance
- Synthesis: Answer based on wiki content

---

## Testing Questions That Trigger the Skill

These questions match the skill's activation rules:

| Category | Example | Trigger |
|----------|---------|---------|
| Finding docs | "Where is the deployment guide?" | "where is" |
| How-to | "How do I authenticate?" | "how do I" |
| Definitions | "What is the auth process?" | "what is" |
| Searching | "Find the troubleshooting docs" | "find" |
| Steps | "Show me the setup steps" | "show me the steps" |
| Details | "Explain the API rate limits" | "explain", "details" |
| Verification | "According to the docs, how do we...?" | "according to the docs" |

---

## Non-Interactive Test (For Scripting)

```bash
copilot -p "How do I deploy the service?" --allow-all
```

**Flags:**
- `-p` = prompt (non-interactive)
- `--allow-all` = auto-accept all tool/skill invocations

**Expected output:**
- Automatically invokes search-wiki
- Returns synthesized answer with wiki citations
- Exit code 0 = success

---

## Verify Skill Is Actually Running

### Sign 1: Explicit Messages
Look in the response for:
- "searching the wiki"
- "[Running search-wiki...]"
- "wiki results"
- Skill name mentioned

### Sign 2: Output Format
Wiki results appear as:
```
# Wiki results for 'query'

## 1. Page Title
- **Space:** Name (KEY)
- **URL:** https://...
- **Excerpt:** ...
```

### Sign 3: Confluence URLs
Links in citations point to your Confluence instance:
```
https://your-instance.atlassian.net/wiki/spaces/KEY/pages/...
```

### Sign 4: Check Logs (Advanced)

```bash
tail -f ~/.config/github-copilot/logs/copilot.log | grep -i search-wiki
```

---

## Direct CLI Test (Without Copilot)

To verify the underlying `wiki_answer.py` works:

```bash
cd /mnt/c/dev/github/confluence-retriever

# Test 1: Basic search
python3 scripts/wiki_answer.py --query "test" --limit 3

# Test 2: With depth
python3 scripts/wiki_answer.py --query "authentication" --depth skim

# Test 3: Specific space
python3 scripts/wiki_answer.py --query "deployment" --space MT --limit 5
```

**Expected:** Ranked markdown with wiki results (exit code 0)

---

## Troubleshooting

### "Skill isn't activating for my question"

**Problem:** You ask a question but search-wiki doesn't run.

**Solutions:**
1. Use a trigger keyword: "how do I", "where is", "what is", "find", "show me", "explain"
2. Check skill is loaded: `/env` in copilot session
3. Try a simpler question: "How do I authenticate?" instead of complex query
4. Use `--allow-all` to auto-accept without prompts

### "Getting auth errors"

**Problem:** `wiki_answer.py` exits with code 3 (auth failed).

**Check:**
```bash
ls ~/.config/confluence-retriever/.env    # or ./confluence-retriever/.env
cat ~/.config/confluence-retriever/.env   # verify CONFLUENCE_PAT exists
```

**Fix:**
1. Regenerate PAT at your Confluence instance
2. Update `.env` file
3. Test directly: `python3 scripts/wiki_answer.py --query "test"`

### "No results returned"

**Problem:** Skill runs but returns no matching pages.

**Solutions:**
1. Search term doesn't exist in Confluence — verify manually first
2. Try broader term: "deployment" instead of "deploy microservices k8s"
3. Add `--limit 10` to see if any results exist
4. Use `--space KEY` if you know which space contains it

### "Skill loaded but not offered"

**Problem:** `/env` shows search-wiki but it's never suggested.

**Solutions:**
1. Your question doesn't match trigger keywords
2. Try explicitly wiki-related questions
3. Use `/skills` command to see if search-wiki is active
4. Restart copilot session: `/clear` then ask again

---

## Example Session

```bash
$ copilot
copilot > /env
Skills loaded:
- search-wiki: Search a Confluence wiki and synthesize...

copilot > How do I set up authentication?

[Copilot detects wiki relevance]

Let me search the wiki for authentication information.

[Running search-wiki with queries: ["authentication", "setup"]...]

# Wiki results for 'authentication', 'setup'

## 1. Authentication Setup Guide
- **Space:** IT (IT)
- **URL:** https://your-instance.atlassian.net/wiki/spaces/IT/pages/123
- **Excerpt:** To set up authentication, first generate a PAT...

Based on this documentation, here are the setup steps:
1. Generate a Personal Access Token at [Reference: Authentication Setup Guide]
2. Add it to your .env file
3. Test the connection

copilot > /exit
```

---

## Next Steps

1. **Quick test:** Run `/env` in copilot to verify skill loads
2. **Interactive test:** Ask a wiki question and observe auto-detection
3. **Non-interactive test:** Use `-p` flag with `--allow-all` for automation
4. **Integration:** Use in your development workflow
5. **Feedback:** Note which query types work best

---

## Resources

- **Setup guide:** [COPILOT_CLI_SETUP.md](COPILOT_CLI_SETUP.md)
- **Skill code:** `~/.copilot/skills/search-wiki/SKILL.md`
- **CLI script:** `/mnt/c/dev/github/confluence-retriever/scripts/wiki_answer.py`
- **Developer guide:** [.github/copilot-instructions.md](.github/copilot-instructions.md)
